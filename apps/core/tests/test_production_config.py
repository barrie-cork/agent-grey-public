"""
Tests for production environment configuration utilities.
"""

import os
import unittest.mock as mock

from django.test import TestCase

from apps.core.utils.production_config import (
    ProductionConfigError,
    get_cache_configuration,
    get_cors_and_csrf_config,
    get_database_config,
    get_logging_config,
    get_redis_config_for_digitalocean,
    parse_csv_env_var,
    validate_required_env_vars,
)


class TestParseCSVEnvVar(TestCase):
    """Test CSV environment variable parsing."""

    def test_empty_string_returns_default(self):
        """Test that empty environment variable returns default value."""
        with mock.patch.dict(os.environ, {"TEST_VAR": ""}):
            result = parse_csv_env_var("TEST_VAR", ["default"])
            self.assertEqual(result, ["default"])

    def test_missing_env_var_returns_default(self):
        """Test that missing environment variable returns default value."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = parse_csv_env_var("MISSING_VAR", ["default1", "default2"])
            self.assertEqual(result, ["default1", "default2"])

    def test_single_value_without_comma(self):
        """Test parsing single value without comma."""
        with mock.patch.dict(os.environ, {"TEST_VAR": "single"}):
            result = parse_csv_env_var("TEST_VAR")
            self.assertEqual(result, ["single"])

    def test_multiple_values_with_comma(self):
        """Test parsing multiple comma-separated values."""
        with mock.patch.dict(os.environ, {"TEST_VAR": "one,two,three"}):
            result = parse_csv_env_var("TEST_VAR")
            self.assertEqual(result, ["one", "two", "three"])

    def test_values_with_whitespace(self):
        """Test that whitespace is properly trimmed."""
        with mock.patch.dict(os.environ, {"TEST_VAR": " one , two , three "}):
            result = parse_csv_env_var("TEST_VAR")
            self.assertEqual(result, ["one", "two", "three"])

    def test_empty_values_filtered_out(self):
        """Test that empty values between commas are filtered out."""
        with mock.patch.dict(os.environ, {"TEST_VAR": "one,,three,"}):
            result = parse_csv_env_var("TEST_VAR")
            self.assertEqual(result, ["one", "three"])


class TestValidateRequiredEnvVars(TestCase):
    """Test environment variable validation."""

    def test_all_required_vars_present_and_valid(self):
        """Test validation passes when all required variables are set correctly."""
        with mock.patch.dict(
            os.environ,
            {
                "SECRET_KEY": "a" * 32,  # Minimum 32 characters
                "DATABASE_URL": "postgres://user:pass@localhost/db",
            },
        ):
            result = validate_required_env_vars()
            self.assertTrue(result["valid"])
            self.assertEqual(len(result["errors"]), 0)

    def test_missing_required_variable(self):
        """Test validation fails when required variables are missing."""
        with mock.patch.dict(os.environ, {}, clear=True):
            result = validate_required_env_vars()
            self.assertFalse(result["valid"])
            self.assertTrue(any("SECRET_KEY" in error for error in result["errors"]))
            self.assertTrue(any("DATABASE_URL" in error for error in result["errors"]))

    def test_secret_key_too_short(self):
        """Test validation fails when SECRET_KEY is too short."""
        with mock.patch.dict(
            os.environ,
            {
                "SECRET_KEY": "short",
                "DATABASE_URL": "postgres://user:pass@localhost/db",
            },
        ):
            result = validate_required_env_vars()
            self.assertFalse(result["valid"])
            self.assertTrue(
                any("at least 32 characters" in error for error in result["errors"])
            )

    def test_invalid_url_format_warning(self):
        """Test that invalid URL format generates warning."""
        with mock.patch.dict(
            os.environ,
            {
                "SECRET_KEY": "a" * 32,
                "DATABASE_URL": "postgres://user:pass@localhost/db",  # Valid URL
                "SENTRY_DSN": "not-a-url",  # Invalid URL (optional field)
            },
        ):
            result = validate_required_env_vars()
            # Should be valid since DATABASE_URL is valid and SENTRY_DSN is optional
            self.assertTrue(result["valid"])
            # SENTRY_DSN should generate a warning
            self.assertTrue(
                any("SENTRY_DSN" in warning for warning in result["warnings"])
            )

    def test_optional_variables_not_required(self):
        """Test that optional variables don't cause validation failure."""
        with mock.patch.dict(
            os.environ,
            {
                "SECRET_KEY": "a" * 32,
                "DATABASE_URL": "postgres://user:pass@localhost/db",
                # No ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, or SENTRY_DSN
            },
        ):
            result = validate_required_env_vars()
            self.assertTrue(result["valid"])


