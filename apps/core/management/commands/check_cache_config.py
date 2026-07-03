"""
Management command to check cache configuration and diagnose issues.
"""

import json
import time
import uuid

from decouple import config
from django.conf import settings
from django.core.cache import cache, caches
from django.core.management.base import BaseCommand

from apps.core.redis_config import check_redis_connection


class Command(BaseCommand):
    help = "Check cache configuration and test cache operations"

    def _check_cache_backend_settings(self):
        """Phase 1: Check cache backend configuration."""
        self.stdout.write("1. Cache Backend Configuration:")
        cache_config = getattr(settings, "CACHES", {})
        for cache_name, cache_conf in cache_config.items():
            self.stdout.write(f"   - {cache_name}:")
            self.stdout.write(
                f"     Backend: {cache_conf.get('BACKEND', 'Not configured')}"
            )
            self.stdout.write(f"     Location: {cache_conf.get('LOCATION', 'Not set')}")
            if "OPTIONS" in cache_conf:
                self.stdout.write(
                    f"     Options: {json.dumps(cache_conf['OPTIONS'], indent=6)}"
                )
        return cache_config

    def _check_default_cache_instance(self):
        """Phase 2: Check default cache instance details."""
        self.stdout.write("\n2. Default Cache Instance:")
        try:
            default_cache = caches["default"]
            self.stdout.write(f"   Type: {type(default_cache).__name__}")
            self.stdout.write(f"   Module: {type(default_cache).__module__}")

            # Check if it's a database cache
            if hasattr(default_cache, "_table"):
                self.stdout.write(f"   Database Table: {default_cache._table}")

            # Check if it's a Redis cache
            self._check_redis_cache_details(default_cache)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   Error getting default cache: {e}"))

    def _check_redis_cache_details(self, cache_instance):
        """Check Redis-specific cache details."""
        if hasattr(cache_instance, "_cache"):
            self.stdout.write(
                f"   Internal Cache Type: {type(cache_instance._cache).__name__}"
            )
            if hasattr(cache_instance._cache, "connection_pool"):
                pool = cache_instance._cache.connection_pool
                self.stdout.write(
                    f"   Redis Connection Pool: {pool.__class__.__name__}"
                )
                self.stdout.write(
                    f"   Max Connections: {getattr(pool, 'max_connections', 'N/A')}"
                )

    def _test_redis_connection(self):
        """Phase 3: Test Redis connection."""
        self.stdout.write("\n3. Redis Connection Test:")
        try:
            is_connected, message = check_redis_connection()
            if is_connected:
                self.stdout.write(self.style.SUCCESS(f"   ✓ {message}"))
            else:
                self.stdout.write(self.style.ERROR(f"   ✗ {message}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   Error checking Redis: {e}"))

    def _test_cache_operations(self):
        """Phase 4: Test cache operations with timing."""
        self.stdout.write("\n4. Cache Operations Test:")

        # Check cache validation settings
        skip_validation = config("CACHE_SKIP_VALIDATION", default=False, cast=bool)
        allow_failed = config("CACHE_ALLOW_FAILED_VALIDATION", default=False, cast=bool)
        self.stdout.write(f"   CACHE_SKIP_VALIDATION: {skip_validation}")
        self.stdout.write(f"   CACHE_ALLOW_FAILED_VALIDATION: {allow_failed}")

        # Test with unique keys to avoid conflicts
        test_key = f"cache_diagnostic_{uuid.uuid4().hex[:8]}"
        test_value = f"test_value_{uuid.uuid4().hex[:8]}"

        # Test SET operation
        self._test_cache_set(test_key, test_value)

        # Small delay for replication
        time.sleep(0.1)

        # Test GET operation
        self._test_cache_get(test_key, test_value)

        # Test DELETE operation
        self._test_cache_delete(test_key)

        # Show cache key prefix info
        self._show_cache_key_prefix()

    def _test_cache_set(self, test_key, test_value):
        """Test cache SET operation with timing."""
        try:
            start_time = time.time()
            cache.set(test_key, test_value, 60)
            set_time = (time.time() - start_time) * 1000  # ms
            self.stdout.write(
                self.style.SUCCESS(f"   ✓ SET operation successful ({set_time:.2f}ms)")
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ SET operation failed: {e}"))

    def _test_cache_get(self, test_key, test_value):
        """Test cache GET operation with retry logic."""
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                start_time = time.time()
                retrieved = cache.get(test_key)
                get_time = (time.time() - start_time) * 1000  # ms

                if retrieved == test_value:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"   ✓ GET operation successful: {retrieved} ({get_time:.2f}ms)"
                        )
                    )
                    break
                else:
                    self._handle_get_mismatch(attempt, max_attempts, retrieved)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ✗ GET operation failed: {e}"))
                break

    def _handle_get_mismatch(self, attempt, max_attempts, retrieved):
        """Handle GET operation value mismatches."""
        if attempt < max_attempts - 1:
            self.stdout.write(
                self.style.WARNING(
                    f"   ! GET attempt {attempt + 1} returned unexpected value: {retrieved}"
                )
            )
            time.sleep(0.5 * (attempt + 1))  # Exponential backoff
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"   ✗ GET failed after {max_attempts} attempts. Final value: {retrieved}"
                )
            )

    def _test_cache_delete(self, test_key):
        """Test cache DELETE operation."""
        try:
            cache.delete(test_key)
            self.stdout.write(self.style.SUCCESS("   ✓ DELETE operation successful"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ DELETE operation failed: {e}"))

    def _show_cache_key_prefix(self):
        """Show cache key prefix information."""
        if hasattr(cache, "key_prefix") or hasattr(cache, "_cache"):
            self.stdout.write("\n   Cache Key Prefix Info:")
            if hasattr(cache, "key_prefix"):
                self.stdout.write(f"   Key Prefix: {cache.key_prefix}")
            if hasattr(cache, "_cache") and hasattr(cache._cache, "key_prefix"):
                self.stdout.write(f"   Internal Key Prefix: {cache._cache.key_prefix}")

    def _check_database_cache_table(self, cache_config):
        """Phase 5: Check database cache table if applicable."""
        if "django.core.cache.backends.db.DatabaseCache" not in str(
            cache_config.get("default", {}).get("BACKEND", "")
        ):
            return

        self.stdout.write("\n5. Database Cache Table Check:")
        from django.db import connection

        table_name = cache_config["default"].get("LOCATION", "cache_table")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                );
            """,
                [table_name],
            )
            exists = cursor.fetchone()[0]
            if exists:
                self._show_cache_table_info(connection, cursor, table_name)
            else:
                self._show_cache_table_missing(table_name)

    def _show_cache_table_info(self, connection, cursor, table_name):
        """Show information about existing cache table."""
        self.stdout.write(self.style.SUCCESS(f'   ✓ Cache table "{table_name}" exists'))
        # SECURITY FIX: Use SQL identifier escaping to prevent SQL injection
        quoted_table = connection.ops.quote_name(table_name)
        cursor.execute(f"SELECT COUNT(*) FROM {quoted_table}")
        count = cursor.fetchone()[0]
        self.stdout.write(f"   Cache entries: {count}")

    def _show_cache_table_missing(self, table_name):
        """Show error for missing cache table."""
        self.stdout.write(
            self.style.ERROR(f'   ✗ Cache table "{table_name}" does not exist')
        )
        self.stdout.write(
            self.style.WARNING("   Run: python manage.py createcachetable")
        )

    def _check_environment_variables(self):
        """Phase 6: Check cache-related environment variables."""
        self.stdout.write("\n6. Cache-related Environment Variables:")
        cache_vars = [
            "REDIS_URL",
            "CACHE_URL",
            "CELERY_BROKER_URL",
            "CELERY_RESULT_BACKEND",
        ]
        for var in cache_vars:
            value = getattr(settings, var, None) or "Not set"
            masked_value = self._mask_sensitive_url(value)
            self.stdout.write(f"   {var}: {masked_value}")

    def _mask_sensitive_url(self, value):
        """Mask sensitive parts of URLs."""
        if value and value != "Not set" and "://" in str(value):
            parts = str(value).split("@")
            if len(parts) > 1:
                return parts[0].split("://")[0] + "://***@" + parts[1]
        return value

    def handle(self, *args, **options):
        """Orchestrate cache diagnostic phases."""
        self.stdout.write(self.style.SUCCESS("=== Cache Configuration Check ===\n"))

        # Phase 1: Cache backend settings
        cache_config = self._check_cache_backend_settings()

        # Phase 2: Default cache instance
        self._check_default_cache_instance()

        # Phase 3: Redis connection test
        self._test_redis_connection()

        # Phase 4: Cache operations test
        self._test_cache_operations()

        # Phase 5: Database cache table check
        self._check_database_cache_table(cache_config)

        # Phase 6: Environment variables check
        self._check_environment_variables()

        self.stdout.write(self.style.SUCCESS("\n=== Check Complete ==="))
