"""Deployment configuration validation utility.

This module provides centralized validation for deployment environment variables
to prevent silent failures and ensure configuration consistency.

Created: 2025-10-17
Purpose: Phase 3 of Post-Deployment Refactoring Plan
"""

import logging
import os
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Custom exceptions for deployment validation
class ValidationError(Exception):
    """Base exception for validation errors."""

    pass


class EnvironmentVariableError(ValidationError):
    """Exception raised for environment variable validation failures."""

    pass


class DatabaseConfigError(ValidationError):
    """Exception raised for database configuration validation failures."""

    pass


class RedisConfigError(ValidationError):
    """Exception raised for Redis configuration validation failures."""

    pass


class SentryConfigError(ValidationError):
    """Exception raised for Sentry configuration validation failures."""

    pass


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    message: str
    severity: str = "info"  # info, warning, error, critical
    hints: Optional[List[str]] = None

    def __post_init__(self):
        """Ensure hints is a list."""
        if self.hints is None:
            self.hints = []


@dataclass
class ValidationReport:
    """Comprehensive validation report."""

    environment: str
    passed: bool
    results: List[ValidationResult]
    errors: List[str]
    warnings: List[str]

    @property
    def summary(self) -> str:
        """Get human-readable summary."""
        status = "✅ PASSED" if self.passed else "❌ FAILED"
        return (
            f"Deployment Validation Report - {self.environment.upper()}\n"
            f"Status: {status}\n"
            f"Errors: {len(self.errors)}\n"
            f"Warnings: {len(self.warnings)}\n"
        )

    def detailed_report(self) -> str:
        """Get detailed validation report."""
        lines = [self.summary, "\n" + "=" * 60 + "\n"]

        # Critical errors
        if self.errors:
            lines.append("ERRORS (must fix):")
            for error in self.errors:
                lines.append(f"  ❌ {error}")
            lines.append("")

        # Warnings
        if self.warnings:
            lines.append("WARNINGS (should review):")
            for warning in self.warnings:
                lines.append(f"  ⚠️  {warning}")
            lines.append("")

        # Detailed results
        lines.append("DETAILED RESULTS:")
        for result in self.results:
            icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🔥"}
            lines.append(f"  {icon.get(result.severity, 'ℹ️')} {result.message}")
            if result.hints:
                for hint in result.hints:
                    lines.append(f"      💡 {hint}")
        lines.append("")

        return "\n".join(lines)


