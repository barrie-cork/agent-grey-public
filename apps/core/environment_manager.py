"""
Environment Configuration Manager

This module provides robust environment configuration management across:
1. Local development (Docker)
2. Staging (Docker)
3. Production (DigitalOcean)

It ensures environment variables are loaded correctly and prevents
the override issues reported in Issue #109.

CRITICAL: This module implements environment locking to prevent runtime overrides
of critical configuration variables that can cause database connection failures.
"""

import logging
import os
import sys
from typing import Any, Dict

# Configure logging early
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class EnvironmentManager:
    """
    Centralized environment configuration manager that ensures
    correct environment variables are loaded based on deployment context.
    """

    # Environment type detection
    ENVIRONMENT_TYPES = {
        "local": "grey_lit_project.settings.local",
        "development": "grey_lit_project.settings.local",
        "staging": "grey_lit_project.settings.staging",
        "production": "grey_lit_project.settings.production",
    }

    # Database configuration templates
    # Each environment has its own separate database
    DATABASE_CONFIGS = {
        "local": {
            "url": "postgres://thesis_grey_user:dev_password_123@db:5432/thesis_grey_dev_db",
            "host": "db",
            "port": 5432,
            "name": "thesis_grey_dev_db",
            "user": "thesis_grey_user",
            "password": "dev_password_123",
            "redis_url": "redis://localhost:6379/0",
        },
        "development": {
            "url": "postgres://thesis_grey_user:dev_password_123@db:5432/thesis_grey_dev_db",
            "host": "db",
            "port": 5432,
            "name": "thesis_grey_dev_db",
            "user": "thesis_grey_user",
            "password": "dev_password_123",
            "redis_url": "redis://localhost:6379/0",
        },
        "staging": {
            "url": (
                "postgres://thesis_grey_staging_user:"
                "staging_secure_password_456@db_staging:5432/thesis_grey_staging_db"
            ),
            "host": "db_staging",
            "port": 5432,
            "name": "thesis_grey_staging_db",
            "user": "thesis_grey_staging_user",
            "password": "staging_secure_password_456",
            "redis_url": "redis://:staging_redis_456@redis_staging:6379/0",
        },
        "production": {
            "url": None,  # Will be loaded from DigitalOcean environment
            "host": None,  # Will be parsed from DATABASE_URL
            "port": None,
            "name": None,
            "user": None,
            "password": None,
            "redis_url": None,  # Will be loaded from environment
        },
    }

    # Class-level lock to prevent multiple initializations and overrides
    _initialized = False
    _locked_vars = {}

    def __init__(self):
        """Initialize the environment manager."""
        # Safety override to completely disable Environment Manager
        if os.environ.get("SKIP_ENVIRONMENT_MANAGER") == "true":
            logger.info(
                "⚠️  Environment Manager disabled via SKIP_ENVIRONMENT_MANAGER=true"
            )
            return

        self.environment_type = self._detect_environment()
        self.deployment_type = self._detect_deployment_type()
        self._validate_environment()
        self._force_correct_settings()
        self._lock_critical_variables()

    def _detect_environment(self) -> str:
        """
        Detect the current environment based on various indicators.

        Priority order:
        1. ENVIRONMENT variable (explicit)
        2. DEPLOYMENT_TYPE variable
        3. DigitalOcean detection
        4. Docker detection
        5. Default to local
        """
        logger.debug("Starting environment detection...")

        # Check explicit ENVIRONMENT variable
        env = os.environ.get("ENVIRONMENT", "").lower()
        if env in self.ENVIRONMENT_TYPES:
            logger.debug(f"Environment detected from ENVIRONMENT variable: {env}")
            return env

        # Check deployment type
        deployment = os.environ.get("DEPLOYMENT_TYPE", "").lower()
        if deployment == "digitalocean":
            logger.debug(
                "Environment detected from DEPLOYMENT_TYPE=digitalocean: production"
            )
            return "production"
        elif deployment == "docker":
            # Check if it's staging or local
            if os.environ.get("STAGING", "").lower() == "true":
                logger.debug(
                    "Environment detected from DEPLOYMENT_TYPE=docker + STAGING=true: staging"
                )
                return "staging"
            logger.debug("Environment detected from DEPLOYMENT_TYPE=docker: local")
            return "local"

        # Check for DigitalOcean
        is_do = self._is_digitalocean()
        logger.debug(f"DigitalOcean detection result: {is_do}")
        if is_do:
            logger.debug(
                "Environment detected from DigitalOcean indicators: production"
            )
            return "production"

        # Check for Docker
        is_docker = self._is_docker()
        logger.debug(f"Docker detection result: {is_docker}")
        if is_docker:
            # Default Docker to local unless specified
            logger.debug("Environment detected from Docker indicators: local")
            return "local"

        # Default to local
        logger.debug("Environment defaulted to: local")
        return "local"

    def _detect_deployment_type(self) -> str:
        """Detect the deployment type (docker, digitalocean, local)."""
        if self._is_digitalocean():
            return "digitalocean"
        elif self._is_docker():
            return "docker"
        else:
            return "local"

    def _is_digitalocean(self) -> bool:
        """Check if running on DigitalOcean App Platform."""
        # Check for DigitalOcean-specific environment variables
        digitalocean_indicators = [
            os.environ.get("DIGITALOCEAN_APP_ID"),
            os.environ.get("DIGITALOCEAN_ACCESS_TOKEN"),
            os.environ.get("DO_APP_ID"),
            os.environ.get(
                "DIGITALOCEAN_APP_NAME"
            ),  # Common DigitalOcean App Platform variable
            os.environ.get("APP_URL"),  # DigitalOcean App Platform sets this
        ]

        # Check if any DigitalOcean indicators are present
        if any(digitalocean_indicators):
            return True

        # Check for production DATABASE_URL patterns that indicate DigitalOcean managed database
        database_url = os.environ.get("DATABASE_URL", "")
        if database_url:
            # DigitalOcean managed databases typically use these patterns
            digitalocean_db_patterns = [
                "doadmin",  # DigitalOcean admin user
                ".db.ondigitalocean.com",  # DigitalOcean database hostname pattern
                "@db-postgresql-",  # Another DigitalOcean pattern
            ]
            if any(pattern in database_url for pattern in digitalocean_db_patterns):
                return True

        # Check for common DigitalOcean environment variables
        if os.environ.get("PORT") and not self._is_docker():
            # DigitalOcean App Platform sets PORT, and we're not in Docker
            return True

        return False

    def _is_docker(self) -> bool:
        """Check if running inside Docker container."""
        # Multiple detection methods for robustness
        checks = []

        # Check 1: .dockerenv file
        checks.append(os.path.exists("/.dockerenv"))

        # Check 2: Environment variable
        checks.append(os.environ.get("DOCKER_CONTAINER", "").lower() == "true")

        # Check 3: Deployment type
        checks.append(os.environ.get("DEPLOYMENT_TYPE", "").lower() == "docker")

        # Check 4: Cgroup file (handle file not existing)
        try:
            if os.path.exists("/proc/1/cgroup"):
                with open("/proc/1/cgroup", "r") as f:
                    checks.append("docker" in f.read())
        except Exception:
            pass

        # Check 5: Hostname pattern (Docker often uses container IDs)
        import socket

        hostname = socket.gethostname()
        checks.append(
            len(hostname) == 12 and all(c in "0123456789abcdef" for c in hostname)
        )

        is_docker = any(checks)
        logger.debug(f"Docker detection checks: {checks}, result: {is_docker}")
        return is_docker

    def _validate_environment(self):
        """
        Validate that critical environment variables are set correctly.
        Raises ValueError if misconfiguration is detected.
        """
        current_django_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        expected_settings = self.ENVIRONMENT_TYPES[self.environment_type]

        # Check for the problematic test configuration
        test_db_url = "postgres://test:test@localhost:5432/test"
        current_db_url = os.environ.get("DATABASE_URL", "")

        if test_db_url in current_db_url:
            logger.warning(
                f"Test database URL detected in {self.environment_type} environment!"
            )
            logger.warning(f"Current DATABASE_URL: {current_db_url}")
            logger.warning("This will be corrected automatically.")

            # Track where this might be coming from
            import traceback

            logger.debug("Call stack when test DB detected:")
            for line in traceback.format_stack():
                logger.debug(line.strip())

        # Check for settings mismatch
        if current_django_settings and current_django_settings != expected_settings:
            logger.warning("Settings mismatch detected!")
            logger.warning(f"Current: {current_django_settings}")
            logger.warning(f"Expected: {expected_settings}")
            logger.warning("This will be corrected automatically.")

        # Check if environment is locked
        if os.environ.get("ENVIRONMENT_LOCKED", "").lower() == "true":
            logger.info("Environment is locked - preventing external overrides")

    def _is_digitalocean_database(self, database_url: str) -> bool:
        """
        Check if database URL is from DigitalOcean managed database.

        Args:
            database_url: Database connection string

        Returns:
            True if DigitalOcean managed database detected
        """
        digitalocean_patterns = [
            "ondigitalocean.com",
            "doadmin",
            "@db-postgresql-",
            ".db.ondigitalocean.com",
        ]
        return any(pattern in database_url for pattern in digitalocean_patterns)

    def _configure_local_environment(self, db_config: Dict[str, Any]):
        """
        Configure environment variables for local/development.

        Args:
            db_config: Database configuration dict
        """
        os.environ["DATABASE_URL"] = db_config["url"]
        os.environ["POSTGRES_DB"] = db_config["name"]
        os.environ["POSTGRES_USER"] = db_config["user"]
        os.environ["POSTGRES_PASSWORD"] = db_config["password"]
        os.environ["REDIS_URL"] = db_config["redis_url"]
        os.environ["CELERY_BROKER_URL"] = db_config["redis_url"]
        os.environ["CELERY_RESULT_BACKEND"] = db_config["redis_url"]

    def _configure_staging_environment(self, db_config: Dict[str, Any]):
        """
        Configure environment variables for staging.

        Args:
            db_config: Database configuration dict
        """
        # Check for incorrect test database URL
        if "test:test@localhost" in os.environ.get("DATABASE_URL", ""):
            logger.warning("Correcting test database URL in staging environment")

        os.environ["DATABASE_URL"] = db_config["url"]
        os.environ["POSTGRES_DB"] = db_config["name"]
        os.environ["POSTGRES_USER"] = db_config["user"]
        os.environ["POSTGRES_PASSWORD"] = db_config["password"]
        os.environ["POSTGRES_HOST"] = db_config["host"]
        os.environ["REDIS_URL"] = db_config["redis_url"]
        os.environ["CELERY_BROKER_URL"] = db_config["redis_url"]
        os.environ["CELERY_RESULT_BACKEND"] = db_config["redis_url"]

        # Staging-specific settings
        os.environ.setdefault("STAGING_DB_PASSWORD", db_config["password"])
        os.environ.setdefault("STAGING_REDIS_PASSWORD", "staging_redis_456")

    def _configure_production_environment(self):
        """
        Configure environment variables for production.

        CRITICAL: Only validates, does not override DigitalOcean variables.
        """
        current_db_url = os.environ.get("DATABASE_URL", "")

        # Only intervene if there are obvious test/development values
        if "test:test@localhost" in current_db_url:
            logger.error("ERROR: Test database URL detected in production!")
            logger.error("Production must use DigitalOcean managed database")
            os.environ.pop("DATABASE_URL", None)
        elif current_db_url and self.deployment_type == "digitalocean":
            logger.info("Using DigitalOcean managed database")

        # Warn if Redis URL missing (but don't override DigitalOcean)
        if not os.environ.get("REDIS_URL") and self.deployment_type != "digitalocean":
            logger.warning("No Redis URL found in production environment")

        # Production should not have DEBUG enabled
        os.environ["DEBUG"] = "False"

    def _log_environment_info(self, environment: str, settings_module: str):
        """
        Log environment configuration information.

        Args:
            environment: Environment type
            settings_module: Django settings module
        """
        logger.info(f"✅ Environment configured: {environment}")
        logger.info(f"   Settings: {settings_module}")
        logger.info(f"   Deployment: {self.deployment_type}")
        logger.info(f"   Database: {self._get_safe_database_url()}")

        if environment == "production" and self.deployment_type == "digitalocean":
            logger.info("   DigitalOcean App Platform detected")
            logger.info("   DATABASE_URL preserved from DigitalOcean environment")
        elif environment == "local" and self._is_digitalocean():
            logger.warning(
                "   DigitalOcean detected but environment set to 'local' - "
                "this may indicate a configuration issue"
            )

    def _force_correct_settings(self):
        """
        Force the correct environment settings based on detected environment.
        This prevents the override issues from Issue #109.
        """
        current_db_url = os.environ.get("DATABASE_URL", "")

        # CRITICAL: Preserve DigitalOcean environment variables
        if self._is_digitalocean_database(current_db_url):
            logger.info(
                "🔒 DigitalOcean DATABASE_URL detected, preserving all environment variables"
            )
            logger.info(f"DATABASE_URL: {current_db_url[:50]}...")
            return

        environment = self.environment_type
        settings_module = self.ENVIRONMENT_TYPES[environment]

        # Force correct Django settings module
        os.environ["DJANGO_SETTINGS_MODULE"] = settings_module

        # Get the appropriate database configuration
        db_config = self.DATABASE_CONFIGS.get(
            environment, self.DATABASE_CONFIGS["local"]
        )

        # Configure environment-specific settings
        if environment in ["local", "development"]:
            self._configure_local_environment(db_config)
        elif environment == "staging":
            self._configure_staging_environment(db_config)
        elif environment == "production":
            self._configure_production_environment()

        # Set additional environment flags
        os.environ["ENVIRONMENT"] = environment
        os.environ["DEPLOYMENT_TYPE"] = self.deployment_type

        # Set debug based on environment
        if environment in ["local", "development"]:
            os.environ["DEBUG"] = "True"
        else:
            os.environ["DEBUG"] = "False"

        self._log_environment_info(environment, settings_module)

    def _lock_critical_variables(self):
        """
        Lock critical environment variables to prevent runtime overrides.
        This is a defense against Issue #109 where variables get mysteriously overridden.

        Compatible with Django 4.2 - uses a verification approach rather than
        trying to override os.environ methods.
        """
        if os.environ.get("ENVIRONMENT_LOCKED", "").lower() == "true":
            # Store current values
            critical_vars = [
                "DATABASE_URL",
                "DJANGO_SETTINGS_MODULE",
                "POSTGRES_DB",
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
                "REDIS_URL",
                "CELERY_BROKER_URL",
                "CELERY_RESULT_BACKEND",
                "ENVIRONMENT",
                "DEPLOYMENT_TYPE",
                "DEBUG",
            ]

            for var in critical_vars:
                if var in os.environ:
                    self._locked_vars[var] = os.environ[var]

            logger.info(
                f"Locked {len(self._locked_vars)} critical environment variables"
            )

            # Set a marker that variables are locked
            self.__class__._initialized = True

    @classmethod
    def verify_environment(cls) -> bool:
        """
        Verify that locked environment variables haven't been changed.
        Call this at critical points (e.g., before database connections).

        Returns:
            True if environment is valid, False if tampering detected
        """
        if not cls._initialized or not cls._locked_vars:
            return True  # Not initialized or no locked vars

        violations = []
        for var, locked_value in cls._locked_vars.items():
            current_value = os.environ.get(var)
            if current_value != locked_value:
                violations.append(
                    {"variable": var, "locked": locked_value, "current": current_value}
                )
                # Force correction
                os.environ[var] = locked_value
                logger.warning(
                    f"CORRECTED: {var} was changed, restored to locked value"
                )

        if violations:
            logger.error(
                f"Environment tampering detected! {len(violations)} variables were changed"
            )
            for v in violations:
                logger.error(
                    f"  {v['variable']}: locked='{v['locked']}' but found='{v['current']}'"
                )
            return False

        return True

    @classmethod
    def enforce_environment(cls):
        """
        Force all locked variables back to their correct values.
        This is a stronger version of verify_environment that always enforces.
        """
        if not cls._initialized or not cls._locked_vars:
            return

        for var, locked_value in cls._locked_vars.items():
            if os.environ.get(var) != locked_value:
                logger.info(f"Enforcing {var} to locked value")
                os.environ[var] = locked_value

    def _get_safe_database_url(self) -> str:
        """Get database URL with password masked for logging."""
        url = os.environ.get("DATABASE_URL", "")
        if "@" in url:
            # Mask password in URL
            parts = url.split("@")
            if "://" in parts[0]:
                creds = parts[0].split("://")[-1]
                if ":" in creds:
                    user = creds.split(":")[0]
                    masked = f"{url.split('://')[0]}://{user}:****@{parts[1]}"
                    return masked
        return url

    def get_config(self) -> Dict[str, Any]:
        """
        Get the current environment configuration.

        Returns:
            Dictionary with all environment settings
        """
        return {
            "environment": self.environment_type,
            "deployment": self.deployment_type,
            "django_settings": os.environ.get("DJANGO_SETTINGS_MODULE"),
            "debug": os.environ.get("DEBUG"),
            "database_url": self._get_safe_database_url(),
            "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            "celery_broker": os.environ.get(
                "CELERY_BROKER_URL", "redis://localhost:6379/0"
            ),
        }

    @classmethod
    def initialize(cls):
        """
        Initialize the environment manager and configure the environment.
        This should be called at the earliest point in application startup.
        """
        manager = cls()
        config = manager.get_config()

        logger.info("=" * 50)
        logger.info("Environment Configuration Summary:")
        for key, value in config.items():
            logger.info(f"  {key}: {value}")
        logger.info("=" * 50)

        return manager


# Initialize on module import to ensure early configuration
# This prevents the override issues from Issue #109
if "manage.py" in sys.argv[0] or "celery" in " ".join(sys.argv):
    # Only auto-initialize for Django management commands and Celery
    _env_manager = EnvironmentManager.initialize()
