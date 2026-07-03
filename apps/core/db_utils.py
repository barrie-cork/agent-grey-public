"""
Database utilities with environment protection for Django 4.2

Provides safe database connection methods that verify environment
variables before establishing connections.
"""

import logging

from django.db import connection

from apps.core.environment_manager import EnvironmentManager

logger = logging.getLogger(__name__)


def get_safe_db_connection():
    """
    Get a database connection after verifying environment variables.
    This prevents using wrong database URLs (Issue #109).

    Returns:
        Django database connection object

    Raises:
        RuntimeError: If environment tampering is detected
    """
    import os

    # Check if we're about to use test database in non-test environment
    db_url = os.environ.get("DATABASE_URL", "")
    environment = os.environ.get("ENVIRONMENT", "")

    if "test:test@localhost" in db_url and environment != "test":
        logger.error("CRITICAL: Test database URL detected in non-test environment!")
        logger.error(f"Environment: {environment}")
        logger.error(f"Database URL: {db_url}")

        # Try to correct it
        EnvironmentManager.enforce_environment()

        # Check again
        db_url = os.environ.get("DATABASE_URL", "")
        if "test:test@localhost" in db_url:
            raise RuntimeError(
                "Cannot connect to database: Test database URL detected. "
                "This is a critical security issue. "
                "Please check your environment configuration."
            )

    # Verify environment before connecting
    if not EnvironmentManager.verify_environment():
        logger.warning(
            "Environment variables were tampered with, corrected before DB connection"
        )

    return connection


def verify_database_settings():
    """
    Verify that database settings are correct for the current environment.

    Returns:
        dict: Status and details about database configuration
    """
    import os

    from django.conf import settings

    environment = os.environ.get("ENVIRONMENT", "unknown")
    db_url = os.environ.get("DATABASE_URL", "")

    # Expected patterns for each environment
    expected_patterns = {
        "local": "thesis_grey_dev_db",
        "development": "thesis_grey_dev_db",
        "staging": "thesis_grey_staging_db",
        "production": None,  # Production URL comes from DigitalOcean
        "test": "test",
    }

    result = {
        "environment": environment,
        "database_url_masked": _mask_password(db_url),
        "is_valid": True,
        "issues": [],
    }

    # Check for test database in wrong environment
    if "test:test@localhost" in db_url and environment != "test":
        result["is_valid"] = False
        result["issues"].append(f"Test database URL found in {environment} environment")

    # Check for expected database name
    expected = expected_patterns.get(environment)
    if expected and expected not in db_url:
        result["is_valid"] = False
        result["issues"].append(
            f"Expected database name containing '{expected}' for {environment} environment"
        )

    # Check Django settings
    if hasattr(settings, "DATABASES"):
        default_db = settings.DATABASES.get("default", {})
        if default_db.get("HOST") == "localhost" and environment in [
            "local",
            "development",
        ]:
            result["issues"].append(
                "Database HOST is 'localhost' but should be 'db' for Docker environment"
            )

    return result


def _mask_password(db_url):
    """Mask password in database URL for safe logging."""
    if "@" in db_url and "://" in db_url:
        parts = db_url.split("@")
        if ":" in parts[0].split("://")[-1]:
            user = parts[0].split("://")[-1].split(":")[0]
            return f"{db_url.split('://')[0]}://{user}:****@{parts[1]}"
    return db_url


class SafeDatabaseConnection:
    """
    Context manager for safe database operations with environment protection.

    Usage:
        with SafeDatabaseConnection() as cursor:
            cursor.execute("SELECT * FROM users")
            results = cursor.fetchall()
    """

    def __init__(self):
        self.connection = None
        self.cursor = None

    def __enter__(self):
        """Enter the context, verify environment, and return cursor."""
        # Verify environment before connecting
        EnvironmentManager.verify_environment()

        self.connection = get_safe_db_connection()
        self.cursor = self.connection.cursor()
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context, close cursor and enforce environment."""
        if self.cursor:
            self.cursor.close()

        # Enforce environment after database operations
        EnvironmentManager.enforce_environment()

        # Don't suppress exceptions
        return False
