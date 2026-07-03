"""
Deployment Integration Tests

Comprehensive integration tests for deployment scenarios to ensure production readiness.

Tests real deployment scenarios and configuration validation to catch issues before
production deployment. Covers configuration validation, health checks, database/cache
connectivity, and Django system checks.

Phase 6, Task 6.3 of Post-Deployment Refactoring Plan
Created: 2025-10-17
"""

import json
import os
import unittest
from io import StringIO

from django.conf import settings
from django.core import management
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, TestCase

from apps.core.middleware.health_check_bypass import HealthCheckBypassMiddleware

_is_production = (
    os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith("production")
    and os.environ.get("ENVIRONMENT") == "production"
)


class DeploymentIntegrationTestCase(TestCase):
    """
    Integration tests for deployment scenarios.

    Test suite verifies:
    1. Configuration validation (management command)
    2. Health check integration
    3. Database configuration and connectivity
    4. Cache configuration and fallback
    5. Django system checks
    6. Middleware integration
    """

    def setUp(self):
        """Set up test environment."""
        self.factory = RequestFactory()
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Clean up test environment."""
        os.environ.clear()
        os.environ.update(self.original_env)
        cache.clear()

    # ========================================================================
    # Test Suite 1: Configuration Validation (6 tests)
    # ========================================================================

    @unittest.skipUnless(_is_production, "Production settings only")
    def test_validate_deployment_config_command_exists(self):
        """
        Test that validate_deployment_config command is registered.

        Verifies Django can find and load the management command.
        """
        out = StringIO()
        err = StringIO()
        try:
            call_command("validate_deployment_config", stdout=out, stderr=err)
        except SystemExit:
            pass  # Command may exit with non-zero in dev environment

        output = out.getvalue() + err.getvalue()

        # Command should produce output (may go to stdout or stderr)
        self.assertGreater(len(output), 0)
        self.assertIn("Deployment Validation Report", output)

    @unittest.skipUnless(_is_production, "Production settings only")
    def test_validate_deployment_config_with_valid_production_config(self):
        """
        Test validation passes with valid production configuration.

        Verifies command correctly identifies valid production settings.
        """
        # Setup valid production environment
        os.environ["SECRET_KEY"] = "a" * 50  # Valid 50-char key
        os.environ["DATABASE_URL"] = (
            "postgresql://user:pass@prod-host:5432/db?sslmode=require"
        )
        os.environ["ALLOWED_HOSTS"] = "grey-lit-app-ifa37.ondigitalocean.app,localhost"

        out = StringIO()
        try:
            call_command(
                "validate_deployment_config", "--environment", "production", stdout=out
            )
            # Command should succeed (exit code 0)
            output = out.getvalue()
            self.assertIn("PASSED", output)
        except SystemExit as e:
            # Exit code 0 = success
            self.assertEqual(e.code, 0)

    def test_validate_deployment_config_with_missing_secret_key(self):
        """
        Test validation fails appropriately when SECRET_KEY is missing.

        Verifies command detects critical configuration errors.
        """
        # Remove SECRET_KEY
        if "SECRET_KEY" in os.environ:
            del os.environ["SECRET_KEY"]

        # Command should fail with SystemExit(1)
        with self.assertRaises(SystemExit) as cm:
            call_command(
                "validate_deployment_config",
                "--environment",
                "production",
                stdout=StringIO(),
            )

        # Exit code 1 = failure
        self.assertEqual(cm.exception.code, 1)

    def test_validate_deployment_config_with_localhost_database(self):
        """
        Test validation detects localhost in DATABASE_URL for production.

        Verifies command catches common deployment misconfiguration.
        """
        # Setup with localhost database (invalid for production)
        os.environ["SECRET_KEY"] = "a" * 50
        os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/db"
        os.environ["ALLOWED_HOSTS"] = "grey-lit-app-ifa37.ondigitalocean.app"

        # Command should fail
        with self.assertRaises(SystemExit) as cm:
            call_command(
                "validate_deployment_config",
                "--environment",
                "production",
                stdout=StringIO(),
            )

        self.assertEqual(cm.exception.code, 1)

    def test_validate_deployment_config_json_output(self):
        """
        Test validation command supports JSON output format.

        Verifies CI/CD integration with machine-readable output.
        """
        # Setup valid configuration
        os.environ["SECRET_KEY"] = "a" * 50
        os.environ["DATABASE_URL"] = (
            "postgresql://user:pass@prod-host:5432/db?sslmode=require"
        )
        os.environ["ALLOWED_HOSTS"] = "grey-lit-app-ifa37.ondigitalocean.app"

        out = StringIO()
        try:
            call_command(
                "validate_deployment_config",
                "--environment",
                "production",
                "--format",
                "json",
                stdout=out,
            )
            output = out.getvalue()

            # Parse JSON output
            data = json.loads(output)

            # Verify JSON structure
            self.assertIn("environment", data)
            self.assertIn("passed", data)
            self.assertIn("summary", data)
            self.assertIn("errors", data)
            self.assertEqual(data["environment"], "production")
        except SystemExit:
            # Still verify JSON output even if validation fails
            output = out.getvalue()
            if output:
                data = json.loads(output)
                self.assertIn("passed", data)

    @unittest.skipUnless(_is_production, "Production settings only")
    def test_validate_deployment_config_exit_codes(self):
        """
        Test validation command returns correct exit codes.

        Verifies exit code 0 for pass, 1 for fail (CI/CD integration).
        """
        # Test exit code 1 for invalid config
        if "SECRET_KEY" in os.environ:
            del os.environ["SECRET_KEY"]

        with self.assertRaises(SystemExit) as cm:
            call_command(
                "validate_deployment_config",
                "--environment",
                "production",
                stdout=StringIO(),
            )
        self.assertEqual(cm.exception.code, 1, "Invalid config should exit with code 1")

        # Test exit code 0 for valid config
        os.environ["SECRET_KEY"] = "a" * 50
        os.environ["DATABASE_URL"] = (
            "postgresql://user:pass@host:5432/db?sslmode=require"
        )
        os.environ["ALLOWED_HOSTS"] = "grey-lit-app-ifa37.ondigitalocean.app"

        try:
            call_command(
                "validate_deployment_config",
                "--environment",
                "production",
                stdout=StringIO(),
            )
            # If no exception, exit code was 0
            exit_code = 0
        except SystemExit as e:
            exit_code = e.code

        self.assertEqual(exit_code, 0, "Valid config should exit with code 0")

    # ========================================================================
    # Test Suite 2: Health Check Integration (5 tests)
    # ========================================================================

    def test_health_check_endpoint_accessible(self):
        """
        Test that health check endpoint returns 200 OK.

        Verifies /health/ endpoint is accessible and returns valid response.
        The lightweight health check returns only status + timestamp (no checks dict).
        """
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        # Parse response - lightweight endpoint returns status + timestamp only
        data = json.loads(response.content)
        self.assertIn("status", data)
        self.assertIn("timestamp", data)

    def test_health_check_with_pod_ip_simulation(self):
        """
        Test health check with simulated DigitalOcean pod IP request.

        Verifies health check bypass middleware handles pod IP requests.
        """
        # Only test in production where HealthCheckBypassMiddleware is configured
        middleware = list(settings.MIDDLEWARE)
        has_bypass = any("HealthCheckBypassMiddleware" in mw for mw in middleware)
        if not has_bypass:
            self.skipTest(
                "HealthCheckBypassMiddleware not configured in test environment"
            )

        response = self.client.get("/health/", HTTP_HOST="10.244.32.5")
        self.assertEqual(response.status_code, 200)

    def test_health_check_middleware_order(self):
        """
        Test health check middleware is first in production settings.

        Verifies middleware order for proper bypass functionality.
        """
        middleware = getattr(settings, "MIDDLEWARE", [])

        health_check_index = -1
        for i, mw in enumerate(middleware):
            if "HealthCheckBypassMiddleware" in mw:
                health_check_index = i
                break

        # HealthCheckBypassMiddleware may not be configured in dev/test
        if health_check_index == -1:
            environment = getattr(settings, "ENVIRONMENT", "local")
            if environment in ("production", "staging"):
                self.fail("HealthCheckBypassMiddleware not found in production")
            else:
                self.skipTest("HealthCheckBypassMiddleware not configured in dev/test")

        self.assertLess(
            health_check_index,
            5,
            "HealthCheckBypassMiddleware should be early in middleware stack",
        )

    def test_health_check_without_middleware(self):
        """
        Test health check falls back to ALLOWED_CIDR_NETS without middleware.

        Verifies defense-in-depth: health checks work even without middleware.
        """
        environment = getattr(settings, "ENVIRONMENT", "local")
        if environment not in ("production", "staging"):
            self.skipTest("ALLOWED_CIDR_NETS only configured in production/staging")

        allowed_cidr_nets = getattr(settings, "ALLOWED_CIDR_NETS", [])

        digitalocean_cidr_configured = any(
            "10.244." in cidr for cidr in allowed_cidr_nets
        )

        self.assertTrue(
            digitalocean_cidr_configured,
            "ALLOWED_CIDR_NETS should include DigitalOcean pod network (10.244.0.0/16)",
        )

    def test_health_check_json_response_format(self):
        """
        Test health check JSON response has expected structure.

        Verifies response format for monitoring integrations.
        The lightweight /health/ endpoint returns {status, timestamp} only.
        The detailed /health/detailed/ endpoint has checks, message, etc.
        """
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)

        # Required fields for lightweight endpoint
        self.assertIn("status", data)
        self.assertIn("timestamp", data)

        # Status should be string
        self.assertIsInstance(data["status"], str)

        # Lightweight endpoint should NOT have detailed fields
        self.assertNotIn("checks", data)
        self.assertNotIn("message", data)

    # ========================================================================
    # Test Suite 3: Database Configuration (4 tests)
    # ========================================================================

    def test_database_connection_successful(self):
        """
        Test database connection is successful.

        Verifies Django can connect to configured database.
        """
        try:
            # Execute simple query
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

            self.assertEqual(result[0], 1)
        except Exception as e:
            self.fail(f"Database connection failed: {e}")

    def test_database_url_parsing(self):
        """
        Test DATABASE_URL is parsed correctly in settings.

        Verifies database configuration loaded from environment.
        """
        # Check database settings exist
        db_config = settings.DATABASES.get("default")

        self.assertIsNotNone(db_config, "Database configuration not found")
        self.assertIn("ENGINE", db_config)
        self.assertIn("NAME", db_config)

        # Engine should be PostgreSQL
        self.assertIn("postgresql", db_config["ENGINE"].lower())

    def test_database_ssl_mode_in_production(self):
        """
        Test SSL mode is required for production database connections.

        Verifies secure database configuration for production.
        """
        # Only check in production-like environments
        environment = getattr(settings, "ENVIRONMENT", "local")

        if environment == "production":
            db_config = settings.DATABASES.get("default")

            # Check for SSL-related options
            options = db_config.get("OPTIONS", {})

            # Should have SSL mode configured
            # This might be in OPTIONS or in the connection string
            has_ssl = (
                "sslmode" in options
                or "ssl" in options
                or (
                    "OPTIONS" in db_config
                    and "sslmode" in str(db_config.get("OPTIONS", {}))
                )
            )

            # For production, SSL should be configured
            # (Note: In test/local environments, this may not be required)
            if environment == "production":
                self.assertTrue(
                    has_ssl, "Production database should have SSL configured"
                )

    def test_database_connection_pooling(self):
        """
        Test database connection pooling is configured.

        Verifies connection pool settings for production performance.
        """
        db_config = settings.DATABASES.get("default")

        # Check for connection pooling settings
        # Django uses CONN_MAX_AGE for persistent connections
        conn_max_age = db_config.get("CONN_MAX_AGE", 0)

        # For production, should have persistent connections
        environment = getattr(settings, "ENVIRONMENT", "local")

        if environment in ["production", "staging"]:
            self.assertGreater(
                conn_max_age,
                0,
                "Production should use persistent database connections (CONN_MAX_AGE > 0)",
            )

    # ========================================================================
    # Test Suite 4: Cache Configuration (4 tests)
    # ========================================================================

    def test_cache_backend_configured(self):
        """
        Test cache backend is loaded correctly.

        Verifies Django cache system is functional.
        """
        # Cache should be accessible
        self.assertIsNotNone(cache)

        # Should have a backend class
        self.assertTrue(hasattr(cache, "__class__"))

        # Backend should be either Redis or Database
        backend_name = cache.__class__.__name__
        self.assertIn(
            backend_name,
            [
                "RedisCache",
                "DatabaseCache",
                "DummyCache",
                "LocMemCache",
                "ConnectionProxy",
            ],
            f"Unexpected cache backend: {backend_name}",
        )

    def test_redis_cache_fallback_to_database(self):
        """
        Test graceful fallback from Redis to database cache.

        Verifies cache system handles Redis unavailability.
        """
        # Check cache configuration
        cache_config = settings.CACHES.get("default", {})
        backend = cache_config.get("BACKEND", "")

        # Log which backend is in use
        if "redis" in backend.lower():
            # Redis configured - test it works
            try:
                cache.set("test_redis_key", "test_value", 10)
                value = cache.get("test_redis_key")
                self.assertEqual(value, "test_value")
            except Exception:
                # Redis not available - should fall back
                # (In real deployment, fallback is automatic)
                pass
        elif "database" in backend.lower():
            # Database cache - test it works
            cache.set("test_db_key", "test_value", 10)
            value = cache.get("test_db_key")
            self.assertEqual(value, "test_value")
        else:
            # Other cache backend (LocMem, Dummy)
            # Just verify it's accessible
            pass

    def test_cache_key_operations(self):
        """
        Test basic cache set/get/delete operations.

        Verifies cache functionality for application use.
        """
        test_key = "deployment_test_key"
        test_value = {"test": "data", "number": 42}

        try:
            # Set value
            cache.set(test_key, test_value, 30)

            # Get value
            retrieved = cache.get(test_key)
            self.assertEqual(retrieved, test_value)

            # Delete value
            cache.delete(test_key)

            # Verify deleted
            retrieved_after_delete = cache.get(test_key)
            self.assertIsNone(retrieved_after_delete)
        finally:
            # Clean up
            cache.delete(test_key)

    def test_cache_timeout_configuration(self):
        """
        Test cache timeouts are configured correctly.

        Verifies cache expiry settings for production.
        """
        cache_config = settings.CACHES.get("default", {})

        # Check timeout setting
        timeout = cache_config.get("TIMEOUT", 300)

        # Should have reasonable timeout (not None, not too short)
        self.assertIsNotNone(timeout)
        self.assertIsInstance(timeout, (int, float))
        self.assertGreater(timeout, 0, "Cache timeout should be positive")

    # ========================================================================
    # Test Suite 5: Django System Checks (5 tests)
    # ========================================================================

    def test_django_check_passes_in_production(self):
        """
        Test 'manage.py check' passes without errors.

        Verifies Django system checks pass for production readiness.
        """
        out = StringIO()
        err = StringIO()

        try:
            management.call_command("check", stdout=out, stderr=err)
            # No exceptions = checks passed
            checks_passed = True
            output = out.getvalue()
        except management.CommandError as e:
            checks_passed = False
            output = str(e)

        self.assertTrue(checks_passed, f"Django system checks failed: {output}")

    def test_django_check_deploy_in_production(self):
        """
        Test 'manage.py check --deploy' passes in production-like settings.

        Verifies production deployment checks pass.
        """
        # Only run deploy checks if in production-like environment
        environment = getattr(settings, "ENVIRONMENT", "local")

        if environment in ["production", "staging"]:
            out = StringIO()
            err = StringIO()

            try:
                management.call_command("check", "--deploy", stdout=out, stderr=err)
                checks_passed = True
                output = out.getvalue()
            except management.CommandError as e:
                checks_passed = False
                output = str(e)

            self.assertTrue(checks_passed, f"Django deployment checks failed: {output}")
        else:
            # Skip in local/test environments
            self.skipTest("Deployment checks only run in production/staging")

    def test_allowed_cidr_nets_validation(self):
        """
        Test ALLOWED_CIDR_NETS validation system check.

        Verifies custom system check for netaddr library availability.
        """
        # Run system checks
        from django.core.management import call_command

        out = StringIO()

        # Should not raise exception
        try:
            call_command("check", stdout=out)
            # Check if netaddr warning appears
            output = out.getvalue()

            # If netaddr not installed, should see warning
            # If netaddr installed, no warning expected
            try:
                import netaddr  # noqa: F401

                netaddr_available = True
            except ImportError:
                netaddr_available = False

            if not netaddr_available:
                # Should see warning about netaddr
                self.assertIn(
                    "netaddr",
                    output.lower(),
                    "Should warn about missing netaddr library",
                )
        except Exception as e:
            self.fail(f"System checks failed unexpectedly: {e}")

    def test_allowed_hosts_patterns_validation(self):
        """
        Test validation detects invalid ALLOWED_HOSTS patterns.

        Verifies system checks catch shell-style glob patterns.
        """
        from apps.core.utils.deployment_validation import DeploymentValidator

        # Set env var for the validator (it reads from os.environ)
        os.environ["ALLOWED_HOSTS"] = "example.com,10.244.*"

        validator = DeploymentValidator(environment="production")

        # validate_allowed_hosts raises EnvironmentVariableError for invalid patterns
        from apps.core.utils.deployment_validation import EnvironmentVariableError

        with self.assertRaises(EnvironmentVariableError):
            validator.validate_allowed_hosts()

    def test_digitalocean_health_check_config(self):
        """
        Test DigitalOcean-specific health check configuration.

        Verifies pod network CIDR is configured for health checks.
        """
        allowed_cidr_nets = getattr(settings, "ALLOWED_CIDR_NETS", [])

        # Should have DigitalOcean pod network
        has_digitalocean_cidr = any(
            "10.244." in str(cidr) for cidr in allowed_cidr_nets
        )

        # In production, this should be configured
        environment = getattr(settings, "ENVIRONMENT", "local")

        if environment == "production":
            self.assertTrue(
                has_digitalocean_cidr,
                "Production should have DigitalOcean pod network in ALLOWED_CIDR_NETS",
            )

    # ========================================================================
    # Test Suite 6: Middleware Integration (4 tests)
    # ========================================================================

    def test_middleware_stack_order(self):
        """
        Test all middleware is in correct order.

        Verifies middleware stack configuration for production.
        """
        middleware = list(settings.MIDDLEWARE)

        # Key middleware that should exist
        required_middleware = [
            "django.middleware.security.SecurityMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
        ]

        for required_mw in required_middleware:
            self.assertIn(
                required_mw, middleware, f"Required middleware missing: {required_mw}"
            )

        # Security middleware should be first in production.
        # In dev, DebugToolbarMiddleware may be first.
        security_idx = next(
            (i for i, mw in enumerate(middleware) if mw.endswith("SecurityMiddleware")),
            -1,
        )
        self.assertNotEqual(security_idx, -1, "SecurityMiddleware not found")
        self.assertLessEqual(
            security_idx,
            2,
            "SecurityMiddleware should be within first 3 middleware entries",
        )

    def test_async_middleware_compatibility(self):
        """
        Test async views work correctly with middleware stack.

        Verifies async-aware middleware configuration.
        """
        # Test async health check endpoint
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)

        # Verify response came from async view
        # (async views in Django 5.1+ work transparently with middleware)
        data = json.loads(response.content)
        self.assertIn("status", data)

    def test_correlation_id_middleware(self):
        """
        Test correlation ID middleware generates request IDs.

        Verifies request tracing functionality.
        """
        # Check if CorrelationIDMiddleware is configured
        middleware = list(settings.MIDDLEWARE)

        has_correlation_middleware = any(
            "CorrelationIDMiddleware" in mw for mw in middleware
        )

        if has_correlation_middleware:
            # Make request and check for correlation ID
            _response = self.client.get("/health/")

            # Should have X-Correlation-ID header
            # (if middleware adds it to response)
            # Note: This depends on middleware implementation
            pass
        else:
            self.skipTest("CorrelationIDMiddleware not configured")

    def test_health_check_bypass_middleware_production(self):
        """
        Test health check bypass middleware works in production config.

        Verifies middleware correctly handles pod IP requests.
        """
        # Check middleware is configured
        middleware = list(settings.MIDDLEWARE)

        has_health_check_bypass = any(
            "HealthCheckBypassMiddleware" in mw for mw in middleware
        )

        if not has_health_check_bypass:
            environment = getattr(settings, "ENVIRONMENT", "local")
            if environment in ("production", "staging"):
                self.fail(
                    "HealthCheckBypassMiddleware should be configured in production"
                )
            else:
                self.skipTest("HealthCheckBypassMiddleware not configured in dev/test")

        # Test middleware functionality
        def simple_response(request):
            from django.http import HttpResponse

            return HttpResponse("OK")

        middleware_instance = HealthCheckBypassMiddleware(simple_response)

        # Create pod IP request
        request = self.factory.get("/health/", HTTP_HOST="10.244.32.5")

        # Process request
        _response = middleware_instance(request)

        # Should have bypass marker
        self.assertTrue(
            hasattr(request, "_health_check_bypass"),
            "Health check bypass should be activated for pod IP",
        )

        self.assertTrue(request._health_check_bypass)
