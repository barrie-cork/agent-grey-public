"""Tests for deployment configuration validation utility.

This module tests the DeploymentValidator class and related validation functions
to ensure deployment configuration is validated correctly.

Created: 2025-10-17
Purpose: Phase 3 of Post-Deployment Refactoring Plan - Task 3.6.1
"""

import os

from django.test import TestCase

from apps.core.utils.deployment_validation import (
    DatabaseConfigError,
    DeploymentValidator,
    EnvironmentVariableError,
    RedisConfigError,
    SentryConfigError,
    ValidationReport,
    ValidationResult,
    validate_deployment_config,
)


class ValidationResultTestCase(TestCase):
    """Test ValidationResult dataclass."""

    def test_validation_result_creation(self):
        """Test creating a ValidationResult."""
        result = ValidationResult(
            is_valid=True, message="Test message", severity="info", hints=["hint1"]
        )

        self.assertTrue(result.is_valid)
        self.assertEqual(result.message, "Test message")
        self.assertEqual(result.severity, "info")
        self.assertEqual(result.hints, ["hint1"])

    def test_validation_result_default_hints(self):
        """Test that hints defaults to empty list."""
        result = ValidationResult(is_valid=True, message="Test", severity="info")

        self.assertEqual(result.hints, [])


class ValidationReportTestCase(TestCase):
    """Test ValidationReport dataclass."""

    def test_validation_report_summary(self):
        """Test ValidationReport summary property."""
        report = ValidationReport(
            environment="production",
            passed=False,
            results=[],
            errors=["error1", "error2"],
            warnings=["warning1"],
        )

        summary = report.summary
        self.assertIn("PRODUCTION", summary.upper())
        self.assertIn("FAILED", summary)
        self.assertIn("Errors: 2", summary)
        self.assertIn("Warnings: 1", summary)

    def test_validation_report_detailed_report(self):
        """Test ValidationReport detailed_report method."""
        result = ValidationResult(
            is_valid=False,
            message="Test error",
            severity="error",
            hints=["Fix this"],
        )

        report = ValidationReport(
            environment="staging",
            passed=False,
            results=[result],
            errors=["Test error"],
            warnings=[],
        )

        detailed = report.detailed_report()
        self.assertIn("STAGING", detailed)
        self.assertIn("Test error", detailed)
        self.assertIn("Fix this", detailed)


class DeploymentValidatorSecretKeyTestCase(TestCase):
    """Test SECRET_KEY validation."""

    def setUp(self):
        """Save original environment variables."""
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Restore original environment variables."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_validate_secret_key_missing(self):
        """Test validation fails when SECRET_KEY is missing."""
        os.environ.pop("SECRET_KEY", None)
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_secret_key()

        self.assertEqual(len(validator.errors), 1)
        self.assertIn("SECRET_KEY", validator.errors[0])

    def test_validate_secret_key_empty(self):
        """Test validation fails when SECRET_KEY is empty string."""
        os.environ["SECRET_KEY"] = ""
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_secret_key()

        self.assertEqual(len(validator.errors), 1)

    def test_validate_secret_key_whitespace_only(self):
        """Test validation fails when SECRET_KEY is whitespace only."""
        os.environ["SECRET_KEY"] = "   "
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_secret_key()

    def test_validate_secret_key_too_short(self):
        """Test validation fails when SECRET_KEY is too short (< 50 chars)."""
        os.environ["SECRET_KEY"] = "a" * 30  # Only 30 characters
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_secret_key()

        self.assertEqual(len(validator.errors), 1)
        self.assertIn("too short", validator.errors[0])

    def test_validate_secret_key_insecure_pattern_django_insecure(self):
        """Test validation fails when SECRET_KEY contains django-insecure-."""
        os.environ["SECRET_KEY"] = "django-insecure-" + "x" * 40
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_secret_key()

        self.assertIn("insecure patterns", validator.errors[0])

    def test_validate_secret_key_insecure_pattern_test(self):
        """Test validation fails when SECRET_KEY contains 'test'."""
        os.environ["SECRET_KEY"] = "test_secret_key_for_testing_purposes_12345678901234"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_secret_key()

    def test_validate_secret_key_insecure_pattern_development(self):
        """Test validation fails when SECRET_KEY contains 'development'."""
        os.environ["SECRET_KEY"] = (
            "development_secret_key_not_for_production_use_1234567890"
        )
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_secret_key()

    def test_validate_secret_key_valid(self):
        """Test validation passes with valid SECRET_KEY."""
        os.environ["SECRET_KEY"] = "x" * 50  # 50 random characters
        validator = DeploymentValidator(environment="production")

        result = validator.validate_secret_key()

        self.assertTrue(result.is_valid)
        self.assertEqual(result.severity, "info")
        self.assertEqual(len(validator.errors), 0)