class DeploymentValidator:
    """Validate deployment configuration."""

    def __init__(self, environment: str = "production"):
        """Initialize validator.

        Args:
            environment: Environment name (production, staging, local)
        """
        self.environment = environment
        self.results: List[ValidationResult] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_all(self) -> ValidationReport:
        """Run all validation checks.

        Returns:
            ValidationReport with comprehensive results
        """
        logger.info(f"Starting deployment validation for {self.environment}")

        # Run all validation checks
        self.validate_secret_key()
        self.validate_database_url()
        self.validate_redis_url()
        self.validate_sentry_dsn()
        self.validate_allowed_hosts()

        # Determine if validation passed
        passed = len(self.errors) == 0

        return ValidationReport(
            environment=self.environment,
            passed=passed,
            results=self.results,
            errors=self.errors,
            warnings=self.warnings,
        )

    def _add_result(
        self,
        is_valid: bool,
        message: str,
        severity: str = "info",
        hints: Optional[List[str]] = None,
    ):
        """Add validation result and update tracking lists."""
        result = ValidationResult(
            is_valid=is_valid,
            message=message,
            severity=severity,
            hints=hints or [],
        )
        self.results.append(result)

        if severity == "error" or severity == "critical":
            self.errors.append(message)
        elif severity == "warning":
            self.warnings.append(message)

    def validate_secret_key(self) -> ValidationResult:
        """Validate SECRET_KEY configuration.

        Returns:
            ValidationResult indicating if SECRET_KEY is valid
        """
        secret_key = os.environ.get("SECRET_KEY", "")

        if not secret_key or not secret_key.strip():
            self._add_result(
                is_valid=False,
                message="SECRET_KEY is not set or empty",
                severity="critical",
                hints=[
                    "Generate with: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'",
                    "Set in DigitalOcean: Apps → Settings → Environment Variables",
                    "Minimum length: 50 characters for production",
                ],
            )
            raise EnvironmentVariableError("SECRET_KEY validation failed")

        if len(secret_key) < 50:
            self._add_result(
                is_valid=False,
                message=f"SECRET_KEY too short ({len(secret_key)} chars, minimum 50)",
                severity="error",
                hints=[
                    "Generate a new key with sufficient length",
                    "Longer keys provide better cryptographic security",
                ],
            )
            raise EnvironmentVariableError("SECRET_KEY too short")

        # Check for common insecure values
        insecure_patterns = [
            "django-insecure-",
            "secret",
            "password",
            "changeme",
            "test",
            "development",
        ]
        if any(pattern in secret_key.lower() for pattern in insecure_patterns):
            self._add_result(
                is_valid=False,
                message="SECRET_KEY contains insecure patterns",
                severity="critical",
                hints=[
                    "Never use default or easily guessable secret keys",
                    "Generate a cryptographically secure random key",
                ],
            )
            raise EnvironmentVariableError("SECRET_KEY insecure")

        self._add_result(
            is_valid=True,
            message=f"SECRET_KEY valid ({len(secret_key)} characters)",
            severity="info",
        )

        return self.results[-1]

    def validate_database_url(self) -> ValidationResult:
        """Validate DATABASE_URL configuration.

        Returns:
            ValidationResult indicating if DATABASE_URL is valid
        """
        database_url = os.environ.get("DATABASE_URL", "")

        if not database_url or not database_url.strip():
            self._add_result(
                is_valid=False,
                message="DATABASE_URL is not set or empty",
                severity="critical",
                hints=[
                    "Required for production deployment",
                    "Format: postgresql://user:password@host:port/database?sslmode=require",
                    "Get from DigitalOcean Managed PostgreSQL connection string",
                ],
            )
            raise DatabaseConfigError("DATABASE_URL validation failed")

        # Check for common mistakes
        if database_url in ["", '""', "''", "None", "null"]:
            self._add_result(
                is_valid=False,
                message="DATABASE_URL contains invalid placeholder value",
                severity="critical",
                hints=[
                    "Set actual DATABASE_URL, not a placeholder",
                    "Empty strings and 'None' are not valid values",
                ],
            )
            raise DatabaseConfigError("DATABASE_URL is placeholder")

        # Parse URL
        try:
            parsed = urlparse(database_url)
        except Exception as e:
            self._add_result(
                is_valid=False,
                message=f"DATABASE_URL has invalid format: {e}",
                severity="critical",
                hints=[
                    "Check URL format: postgresql://user:password@host:port/database",
                    "Ensure no special characters are improperly escaped",
                ],
            )
            raise DatabaseConfigError("DATABASE_URL format invalid")

        # Validate scheme
        if parsed.scheme not in ["postgresql", "postgres", "psql"]:
            self._add_result(
                is_valid=False,
                message=f"DATABASE_URL has invalid scheme: {parsed.scheme} (expected postgresql)",
                severity="error",
                hints=[
                    "Use 'postgresql://' scheme for PostgreSQL",
                    "Other database backends not supported in production",
                ],
            )
            raise DatabaseConfigError("DATABASE_URL scheme invalid")

        # Check for localhost in production
        if self.environment == "production" and parsed.hostname in [
            "localhost",
            "127.0.0.1",
            "::1",
        ]:
            self._add_result(
                is_valid=False,
                message="DATABASE_URL points to localhost in production",
                severity="critical",
                hints=[
                    "Use DigitalOcean Managed PostgreSQL connection string",
                    "Localhost is not accessible from DigitalOcean App Platform",
                ],
            )
            raise DatabaseConfigError("DATABASE_URL uses localhost in production")

        # Check for SSL mode in production
        if self.environment == "production" and "sslmode=require" not in database_url:
            self._add_result(
                is_valid=False,
                message="DATABASE_URL missing SSL mode parameter",
                severity="warning",
                hints=[
                    "Add '?sslmode=require' to connection string",
                    "SSL is required for secure database connections",
                ],
            )

        self._add_result(
            is_valid=True,
            message=f"DATABASE_URL valid (host: {parsed.hostname})",
            severity="info",
        )

        return self.results[-1]

    def validate_redis_url(self) -> ValidationResult:
        """Validate REDIS_URL configuration.

        Returns:
            ValidationResult indicating if REDIS_URL is valid
        """
        redis_url = os.environ.get("REDIS_URL", "")

        # Redis is optional - fallback to database cache
        if not redis_url or not redis_url.strip():
            self._add_result(
                is_valid=True,
                message="REDIS_URL not configured, will use database cache",
                severity="warning",
                hints=[
                    "Redis provides better performance than database cache",
                    "Recommended for production: Use DigitalOcean Managed Redis",
                ],
            )
            return self.results[-1]

        # Check for common mistakes
        if redis_url in ['""', "''", "None", "null"]:
            self._add_result(
                is_valid=False,
                message="REDIS_URL contains invalid placeholder value",
                severity="warning",
                hints=[
                    "Either set actual REDIS_URL or leave unset for database cache",
                    "Empty strings and 'None' are treated as misconfiguration",
                ],
            )
            return self.results[-1]

        # Parse URL
        try:
            parsed = urlparse(redis_url)
        except Exception as e:
            self._add_result(
                is_valid=False,
                message=f"REDIS_URL has invalid format: {e}",
                severity="warning",
                hints=[
                    "Check URL format: redis://host:port/db or rediss://host:port/db (SSL)",
                ],
            )
            raise RedisConfigError("REDIS_URL format invalid")

        # Validate scheme
        if parsed.scheme not in ["redis", "rediss"]:
            self._add_result(
                is_valid=False,
                message=f"REDIS_URL has invalid scheme: {parsed.scheme}",
                severity="warning",
                hints=[
                    "Use 'redis://' for non-SSL or 'rediss://' for SSL",
                ],
            )
            raise RedisConfigError("REDIS_URL scheme invalid")

        # Check for localhost in production
        if self.environment == "production" and parsed.hostname in [
            "localhost",
            "127.0.0.1",
            "::1",
        ]:
            self._add_result(
                is_valid=False,
                message="REDIS_URL points to localhost in production",
                severity="critical",
                hints=[
                    "Use DigitalOcean Managed Redis connection string",
                    "Localhost is not accessible from DigitalOcean App Platform",
                    "This will cause deployment failures!",
                ],
            )
            raise RedisConfigError("REDIS_URL uses localhost in production")

        # Recommend SSL in production
        if self.environment == "production" and parsed.scheme == "redis":
            self._add_result(
                is_valid=True,
                message="REDIS_URL uses non-SSL connection",
                severity="warning",
                hints=[
                    "Consider using 'rediss://' for SSL encryption",
                    "DigitalOcean Managed Redis supports SSL",
                ],
            )
        else:
            self._add_result(
                is_valid=True,
                message=f"REDIS_URL valid (host: {parsed.hostname}, SSL: {parsed.scheme == 'rediss'})",
                severity="info",
            )

        return self.results[-1]

    def validate_sentry_dsn(self) -> ValidationResult:
        """Validate SENTRY_DSN configuration.

        Returns:
            ValidationResult indicating if SENTRY_DSN is valid
        """
        sentry_dsn = os.environ.get("SENTRY_DSN", "")

        # Sentry is optional
        if not sentry_dsn or not sentry_dsn.strip():
            self._add_result(
                is_valid=True,
                message="SENTRY_DSN not configured, error monitoring disabled",
                severity="info",
                hints=[
                    "Optional: Configure Sentry for error monitoring",
                    "Sign up at https://sentry.io",
                ],
            )
            return self.results[-1]

        # Check for common mistakes
        if sentry_dsn in ['""', "''", "None", "null"]:
            self._add_result(
                is_valid=True,
                message="SENTRY_DSN contains placeholder, error monitoring disabled",
                severity="info",
            )
            return self.results[-1]

        # Validate DSN format
        if not sentry_dsn.startswith(("http://", "https://")):
            self._add_result(
                is_valid=False,
                message="SENTRY_DSN has invalid format (must start with http:// or https://)",
                severity="warning",
                hints=[
                    "Get DSN from Sentry.io project settings",
                    "Format: https://[key]@[org].ingest.sentry.io/[project]",
                ],
            )
            raise SentryConfigError("SENTRY_DSN format invalid")

        # Check for sentry.io domain (most common)
        if "sentry.io" not in sentry_dsn and "sentry.com" not in sentry_dsn:
            self._add_result(
                is_valid=True,
                message="SENTRY_DSN uses custom Sentry instance",
                severity="info",
                hints=[
                    "Using self-hosted or custom Sentry instance",
                ],
            )
        else:
            self._add_result(
                is_valid=True,
                message="SENTRY_DSN valid, error monitoring enabled",
                severity="info",
            )

        return self.results[-1]

    def validate_allowed_hosts(self) -> ValidationResult:
        """Validate ALLOWED_HOSTS configuration.

        Returns:
            ValidationResult indicating if ALLOWED_HOSTS is valid
        """
        allowed_hosts = os.environ.get("ALLOWED_HOSTS", "")

        # ALLOWED_HOSTS is critical for production
        if not allowed_hosts or not allowed_hosts.strip():
            if self.environment == "production":
                self._add_result(
                    is_valid=False,
                    message="ALLOWED_HOSTS not configured in production",
                    severity="critical",
                    hints=[
                        "Required for Django to accept requests",
                        "Format: grey-lit-app-ifa37.ondigitalocean.app,localhost",
                        "Comma-separated list of allowed hostnames",
                    ],
                )
                raise EnvironmentVariableError("ALLOWED_HOSTS validation failed")
            else:
                self._add_result(
                    is_valid=True,
                    message="ALLOWED_HOSTS not configured (OK for development)",
                    severity="info",
                )
                return self.results[-1]

        # Parse comma-separated hosts
        hosts = [h.strip() for h in allowed_hosts.split(",") if h.strip()]

        if not hosts:
            self._add_result(
                is_valid=False,
                message="ALLOWED_HOSTS is empty after parsing",
                severity="critical",
                hints=[
                    "Provide at least one valid hostname",
                ],
            )
            raise EnvironmentVariableError("ALLOWED_HOSTS empty")

        # Check for wildcard in production
        if self.environment == "production" and "*" in hosts:
            self._add_result(
                is_valid=False,
                message="ALLOWED_HOSTS contains wildcard '*' in production",
                severity="critical",
                hints=[
                    "Wildcard allows any host - serious security risk!",
                    "Specify exact hostnames instead",
                ],
            )
            raise EnvironmentVariableError("ALLOWED_HOSTS wildcard in production")

        # Check for shell-style glob patterns (not supported by Django)
        invalid_patterns = []
        for host in hosts:
            if "*" in host and host != "*":
                # Check for invalid patterns like "10.244.*" or "*.example.*"
                if not host.startswith("."):
                    invalid_patterns.append(host)

        if invalid_patterns:
            self._add_result(
                is_valid=False,
                message=f"ALLOWED_HOSTS contains invalid patterns: {invalid_patterns}",
                severity="error",
                hints=[
                    "Django does NOT support shell-style glob patterns",
                    "Valid: '.example.com' (subdomain wildcard)",
                    "Invalid: '10.244.*' (IP wildcard)",
                    "For IP ranges, use ALLOWED_CIDR_NETS instead",
                ],
            )
            raise EnvironmentVariableError("ALLOWED_HOSTS invalid patterns")

        self._add_result(
            is_valid=True,
            message=f"ALLOWED_HOSTS valid ({len(hosts)} hosts configured)",
            severity="info",
        )

        return self.results[-1]


def validate_deployment_config(environment: str = "production") -> ValidationReport:
    """Convenience function to validate deployment configuration.

    Args:
        environment: Environment name (production, staging, local)

    Returns:
        ValidationReport with validation results

    Example:
        >>> report = validate_deployment_config("production")
        >>> if not report.passed:
        ...     print(report.detailed_report())
        ...     raise SystemExit(1)
    """
    validator = DeploymentValidator(environment=environment)
    return validator.validate_all()
