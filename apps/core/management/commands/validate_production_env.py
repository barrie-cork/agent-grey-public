"""
Management command to validate production environment variables.
Useful for deployment debugging and pre-deployment checks.
"""

from django.core.management.base import BaseCommand

from apps.core.utils.production_config import (
    get_cache_configuration,
    get_cors_and_csrf_config,
    get_redis_config_for_digitalocean,
    validate_required_env_vars,
)


class Command(BaseCommand):
    help = "Validate production environment configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-redis", action="store_true", help="Test Redis connection"
        )
        parser.add_argument(
            "--check-db", action="store_true", help="Test database connection"
        )

    def handle(self, *args, **options):  # noqa: C901 - Production env validation
        self.stdout.write("=== Production Environment Validation ===")

        # Validate environment variables
        validation_results = validate_required_env_vars()

        if validation_results["valid"]:
            self.stdout.write(
                self.style.SUCCESS("✓ All required environment variables are set")
            )
        else:
            self.stdout.write(
                self.style.ERROR("✗ Environment variable validation failed:")
            )
            for error in validation_results["errors"]:
                self.stdout.write(f"  - {self.style.ERROR(error)}")

        if validation_results["warnings"]:
            self.stdout.write(self.style.WARNING("⚠ Warnings:"))
            for warning in validation_results["warnings"]:
                self.stdout.write(f"  - {self.style.WARNING(warning)}")

        # Show variable status
        self.stdout.write("\n=== Environment Variables ===")
        for var_name, var_info in validation_results["variables"].items():
            if var_info["set"]:
                status = (
                    self.style.SUCCESS("✓")
                    if var_info["valid"]
                    else self.style.ERROR("✗")
                )
                self.stdout.write(f"{status} {var_name}: Set")
            else:
                self.stdout.write(f"{self.style.ERROR('✗')} {var_name}: Not set")

        # Test cache configuration
        self.stdout.write("\n=== Cache Configuration ===")
        try:
            cache_config = get_cache_configuration()
            backend = cache_config["default"]["BACKEND"]
            self.stdout.write(f"Backend: {backend}")

            if "redis" in backend.lower():
                redis_config = get_redis_config_for_digitalocean()
                self.stdout.write(f"Redis status: {redis_config['reason']}")

                if options["check_redis"] and redis_config["enabled"]:
                    self.test_redis_connection()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Cache configuration error: {e}"))

        # Test CORS/CSRF configuration
        self.stdout.write("\n=== CORS/CSRF Configuration ===")
        try:
            cors_csrf = get_cors_and_csrf_config()
            self.stdout.write(f"Allowed hosts: {cors_csrf['ALLOWED_HOSTS']}")
            self.stdout.write(
                f"CSRF origins: {len(cors_csrf['CSRF_TRUSTED_ORIGINS'])} configured"
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ CORS/CSRF configuration error: {e}"))

        # Test database connection
        if options["check_db"]:
            self.stdout.write("\n=== Database Connection Test ===")
            self.test_database_connection()

    def test_redis_connection(self):
        """Test Redis connection."""
        try:
            from apps.core.utils.redis_utils import get_safe_redis_connection

            redis_conn = get_safe_redis_connection()

            if redis_conn.ping():
                self.stdout.write(self.style.SUCCESS("✓ Redis connection successful"))
            else:
                self.stdout.write(self.style.ERROR("✗ Redis ping failed"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Redis connection error: {e}"))

    def test_database_connection(self):
        """Test database connection."""
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

            if result and result[0] == 1:
                self.stdout.write(
                    self.style.SUCCESS("✓ Database connection successful")
                )
            else:
                self.stdout.write(self.style.ERROR("✗ Database query failed"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Database connection error: {e}"))