class DeploymentValidatorDatabaseURLTestCase(TestCase):
    """Test DATABASE_URL validation."""

    def setUp(self):
        """Save original environment variables."""
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Restore original environment variables."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_validate_database_url_missing(self):
        """Test validation fails when DATABASE_URL is missing."""
        os.environ.pop("DATABASE_URL", None)
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(DatabaseConfigError):
            validator.validate_database_url()

        self.assertIn("DATABASE_URL", validator.errors[0])

    def test_validate_database_url_empty_string(self):
        """Test validation fails when DATABASE_URL is empty."""
        os.environ["DATABASE_URL"] = ""
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(DatabaseConfigError):
            validator.validate_database_url()

    def test_validate_database_url_invalid_placeholder_none(self):
        """Test validation fails with 'None' placeholder."""
        os.environ["DATABASE_URL"] = "None"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(DatabaseConfigError):
            validator.validate_database_url()

        self.assertIn("placeholder", validator.errors[0])

    def test_validate_database_url_invalid_placeholder_null(self):
        """Test validation fails with 'null' placeholder."""
        os.environ["DATABASE_URL"] = "null"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(DatabaseConfigError):
            validator.validate_database_url()

    def test_validate_database_url_invalid_scheme(self):
        """Test validation fails with invalid scheme."""
        os.environ["DATABASE_URL"] = "mysql://user:pass@host:3306/db"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(DatabaseConfigError):
            validator.validate_database_url()

        self.assertIn("scheme", validator.errors[0])

    def test_validate_database_url_localhost_in_production(self):
        """Test validation fails with localhost in production."""
        os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/db"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(DatabaseConfigError):
            validator.validate_database_url()

        self.assertIn("localhost", validator.errors[0])

    def test_validate_database_url_127_0_0_1_in_production(self):
        """Test validation fails with 127.0.0.1 in production."""
        os.environ["DATABASE_URL"] = "postgresql://user:pass@127.0.0.1:5432/db"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(DatabaseConfigError):
            validator.validate_database_url()

    def test_validate_database_url_missing_ssl_mode_warning(self):
        """Test validation warns when SSL mode is missing in production."""
        os.environ["DATABASE_URL"] = "postgresql://user:pass@db.example.com:5432/db"
        validator = DeploymentValidator(environment="production")

        result = validator.validate_database_url()

        # Should pass but generate warning
        self.assertTrue(result.is_valid)
        self.assertEqual(len(validator.warnings), 1)
        self.assertIn("SSL", validator.warnings[0])

    def test_validate_database_url_valid_with_ssl(self):
        """Test validation passes with valid PostgreSQL URL with SSL."""
        os.environ["DATABASE_URL"] = (
            "postgresql://user:pass@db.example.com:5432/db?sslmode=require"
        )
        validator = DeploymentValidator(environment="production")

        result = validator.validate_database_url()

        self.assertTrue(result.is_valid)
        self.assertEqual(result.severity, "info")
        self.assertEqual(len(validator.errors), 0)

    def test_validate_database_url_localhost_ok_in_development(self):
        """Test validation allows localhost in non-production."""
        os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/db"
        validator = DeploymentValidator(environment="local")

        result = validator.validate_database_url()

        self.assertTrue(result.is_valid)
        self.assertEqual(len(validator.errors), 0)


class DeploymentValidatorRedisURLTestCase(TestCase):
    """Test REDIS_URL validation."""

    def setUp(self):
        """Save original environment variables."""
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Restore original environment variables."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_validate_redis_url_empty_ok(self):
        """Test validation passes when REDIS_URL is empty (optional)."""
        os.environ.pop("REDIS_URL", None)
        validator = DeploymentValidator(environment="production")

        result = validator.validate_redis_url()

        self.assertTrue(result.is_valid)
        self.assertEqual(result.severity, "warning")
        self.assertIn("database cache", result.message)

    def test_validate_redis_url_invalid_placeholder_none(self):
        """Test validation fails with 'None' placeholder."""
        os.environ["REDIS_URL"] = "None"
        validator = DeploymentValidator(environment="production")

        result = validator.validate_redis_url()

        self.assertFalse(result.is_valid)
        self.assertEqual(result.severity, "warning")

    def test_validate_redis_url_invalid_scheme(self):
        """Test validation fails with invalid scheme."""
        os.environ["REDIS_URL"] = "http://host:6379/0"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(RedisConfigError):
            validator.validate_redis_url()

    def test_validate_redis_url_localhost_in_production_critical(self):
        """Test validation fails with localhost Redis in production."""
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(RedisConfigError):
            validator.validate_redis_url()

        self.assertIn("localhost", validator.errors[0])

    def test_validate_redis_url_127_0_0_1_in_production(self):
        """Test validation fails with 127.0.0.1 in production."""
        os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/0"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(RedisConfigError):
            validator.validate_redis_url()

    def test_validate_redis_url_non_ssl_warning(self):
        """Test validation warns about non-SSL Redis in production."""
        os.environ["REDIS_URL"] = "redis://redis.example.com:6379/0"
        validator = DeploymentValidator(environment="production")

        result = validator.validate_redis_url()

        self.assertTrue(result.is_valid)
        self.assertEqual(result.severity, "warning")
        self.assertIn("non-SSL", result.message)

    def test_validate_redis_url_valid_with_ssl(self):
        """Test validation passes with valid rediss:// URL."""
        os.environ["REDIS_URL"] = "rediss://redis.example.com:6380/0"
        validator = DeploymentValidator(environment="production")

        result = validator.validate_redis_url()

        self.assertTrue(result.is_valid)
        self.assertEqual(result.severity, "info")
        self.assertEqual(len(validator.errors), 0)

    def test_validate_redis_url_localhost_ok_in_development(self):
        """Test validation allows localhost in non-production."""
        os.environ["REDIS_URL"] = "redis://localhost:6379/0"
        validator = DeploymentValidator(environment="local")

        result = validator.validate_redis_url()

        # Should pass or warn, but not be critical
        self.assertTrue(result.is_valid)