class TestRedisConfigForDigitalOcean(TestCase):
    """Test Redis configuration for DigitalOcean."""

    def test_no_redis_url_disables_redis(self):
        """Test that missing REDIS_URL disables Redis."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = get_redis_config_for_digitalocean()
            self.assertFalse(config["enabled"])
            self.assertEqual(config["reason"], "no_redis_url")
            self.assertIn("DatabaseCache", config["backend"])

    def test_ssl_redis_url_for_digitalocean(self):
        """Test SSL Redis URL configuration for DigitalOcean Managed Redis."""
        with mock.patch.dict(
            os.environ, {"REDIS_URL": "rediss://user:pass@host:6380/0"}
        ):
            config = get_redis_config_for_digitalocean()
            self.assertTrue(config["enabled"])
            self.assertEqual(config["reason"], "digitalocean_ssl_redis")
            self.assertIn("RedisCache", config["backend"])
            self.assertIsNone(
                config["options"]["CONNECTION_POOL_KWARGS"]["ssl_cert_reqs"]
            )
            self.assertFalse(
                config["options"]["CONNECTION_POOL_KWARGS"]["ssl_check_hostname"]
            )

    def test_standard_redis_url(self):
        """Test standard Redis URL configuration."""
        with mock.patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            config = get_redis_config_for_digitalocean()
            self.assertTrue(config["enabled"])
            self.assertEqual(config["reason"], "standard_redis")
            self.assertIn("RedisCache", config["backend"])
            self.assertNotIn(
                "ssl_cert_reqs", config["options"]["CONNECTION_POOL_KWARGS"]
            )

    def test_invalid_redis_url_scheme(self):
        """Test invalid Redis URL scheme disables Redis."""
        with mock.patch.dict(os.environ, {"REDIS_URL": "invalid://host:6379/0"}):
            config = get_redis_config_for_digitalocean()
            self.assertFalse(config["enabled"])
            self.assertEqual(config["reason"], "invalid_redis_url")


class TestCacheConfiguration(TestCase):
    """Test cache configuration generation."""

    def test_skip_redis_config_uses_database_cache(self):
        """Test that SKIP_REDIS_CONFIG forces database cache."""
        with mock.patch.dict(os.environ, {"SKIP_REDIS_CONFIG": "true"}):
            config = get_cache_configuration()
            self.assertIn("DatabaseCache", config["default"]["BACKEND"])
            self.assertEqual(config["default"]["LOCATION"], "django_cache_table")

    def test_redis_enabled_when_available(self):
        """Test Redis cache configuration when Redis URL is valid."""
        with mock.patch.dict(
            os.environ,
            {"REDIS_URL": "redis://localhost:6379/0", "SKIP_REDIS_CONFIG": "false"},
        ):
            config = get_cache_configuration()
            self.assertIn("RedisCache", config["default"]["BACKEND"])

    def test_fallback_to_database_when_redis_unavailable(self):
        """Test fallback to database cache when Redis is not available."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = get_cache_configuration()
            self.assertIn("DatabaseCache", config["default"]["BACKEND"])

    def test_cache_timeout_configuration(self):
        """Test that cache timeout is properly configured."""
        with mock.patch.dict(os.environ, {"SKIP_REDIS_CONFIG": "true"}):
            config = get_cache_configuration()
            self.assertEqual(config["default"]["TIMEOUT"], 3600)


