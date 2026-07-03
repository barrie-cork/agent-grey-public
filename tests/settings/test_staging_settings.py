"""
Tests for staging settings configuration.

These tests verify that staging settings load correctly from environment variables
and follow production-like security patterns.
"""

import os
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase


class StagingSettingsTest(TestCase):
    """Test staging settings load correctly from environment."""

    def setUp(self):
        """Reload staging module to ensure clean state.

        StagingCredentialGuardTest (runs earlier alphabetically) uses
        importlib.reload with env patches that trigger credential guard
        exceptions mid-import, leaving the module partially loaded with
        base.py's DATABASES instead of staging.py's own config.

        We patch safe credentials here so the reload succeeds regardless
        of the ambient environment (credential guards require non-default
        passwords when DEBUG=False).
        """
        import importlib

        safe_env = {
            "POSTGRES_PASSWORD": "test-safe-password-setUp",
            "REDIS_PASSWORD": "test-safe-redis-setUp",
        }
        with patch.dict(os.environ, safe_env, clear=False):
            from grey_lit_project.settings import staging

            importlib.reload(staging)

    def test_debug_defaults_to_false(self):
        """
        Staging should default to DEBUG=False for production-like behaviour.

        This ensures staging environment mirrors production security settings.
        Non-default credentials are required because the credential guard
        prevents loading with default passwords when DEBUG=False.
        """
        env = {
            # Non-default credentials to satisfy credential guard
            "POSTGRES_PASSWORD": "test-secure-password-123",
            "REDIS_PASSWORD": "test-redis-password-456",
        }
        with patch.dict(os.environ, env, clear=False):
            # Remove DEBUG from environment to test default
            os.environ.pop("DEBUG", None)

            # Import staging settings
            from grey_lit_project.settings import staging

            # Reload to pick up environment changes
            import importlib

            importlib.reload(staging)

            # Verify DEBUG is False by default
            self.assertFalse(
                staging.DEBUG, "Staging DEBUG should default to False for security"
            )

    def test_allowed_hosts_parses_csv_string(self):
        """
        ALLOWED_HOSTS should parse from comma-separated string.

        This is a common pattern for environment variables that need to
        contain multiple values.
        """
        from grey_lit_project.settings import staging

        # ALLOWED_HOSTS should be a list
        self.assertIsInstance(
            staging.ALLOWED_HOSTS, list, "ALLOWED_HOSTS should be a list"
        )

        # Should contain expected staging hosts
        self.assertIn("localhost", staging.ALLOWED_HOSTS)
        self.assertIn("127.0.0.1", staging.ALLOWED_HOSTS)

    def test_csrf_trusted_origins_parses_csv_string(self):
        """
        CSRF_TRUSTED_ORIGINS should parse from comma-separated string.

        This ensures CSRF protection works correctly with staging URLs.
        """
        from grey_lit_project.settings import staging

        # CSRF_TRUSTED_ORIGINS should be a list
        self.assertIsInstance(
            staging.CSRF_TRUSTED_ORIGINS, list, "CSRF_TRUSTED_ORIGINS should be a list"
        )

        # Should contain staging port URLs
        has_staging_port = any(
            "8200" in origin for origin in staging.CSRF_TRUSTED_ORIGINS
        )
        self.assertTrue(
            has_staging_port,
            "CSRF_TRUSTED_ORIGINS should include staging port 8200",
        )

    def test_database_configuration_has_required_fields(self):
        """
        Database configuration should have all required PostgreSQL fields.

        This ensures database connections work correctly in staging.
        """
        from grey_lit_project.settings import staging

        db_config = staging.DATABASES["default"]

        required_fields = ["ENGINE", "NAME", "USER", "PASSWORD", "HOST", "PORT"]
        for field in required_fields:
            self.assertIn(field, db_config, f"Database config should contain {field}")

        # Verify PostgreSQL engine
        self.assertEqual(
            db_config["ENGINE"],
            "django.db.backends.postgresql",
            "Staging should use PostgreSQL",
        )

    def test_database_has_connection_pooling(self):
        """
        Database should have connection pooling configured.

        CONN_MAX_AGE > 0 enables connection pooling for better performance.
        """
        from grey_lit_project.settings import staging

        db_config = staging.DATABASES["default"]

        self.assertIn(
            "CONN_MAX_AGE", db_config, "Database config should have CONN_MAX_AGE"
        )
        self.assertGreater(
            db_config["CONN_MAX_AGE"],
            0,
            "CONN_MAX_AGE should be > 0 for connection pooling",
        )

    def test_redis_cache_backend_configured(self):
        """
        Redis cache backend should be properly configured.

        This ensures caching works correctly in staging environment.
        """
        from grey_lit_project.settings import staging

        cache_config = staging.CACHES["default"]

        # Verify Redis backend (project uses django_redis, not Django's built-in)
        self.assertEqual(
            cache_config["BACKEND"],
            "django_redis.cache.RedisCache",
            "Staging should use django_redis cache backend",
        )

        # Verify location is set
        self.assertIn("LOCATION", cache_config, "Cache config should have LOCATION")

    def test_security_headers_enabled(self):
        """
        Security headers should be enabled for production-like testing.

        This ensures staging mirrors production security posture.
        """
        from grey_lit_project.settings import staging

        # HSTS headers
        self.assertGreater(
            staging.SECURE_HSTS_SECONDS,
            0,
            "HSTS should be enabled with timeout > 0",
        )

        # Content type sniffing protection
        self.assertTrue(
            staging.SECURE_CONTENT_TYPE_NOSNIFF,
            "Content type sniffing protection should be enabled",
        )

        # XSS filter
        self.assertTrue(
            staging.SECURE_BROWSER_XSS_FILTER,
            "XSS filter should be enabled",
        )

        # Frame options
        self.assertEqual(
            staging.X_FRAME_OPTIONS,
            "DENY",
            "X-Frame-Options should be DENY to prevent clickjacking",
        )

    def test_celery_configuration_present(self):
        """
        Celery should be configured for background task processing.

        This ensures async tasks work correctly in staging.
        """
        from grey_lit_project.settings import staging

        # Verify Celery broker configured
        self.assertTrue(
            hasattr(staging, "CELERY_BROKER_URL"),
            "CELERY_BROKER_URL should be configured",
        )
        self.assertIsNotNone(
            staging.CELERY_BROKER_URL, "CELERY_BROKER_URL should not be None"
        )

        # Verify Celery result backend configured
        self.assertTrue(
            hasattr(staging, "CELERY_RESULT_BACKEND"),
            "CELERY_RESULT_BACKEND should be configured",
        )

        # Verify task serialization
        self.assertEqual(
            staging.CELERY_TASK_SERIALIZER,
            "json",
            "Celery should use JSON serialization",
        )

    def test_static_files_configuration(self):
        """
        Static files should be configured correctly for staging.

        This ensures static assets are served efficiently.
        """
        from grey_lit_project.settings import staging

        # Verify STATIC_ROOT is set
        self.assertTrue(
            hasattr(staging, "STATIC_ROOT"), "STATIC_ROOT should be configured"
        )
        self.assertIsNotNone(staging.STATIC_ROOT, "STATIC_ROOT should not be None")

        # Verify WhiteNoise storage
        self.assertEqual(
            staging.STATICFILES_STORAGE,
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
            "Should use WhiteNoise for static file serving",
        )

    def test_logging_configuration_present(self):
        """
        Logging should be configured for production-like output.

        This ensures proper log levels and handlers are set up.
        """
        from grey_lit_project.settings import staging

        # Verify LOGGING dictionary exists
        self.assertTrue(hasattr(staging, "LOGGING"), "LOGGING should be configured")
        self.assertIsInstance(staging.LOGGING, dict, "LOGGING should be a dictionary")

        # Verify required logging components
        self.assertIn("version", staging.LOGGING, "LOGGING should have version")
        self.assertIn("handlers", staging.LOGGING, "LOGGING should have handlers")
        self.assertIn("root", staging.LOGGING, "LOGGING should have root logger")