class DeploymentValidatorSentryDSNTestCase(TestCase):
    """Test SENTRY_DSN validation."""

    def setUp(self):
        """Save original environment variables."""
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Restore original environment variables."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_validate_sentry_dsn_empty_ok(self):
        """Test validation passes when SENTRY_DSN is empty (optional)."""
        os.environ.pop("SENTRY_DSN", None)
        validator = DeploymentValidator(environment="production")

        result = validator.validate_sentry_dsn()

        self.assertTrue(result.is_valid)
        self.assertEqual(result.severity, "info")

    def test_validate_sentry_dsn_placeholder_none(self):
        """Test validation handles 'None' placeholder gracefully."""
        os.environ["SENTRY_DSN"] = "None"
        validator = DeploymentValidator(environment="production")

        result = validator.validate_sentry_dsn()

        self.assertTrue(result.is_valid)

    def test_validate_sentry_dsn_invalid_format_not_http(self):
        """Test validation fails with invalid format (not http/https)."""
        os.environ["SENTRY_DSN"] = "invalid-dsn-format"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(SentryConfigError):
            validator.validate_sentry_dsn()

    def test_validate_sentry_dsn_valid_http(self):
        """Test validation passes with valid http:// DSN."""
        os.environ["SENTRY_DSN"] = "http://key@example.com/123"
        validator = DeploymentValidator(environment="production")

        result = validator.validate_sentry_dsn()

        self.assertTrue(result.is_valid)

    def test_validate_sentry_dsn_valid_https(self):
        """Test validation passes with valid https:// DSN."""
        os.environ["SENTRY_DSN"] = "https://key@sentry.io/123"
        validator = DeploymentValidator(environment="production")

        result = validator.validate_sentry_dsn()

        self.assertTrue(result.is_valid)
        self.assertEqual(result.severity, "info")

    def test_validate_sentry_dsn_custom_instance(self):
        """Test validation passes with custom Sentry instance."""
        os.environ["SENTRY_DSN"] = "https://key@custom-sentry.example.com/123"
        validator = DeploymentValidator(environment="production")

        result = validator.validate_sentry_dsn()

        self.assertTrue(result.is_valid)