class TestCORSAndCSRFConfig(TestCase):
    """Test CORS and CSRF configuration."""

    def test_default_allowed_hosts(self):
        """Test default ALLOWED_HOSTS when not specified."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = get_cors_and_csrf_config()
            self.assertIn("localhost", config["ALLOWED_HOSTS"])
            self.assertIn("127.0.0.1", config["ALLOWED_HOSTS"])

    def test_parse_allowed_hosts_from_env(self):
        """Test parsing ALLOWED_HOSTS from environment."""
        with mock.patch.dict(
            os.environ, {"ALLOWED_HOSTS": "example.com,api.example.com"}
        ):
            config = get_cors_and_csrf_config()
            self.assertEqual(
                config["ALLOWED_HOSTS"], ["example.com", "api.example.com"]
            )

    def test_parse_csrf_trusted_origins(self):
        """Test parsing CSRF_TRUSTED_ORIGINS from environment."""
        with mock.patch.dict(
            os.environ,
            {"CSRF_TRUSTED_ORIGINS": "https://example.com,https://api.example.com"},
        ):
            config = get_cors_and_csrf_config()
            self.assertEqual(
                config["CSRF_TRUSTED_ORIGINS"],
                ["https://example.com", "https://api.example.com"],
            )

    def test_auto_generate_csrf_origins_from_allowed_hosts(self):
        """Test auto-generation of CSRF origins from ALLOWED_HOSTS."""
        with mock.patch.dict(os.environ, {"ALLOWED_HOSTS": "example.com"}, clear=True):
            config = get_cors_and_csrf_config()
            self.assertIn("https://example.com", config["CSRF_TRUSTED_ORIGINS"])
            self.assertIn("http://example.com", config["CSRF_TRUSTED_ORIGINS"])

    def test_security_settings_enabled(self):
        """Test that security settings are enabled in production."""
        config = get_cors_and_csrf_config()
        self.assertTrue(config["CORS_ALLOW_CREDENTIALS"])
        self.assertTrue(config["CSRF_COOKIE_SECURE"])
        self.assertTrue(config["SESSION_COOKIE_SECURE"])


class TestDatabaseConfig(TestCase):
    """Test database configuration."""

    def test_missing_database_url_raises_error(self):
        """Test that missing DATABASE_URL raises ProductionConfigError."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProductionConfigError) as context:
                get_database_config()
            self.assertIn("DATABASE_URL", str(context.exception))

    @mock.patch("dj_database_url.parse")
    def test_database_config_with_digitalocean_optimizations(self, mock_parse):
        """Test database configuration includes DigitalOcean optimizations."""
        mock_parse.return_value = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "test_db",
            "USER": "test_user",
            "PASSWORD": "test_pass",
            "HOST": "localhost",
            "PORT": 5432,
        }

        with mock.patch.dict(
            os.environ,
            {"DATABASE_URL": "postgres://test_user:test_pass@localhost:5432/test_db"},
        ):
            config = get_database_config()
            self.assertIn("default", config)
            self.assertEqual(config["default"]["CONN_MAX_AGE"], 600)
            self.assertEqual(config["default"]["OPTIONS"]["sslmode"], "require")
            self.assertEqual(config["default"]["OPTIONS"]["connect_timeout"], 30)

    @mock.patch("dj_database_url.parse")
    def test_invalid_database_url_raises_error(self, mock_parse):
        """Test that invalid DATABASE_URL raises ProductionConfigError."""
        mock_parse.side_effect = Exception("Invalid URL")

        with mock.patch.dict(os.environ, {"DATABASE_URL": "invalid-url"}):
            with self.assertRaises(ProductionConfigError) as context:
                get_database_config()
            self.assertIn("Invalid DATABASE_URL", str(context.exception))