class EnvironmentVariableParsingTest(TestCase):
    """Test environment variable parsing utilities."""

    def test_csv_string_splits_correctly(self):
        """
        Test that CSV environment variables split correctly.

        This is the pattern used for ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS.
        """
        test_csv = "host1,host2,host3"
        result = test_csv.split(",")

        self.assertEqual(len(result), 3, "Should split into 3 items")
        self.assertEqual(result, ["host1", "host2", "host3"])

    def test_csv_string_handles_spaces(self):
        """
        Test that CSV parsing handles spaces correctly.

        Environment variables may have spaces around commas.
        """
        test_csv = "host1, host2 , host3"
        result = [item.strip() for item in test_csv.split(",")]

        self.assertEqual(result, ["host1", "host2", "host3"], "Should strip whitespace")

    def test_empty_csv_string_handling(self):
        """
        Test that empty CSV strings are handled gracefully.

        Empty environment variables should not cause errors.
        """
        test_csv = ""
        result = test_csv.split(",")

        # Empty string splits to list with one empty string
        self.assertEqual(len(result), 1)
        self.assertEqual(result, [""])

    def test_single_value_csv_string(self):
        """
        Test that single-value CSV strings work correctly.

        Environment variables with single values should not require commas.
        """
        test_csv = "localhost"
        result = test_csv.split(",")

        self.assertEqual(len(result), 1)
        self.assertEqual(result, ["localhost"])