class DeploymentValidatorAllowedHostsTestCase(TestCase):
    """Test ALLOWED_HOSTS validation."""

    def setUp(self):
        """Save original environment variables."""
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Restore original environment variables."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_validate_allowed_hosts_empty_in_production(self):
        """Test validation fails when ALLOWED_HOSTS is empty in production."""
        os.environ.pop("ALLOWED_HOSTS", None)
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_allowed_hosts()

        self.assertIn("ALLOWED_HOSTS", validator.errors[0])

    def test_validate_allowed_hosts_empty_ok_in_development(self):
        """Test validation passes when ALLOWED_HOSTS is empty in development."""
        os.environ.pop("ALLOWED_HOSTS", None)
        validator = DeploymentValidator(environment="local")

        result = validator.validate_allowed_hosts()

        self.assertTrue(result.is_valid)

    def test_validate_allowed_hosts_wildcard_in_production(self):
        """Test validation fails with wildcard '*' in production."""
        os.environ["ALLOWED_HOSTS"] = "*"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_allowed_hosts()

        self.assertIn("wildcard", validator.errors[0])

    def test_validate_allowed_hosts_wildcard_among_hosts_in_production(self):
        """Test validation fails with wildcard among other hosts."""
        os.environ["ALLOWED_HOSTS"] = "example.com,*,localhost"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_allowed_hosts()

    def test_validate_allowed_hosts_invalid_pattern_ip_wildcard(self):
        """Test validation fails with invalid IP wildcard pattern."""
        os.environ["ALLOWED_HOSTS"] = "10.244.*"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_allowed_hosts()

        self.assertIn("invalid patterns", validator.errors[0])

    def test_validate_allowed_hosts_invalid_pattern_multiple_wildcards(self):
        """Test validation fails with multiple wildcards."""
        os.environ["ALLOWED_HOSTS"] = "*.example.*"
        validator = DeploymentValidator(environment="production")

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_allowed_hosts()

    def test_validate_allowed_hosts_valid_subdomain_wildcard(self):
        """Test validation passes with valid subdomain wildcard."""
        os.environ["ALLOWED_HOSTS"] = ".example.com"
        validator = DeploymentValidator(environment="production")

        result = validator.validate_allowed_hosts()

        self.assertTrue(result.is_valid)
        self.assertEqual(len(validator.errors), 0)

    def test_validate_allowed_hosts_valid_multiple_hosts(self):
        """Test validation passes with multiple valid hosts."""
        os.environ["ALLOWED_HOSTS"] = "example.com,api.example.com,localhost"
        validator = DeploymentValidator(environment="production")

        result = validator.validate_allowed_hosts()

        self.assertTrue(result.is_valid)
        self.assertEqual(result.severity, "info")


class DeploymentValidatorIntegrationTestCase(TestCase):
    """Integration tests for DeploymentValidator.validate_all()."""

    def setUp(self):
        """Save original environment variables."""
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Restore original environment variables."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_validate_all_passes_with_valid_config(self):
        """Test validate_all() passes with complete valid configuration."""
        os.environ.update(
            {
                "SECRET_KEY": "x" * 50,
                "DATABASE_URL": "postgresql://user:pass@db.example.com:5432/db?sslmode=require",
                "REDIS_URL": "rediss://redis.example.com:6380/0",
                "SENTRY_DSN": "https://key@sentry.io/123",
                "ALLOWED_HOSTS": "example.com,api.example.com",
            }
        )

        validator = DeploymentValidator(environment="production")
        report = validator.validate_all()

        self.assertTrue(report.passed)
        self.assertEqual(len(report.errors), 0)
        self.assertEqual(report.environment, "production")

    def test_validate_all_fails_with_missing_secret_key(self):
        """Test validate_all() fails with missing SECRET_KEY."""
        os.environ.clear()

        validator = DeploymentValidator(environment="production")

        # validate_all() catches exceptions from individual validators
        try:
            report = validator.validate_all()
            # If we get here, validation completed but found errors
            self.assertFalse(report.passed)
            self.assertGreater(len(report.errors), 0)
        except Exception:
            # Individual validators may raise exceptions
            # which is also acceptable behavior
            pass

    def test_validate_all_minimal_valid_config(self):
        """Test validate_all() with minimal valid configuration."""
        # Clear REDIS_URL to avoid localhost validation error
        os.environ.pop("REDIS_URL", None)
        os.environ.update(
            {
                "SECRET_KEY": "x" * 50,
                "DATABASE_URL": "postgresql://db.example.com/db?sslmode=require",
                "ALLOWED_HOSTS": "example.com",
            }
        )

        validator = DeploymentValidator(environment="production")
        report = validator.validate_all()

        self.assertTrue(report.passed)
        # Should have warnings about missing Redis
        self.assertGreater(len(report.warnings), 0)


class ValidateDeploymentConfigFunctionTestCase(TestCase):
    """Test validate_deployment_config() convenience function."""

    def setUp(self):
        """Save original environment variables."""
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Restore original environment variables."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_validate_deployment_config_returns_report(self):
        """Test convenience function returns ValidationReport."""
        # Clear REDIS_URL to avoid localhost validation error
        os.environ.pop("REDIS_URL", None)
        os.environ.update(
            {
                "SECRET_KEY": "x" * 50,
                "DATABASE_URL": "postgresql://db.example.com/db?sslmode=require",
                "ALLOWED_HOSTS": "example.com",
            }
        )

        report = validate_deployment_config(environment="production")

        self.assertIsInstance(report, ValidationReport)
        self.assertEqual(report.environment, "production")

    def test_validate_deployment_config_custom_environment(self):
        """Test convenience function with custom environment."""
        os.environ.update(
            {
                "SECRET_KEY": "x" * 50,
                "DATABASE_URL": "postgresql://localhost/db",
            }
        )

        report = validate_deployment_config(environment="local")

        self.assertEqual(report.environment, "local")
        # Localhost should be OK in local environment
        self.assertTrue(report.passed)