class TestLoggingConfig(TestCase):
    """Test logging configuration."""

    def test_default_log_level(self):
        """Test default log level is INFO."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = get_logging_config()
            self.assertEqual(config["root"]["level"], "INFO")
            self.assertEqual(config["loggers"]["django"]["level"], "INFO")

    def test_custom_log_level_from_env(self):
        """Test custom log level from environment variable."""
        with mock.patch.dict(os.environ, {"DJANGO_LOG_LEVEL": "DEBUG"}):
            config = get_logging_config()
            self.assertEqual(config["root"]["level"], "DEBUG")
            self.assertEqual(config["loggers"]["django"]["level"], "DEBUG")

    def test_logging_handlers_configured(self):
        """Test that logging handlers are properly configured."""
        config = get_logging_config()
        self.assertIn("console", config["handlers"])
        self.assertIn("file", config["handlers"])
        self.assertEqual(
            config["handlers"]["console"]["class"], "logging.StreamHandler"
        )
        self.assertEqual(
            config["handlers"]["file"]["class"], "logging.handlers.RotatingFileHandler"
        )

    def test_json_formatter_for_file_handler(self):
        """Test that file handler uses JSON formatter."""
        config = get_logging_config()
        self.assertIn("json", config["formatters"])
        self.assertEqual(
            config["formatters"]["json"]["()"],
            "pythonjsonlogger.jsonlogger.JsonFormatter",
        )


class TestIntegration(TestCase):
    """Integration tests for production configuration."""

    def test_full_production_environment(self):
        """Test complete production environment configuration."""
        with mock.patch.dict(
            os.environ,
            {
                "SECRET_KEY": "a" * 50,
                "DATABASE_URL": "postgres://user:pass@db.digitalocean.com:5432/proddb",
                "REDIS_URL": "rediss://default:pass@redis.digitalocean.com:25061/0",
                "ALLOWED_HOSTS": "app.example.com,api.example.com",
                "CSRF_TRUSTED_ORIGINS": "https://app.example.com,https://api.example.com",
                "SENTRY_DSN": "https://key@sentry.io/123",
                "DJANGO_LOG_LEVEL": "WARNING",
            },
        ):
            # All validations should pass
            validation = validate_required_env_vars()
            self.assertTrue(validation["valid"])

            # Redis should be configured for SSL
            redis_config = get_redis_config_for_digitalocean()
            self.assertTrue(redis_config["enabled"])
            self.assertEqual(redis_config["reason"], "digitalocean_ssl_redis")

            # Cache should use Redis
            cache_config = get_cache_configuration()
            self.assertIn("RedisCache", cache_config["default"]["BACKEND"])

            # CORS/CSRF should be configured
            cors_csrf = get_cors_and_csrf_config()
            self.assertEqual(len(cors_csrf["ALLOWED_HOSTS"]), 2)
            self.assertEqual(len(cors_csrf["CSRF_TRUSTED_ORIGINS"]), 2)

    def test_minimal_production_environment(self):
        """Test minimal viable production environment."""
        with mock.patch.dict(
            os.environ,
            {
                "SECRET_KEY": "a" * 32,
                "DATABASE_URL": "sqlite:///db.sqlite3",
                "SKIP_REDIS_CONFIG": "true",
            },
        ):
            # Should still be valid
            validation = validate_required_env_vars()
            self.assertTrue(validation["valid"])

            # Should use database cache
            cache_config = get_cache_configuration()
            self.assertIn("DatabaseCache", cache_config["default"]["BACKEND"])

    def test_digitalocean_specific_features(self):
        """Test DigitalOcean-specific configuration features."""
        with mock.patch.dict(
            os.environ,
            {
                "REDIS_URL": "rediss://user:pass@private-redis-do.com:25061/0",
                "DATABASE_URL": "postgres://user:pass@private-db-do.com:25060/defaultdb",
            },
        ):
            # Redis should detect SSL and configure accordingly
            redis_config = get_redis_config_for_digitalocean()
            self.assertTrue(redis_config["enabled"])
            self.assertIsNone(
                redis_config["options"]["CONNECTION_POOL_KWARGS"]["ssl_cert_reqs"]
            )

            # Cache should use Redis with SSL
            cache_config = get_cache_configuration()
            self.assertIn("rediss://", cache_config["default"]["LOCATION"])