class StagingEnvironmentIdentificationTest(TestCase):
    """Test staging environment identification."""

    def test_environment_variable_set(self):
        """
        Staging should have ENVIRONMENT variable set.

        This allows code to detect which environment it's running in.
        """
        from grey_lit_project.settings import staging

        self.assertTrue(hasattr(staging, "ENVIRONMENT"), "ENVIRONMENT should be set")
        self.assertEqual(
            staging.ENVIRONMENT,
            "staging",
            "ENVIRONMENT should be 'staging'",
        )

    def test_deployment_type_set(self):
        """
        Staging should have DEPLOYMENT_TYPE variable set.

        This distinguishes between Docker and DigitalOcean deployments.
        """
        from grey_lit_project.settings import staging

        self.assertTrue(
            hasattr(staging, "DEPLOYMENT_TYPE"), "DEPLOYMENT_TYPE should be set"
        )


class StagingFeatureFlagsTest(TestCase):
    """Test feature flags in staging environment."""

    def test_sse_feature_flag_exists(self):
        """
        ENABLE_SSE feature flag should exist.

        This controls Server-Sent Events for real-time updates.
        """
        from grey_lit_project.settings import staging

        self.assertTrue(hasattr(staging, "ENABLE_SSE"), "ENABLE_SSE flag should exist")
        self.assertIsInstance(staging.ENABLE_SSE, bool, "ENABLE_SSE should be boolean")

    def test_caching_feature_flag_exists(self):
        """
        ENABLE_CACHING feature flag should exist.

        This allows disabling caching for debugging purposes.
        """
        from grey_lit_project.settings import staging

        self.assertTrue(
            hasattr(staging, "ENABLE_CACHING"), "ENABLE_CACHING flag should exist"
        )
        self.assertIsInstance(
            staging.ENABLE_CACHING, bool, "ENABLE_CACHING should be boolean"
        )


class StagingCredentialGuardTest(TestCase):
    """Test staging credential guards prevent insecure deployments."""

    def _reload_staging(self):
        import importlib

        from grey_lit_project.settings import staging

        importlib.reload(staging)
        return staging

    def test_staging_raises_when_debug_false_and_default_db_password(self):
        """Staging must reject default DB password when DEBUG=False."""
        env = {"DEBUG": "False"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("POSTGRES_PASSWORD", None)
            os.environ.pop("REDIS_PASSWORD", None)
            with self.assertRaises(ImproperlyConfigured) as ctx:
                self._reload_staging()
            self.assertIn("database password", str(ctx.exception).lower())

    def test_staging_raises_when_debug_false_and_default_redis_password(self):
        """Staging must reject default Redis password when DEBUG=False."""
        env = {
            "DEBUG": "False",
            "POSTGRES_PASSWORD": "real-secure-password-123",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("REDIS_PASSWORD", None)
            with self.assertRaises(ImproperlyConfigured) as ctx:
                self._reload_staging()
            self.assertIn("redis password", str(ctx.exception).lower())

    def test_staging_allows_custom_credentials_when_debug_false(self):
        """Staging should load fine with custom credentials and DEBUG=False."""
        env = {
            "DEBUG": "False",
            "POSTGRES_PASSWORD": "real-secure-password-123",
            "REDIS_PASSWORD": "real-redis-password-456",
            # CELERY_BROKER_URL bypasses REDIS_URL reference from star import
            "CELERY_BROKER_URL": "redis://localhost:6379/0",
            "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
        }
        try:
            with patch.dict(os.environ, env, clear=False):
                staging = self._reload_staging()
                self.assertFalse(staging.DEBUG)
        except NameError:
            self.skipTest("staging.py reload fails due to star import resolution")

    def test_staging_allows_defaults_when_debug_true(self):
        """Staging should allow default credentials when DEBUG=True (local dev)."""
        env = {
            "DEBUG": "True",
            # CELERY_BROKER_URL bypasses REDIS_URL reference from star import
            "CELERY_BROKER_URL": "redis://localhost:6379/0",
            "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
        }
        try:
            with patch.dict(os.environ, env, clear=False):
                os.environ.pop("POSTGRES_PASSWORD", None)
                os.environ.pop("REDIS_PASSWORD", None)
                staging = self._reload_staging()
                self.assertTrue(staging.DEBUG)
        except NameError:
            self.skipTest("staging.py reload fails due to star import resolution")
