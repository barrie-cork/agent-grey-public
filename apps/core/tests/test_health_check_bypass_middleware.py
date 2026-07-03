"""
Health Check Bypass Middleware Tests

Comprehensive test coverage for HealthCheckBypassMiddleware to ensure:
- Proper bypass activation for pod IP health checks
- No bypass for normal requests
- DisallowedHost exception handling
- Custom configuration support
"""

from unittest.mock import patch

from django.core.exceptions import DisallowedHost
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.core.middleware.health_check_bypass import HealthCheckBypassMiddleware


class HealthCheckBypassMiddlewareTestCase(TestCase):
    """
    Test HealthCheckBypassMiddleware for health check endpoint access.

    Tests verify:
    1. Bypass activated for pod IP health checks
    2. No bypass for normal requests
    3. DisallowedHost exception handling
    4. Custom configuration respected
    """

    def setUp(self):
        """Set up test fixtures."""
        self.sync_factory = RequestFactory()

    def sync_get_response(self, request):
        """Simulate a sync view."""
        return HttpResponse("Sync response")

    # Test 1: Bypass activated for pod IP health checks

    def test_bypass_for_pod_ip_health_check_default_path(self):
        """
        Test bypass activation for pod IP accessing /health/.

        Verifies:
        - request._health_check_bypass is set to True
        - request.get_host() returns configured app domain
        - Request processes successfully
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/health/", HTTP_HOST="10.244.32.5:8080")

        response = middleware(request)

        # Assert bypass was activated
        self.assertTrue(hasattr(request, "_health_check_bypass"))
        self.assertTrue(request._health_check_bypass)

        # Assert get_host() was patched to return app domain
        self.assertEqual(request.get_host(), "grey-lit-app-ifa37.ondigitalocean.app")

        # Assert response is successful
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "Sync response")

    def test_bypass_for_pod_ip_health_check_healthz_path(self):
        """
        Test bypass activation for pod IP accessing /healthz.

        Verifies alternate health check path works.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/healthz", HTTP_HOST="10.244.1.100")

        _response = middleware(request)

        # Assert bypass was activated
        self.assertTrue(hasattr(request, "_health_check_bypass"))
        self.assertTrue(request._health_check_bypass)
        self.assertEqual(request.get_host(), "grey-lit-app-ifa37.ondigitalocean.app")

    def test_bypass_for_pod_ip_health_check_with_port(self):
        """
        Test bypass activation for pod IP with port number.

        Verifies pod IP detection works with :port suffix.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/health/", HTTP_HOST="10.244.99.254:8000")

        _response = middleware(request)

        self.assertTrue(hasattr(request, "_health_check_bypass"))
        self.assertTrue(request._health_check_bypass)

    def test_bypass_for_pod_ip_health_check_without_port(self):
        """
        Test bypass activation for pod IP without port number.

        Verifies pod IP detection works without :port suffix.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/health/", HTTP_HOST="10.244.50.1")

        _response = middleware(request)

        self.assertTrue(hasattr(request, "_health_check_bypass"))
        self.assertTrue(request._health_check_bypass)

    # Test 2: No bypass for normal requests

    def test_no_bypass_for_external_domain_health_check(self):
        """
        Test no bypass for health check from external domain.

        Verifies only pod IPs trigger bypass, not legitimate domains.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get(
            "/health/", HTTP_HOST="grey-lit-app-ifa37.ondigitalocean.app"
        )

        response = middleware(request)

        # Assert bypass was NOT activated
        self.assertFalse(hasattr(request, "_health_check_bypass"))

        # Assert request processed normally
        self.assertEqual(response.status_code, 200)

    def test_no_bypass_for_pod_ip_non_health_path(self):
        """
        Test no bypass for pod IP accessing non-health check path.

        Verifies bypass only applies to health check endpoints.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/", HTTP_HOST="10.244.32.5")

        _response = middleware(request)

        # Assert bypass was NOT activated
        self.assertFalse(hasattr(request, "_health_check_bypass"))

    def test_no_bypass_for_non_pod_ip_prefix(self):
        """
        Test no bypass for IP addresses outside pod network range.

        Verifies only 10.244.x.x IPs trigger bypass.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)

        # Test various non-pod IPs
        non_pod_ips = [
            "192.168.1.1",
            "172.16.0.1",
            "10.245.1.1",  # Close but not 10.244
            "10.243.1.1",  # Close but not 10.244
        ]

        for ip in non_pod_ips:
            request = self.sync_factory.get("/health/", HTTP_HOST=ip)
            _response = middleware(request)
            self.assertFalse(
                hasattr(request, "_health_check_bypass"),
                f"Bypass incorrectly activated for IP: {ip}",
            )

    def test_no_bypass_for_localhost(self):
        """
        Test no bypass for localhost accessing health check.

        Verifies localhost is handled normally (should be in ALLOWED_HOSTS).
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/health/", HTTP_HOST="localhost")

        _response = middleware(request)

        # Assert bypass was NOT activated
        self.assertFalse(hasattr(request, "_health_check_bypass"))

    # Test 3: DisallowedHost exception handling

    def test_disallowed_host_returns_200_for_health_check(self):
        """
        Test DisallowedHost exception returns 200 OK for health checks.

        Verifies middleware catches and handles DisallowedHost for health
        check endpoints, returning a valid JSON response.
        """

        def failing_get_response(request):
            raise DisallowedHost("Host not allowed")

        middleware = HealthCheckBypassMiddleware(failing_get_response)
        request = self.sync_factory.get("/health/", HTTP_HOST="10.244.32.5")

        response = middleware(request)

        # Assert response is 200 OK with JSON content
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("status", response.content.decode())
        self.assertIn("ok", response.content.decode())

    def test_disallowed_host_returns_200_for_healthz(self):
        """
        Test DisallowedHost exception returns 200 OK for /healthz.

        Verifies alternate health check path also returns 200 OK.
        """

        def failing_get_response(request):
            raise DisallowedHost("Host not allowed")

        middleware = HealthCheckBypassMiddleware(failing_get_response)
        request = self.sync_factory.get("/healthz", HTTP_HOST="10.244.1.100")

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_disallowed_host_propagates_for_non_health_check(self):
        """
        Test DisallowedHost exception propagates for non-health check paths.

        Verifies middleware doesn't interfere with normal Django security.
        """

        def failing_get_response(request):
            raise DisallowedHost("Host not allowed")

        middleware = HealthCheckBypassMiddleware(failing_get_response)
        request = self.sync_factory.get("/", HTTP_HOST="10.244.32.5")

        # Assert exception propagates
        with self.assertRaises(DisallowedHost):
            middleware(request)

    def test_other_exceptions_propagate_normally(self):
        """
        Test other exceptions propagate without interference.

        Verifies middleware only handles DisallowedHost, not all exceptions.
        """

        def failing_get_response(request):
            raise ValueError("Test error")

        middleware = HealthCheckBypassMiddleware(failing_get_response)
        request = self.sync_factory.get("/health/", HTTP_HOST="10.244.32.5")

        # Assert ValueError propagates
        with self.assertRaises(ValueError):
            middleware(request)

    # Test 4: Custom configuration respected

    @override_settings(HEALTH_CHECK_PATHS=["/custom-health/", "/status/"])
    def test_custom_health_check_paths(self):
        """
        Test middleware respects custom HEALTH_CHECK_PATHS setting.

        Verifies configuration can override default health check paths.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)

        # Test custom path activates bypass
        request = self.sync_factory.get("/custom-health/", HTTP_HOST="10.244.32.5")
        _response = middleware(request)
        self.assertTrue(hasattr(request, "_health_check_bypass"))

        # Test default path no longer activates bypass
        request = self.sync_factory.get("/health/", HTTP_HOST="10.244.32.5")
        _response = middleware(request)
        self.assertFalse(hasattr(request, "_health_check_bypass"))

    @override_settings(HEALTH_CHECK_POD_NETWORK_PREFIX="192.168.")
    def test_custom_pod_network_prefix(self):
        """
        Test middleware respects custom HEALTH_CHECK_POD_NETWORK_PREFIX.

        Verifies pod network prefix can be customised for different
        Kubernetes/cloud environments.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)

        # Test custom prefix activates bypass
        request = self.sync_factory.get("/health/", HTTP_HOST="192.168.1.100")
        _response = middleware(request)
        self.assertTrue(hasattr(request, "_health_check_bypass"))

        # Test default prefix no longer activates bypass
        request = self.sync_factory.get("/health/", HTTP_HOST="10.244.32.5")
        _response = middleware(request)
        self.assertFalse(hasattr(request, "_health_check_bypass"))

    @override_settings(HEALTH_CHECK_APP_DOMAIN="custom-app.example.com")
    def test_custom_app_domain(self):
        """
        Test middleware respects custom HEALTH_CHECK_APP_DOMAIN.

        Verifies get_host() returns custom domain when configured.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/health/", HTTP_HOST="10.244.32.5")

        _response = middleware(request)

        # Assert custom domain is returned
        self.assertEqual(request.get_host(), "custom-app.example.com")

    @override_settings(
        HEALTH_CHECK_PATHS=["/api/health/"],
        HEALTH_CHECK_POD_NETWORK_PREFIX="172.31.",
        HEALTH_CHECK_APP_DOMAIN="test.example.org",
    )
    def test_multiple_custom_settings(self):
        """
        Test middleware respects multiple custom settings simultaneously.

        Verifies all configuration options work together correctly.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/api/health/", HTTP_HOST="172.31.50.1")

        _response = middleware(request)

        self.assertTrue(hasattr(request, "_health_check_bypass"))
        self.assertEqual(request.get_host(), "test.example.org")

    # Additional edge cases and integration tests

    def test_missing_http_host_header(self):
        """
        Test middleware handles requests without HTTP_HOST header.

        Verifies middleware doesn't crash if HTTP_HOST is missing.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)

        # Create request without HTTP_HOST
        request = self.sync_factory.get("/health/")
        # Remove HTTP_HOST from META
        if "HTTP_HOST" in request.META:
            del request.META["HTTP_HOST"]

        # Should not raise exception
        _response = middleware(request)

        # Should not activate bypass (no host to check)
        self.assertFalse(hasattr(request, "_health_check_bypass"))

    def test_empty_http_host_header(self):
        """
        Test middleware handles empty HTTP_HOST header.

        Verifies middleware gracefully handles empty host values.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/health/", HTTP_HOST="")

        _response = middleware(request)

        # Should not activate bypass
        self.assertFalse(hasattr(request, "_health_check_bypass"))

    @patch("apps.core.middleware.health_check_bypass.logger")
    def test_debug_logging_on_bypass_activation(self, mock_logger):
        """
        Test middleware logs debug information when bypass is activated.

        Verifies logging helps troubleshoot health check issues.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/health/", HTTP_HOST="10.244.32.5")

        _response = middleware(request)

        # Assert debug logging was called
        mock_logger.debug.assert_called()

    @patch("apps.core.middleware.health_check_bypass.logger")
    def test_warning_logging_on_disallowed_host(self, mock_logger):
        """
        Test middleware logs warning when catching DisallowedHost.

        Verifies security-relevant events are logged for monitoring.
        """

        def failing_get_response(request):
            raise DisallowedHost("Host not allowed")

        middleware = HealthCheckBypassMiddleware(failing_get_response)
        request = self.sync_factory.get("/health/", HTTP_HOST="10.244.32.5")

        _response = middleware(request)

        # Assert warning logging was called
        mock_logger.warning.assert_called()

    def test_original_get_host_not_affected_for_non_bypass_requests(self):
        """
        Test get_host() is not patched for non-bypass requests.

        Verifies middleware doesn't interfere with normal request processing.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)
        request = self.sync_factory.get("/", HTTP_HOST="example.com")

        # Store original get_host method
        original_get_host = request.get_host

        _response = middleware(request)

        # Assert get_host was not patched
        self.assertEqual(request.get_host, original_get_host)

    def test_middleware_configuration_loaded_at_init(self):
        """
        Test middleware loads configuration from settings at initialisation.

        Verifies configuration is read once during __init__, not per request.
        """
        middleware = HealthCheckBypassMiddleware(self.sync_get_response)

        # Assert configuration attributes exist
        self.assertTrue(hasattr(middleware, "health_check_paths"))
        self.assertTrue(hasattr(middleware, "pod_network_prefix"))
        self.assertTrue(hasattr(middleware, "app_domain"))

        # Assert default values
        self.assertIn("/health/", middleware.health_check_paths)
        self.assertEqual(middleware.pod_network_prefix, "10.244.")
        self.assertEqual(middleware.app_domain, "grey-lit-app-ifa37.ondigitalocean.app")
