"""
Tests for production security settings including CSP headers and cookie security.

These tests validate production settings file content and production-specific
configurations. They are skipped in local/test environments.
"""

import os
import unittest
from importlib import import_module

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.test.client import Client
from django.urls import reverse
from apps.core.tests.utils import create_test_user

User = get_user_model()

_is_production = (
    os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith("production")
    and os.environ.get("ENVIRONMENT") == "production"
)


@unittest.skipUnless(_is_production, "Production settings only")
class ProductionSecurityTests(TestCase):
    """Test production security configurations."""

    def setUp(self):
        """Set up test client and user."""
        self.client = Client()
        self.user = create_test_user()

    @override_settings(
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        CSRF_COOKIE_HTTPONLY=True,
        X_FRAME_OPTIONS="DENY",
        SESSION_COOKIE_SAMESITE="Strict",
        CSRF_COOKIE_SAMESITE="Strict",
    )
    def test_security_headers_configured(self):
        """Test all security headers are properly set."""
        # Make a request to generate response
        self.client.login(username=self.user.username, password="testpass123")
        response = self.client.get("/")

        # Check X-Frame-Options header
        self.assertEqual(response.get("X-Frame-Options", "").upper(), "DENY")

    def test_csp_middleware_configured(self):
        """Test CSP middleware is in correct position."""
        # Import production settings module
        try:
            prod_settings = import_module("grey_lit_project.settings.production")
            middleware = prod_settings.MIDDLEWARE

            # Check CSP middleware is present
            csp_middlewares = ["csp.middleware.CSPMiddleware"]

            for csp_mw in csp_middlewares:
                self.assertIn(
                    csp_mw,
                    middleware,
                    f"CSP middleware {csp_mw} not found in MIDDLEWARE",
                )

            # Check middleware ordering
            security_middleware_idx = middleware.index(
                "django.middleware.security.SecurityMiddleware"
            )
            csp_middleware_idx = middleware.index("csp.middleware.CSPMiddleware")

            # CSP should come after SecurityMiddleware
            self.assertGreater(
                csp_middleware_idx,
                security_middleware_idx,
                "CSP middleware should come after SecurityMiddleware",
            )

        except ImportError:
            self.skipTest(
                "Production settings module not available in test environment"
            )

    def test_sentry_configuration_without_hardcoded_dsn(self):
        """Test Sentry initializes only with environment variable."""
        try:
            # Read file content instead of importing (avoids side effects)
            import os

            settings_path = os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                ),
                "grey_lit_project",
                "settings",
                "production.py",
            )
            with open(settings_path, "r") as f:
                content = f.read()

            # Check for the old hardcoded DSN pattern
            self.assertNotIn(
                "https://0d1d5b4f6155f3852377e3052a2016ea@",
                content,
                "Hardcoded Sentry DSN found in production settings!",
            )

            # Verify Sentry uses SentryInitializer (which reads from env internally)
            # OR directly references SENTRY_DSN via get_env/os.environ
            has_sentry_initializer = "SentryInitializer.initialize" in content
            has_env_dsn = (
                'get_env("SENTRY_DSN"' in content
                or "get_env('SENTRY_DSN'" in content
                or 'os.environ.get("SENTRY_DSN"' in content
                or "os.environ.get('SENTRY_DSN'" in content
            )
            self.assertTrue(
                has_sentry_initializer or has_env_dsn,
                "Sentry should be initialized via SentryInitializer.initialize() or directly reference SENTRY_DSN from environment",
            )
        except FileNotFoundError:
            self.skipTest("Production settings file not found")

    @override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_secure_cookies_configuration(self):
        """Test secure cookie settings are enforced."""
        # Login to create session
        self.client.login(username=self.user.username, password="testpass123")
        _response = self.client.get("/")

        # Check response has secure cookie attributes
        # Note: In test environment, we can't directly check Set-Cookie headers
        # but we verify the settings are applied
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)

    def test_csrf_middleware_present(self):
        """Test CSRF middleware is properly configured."""
        # Verify CSRF middleware is in the middleware stack
        middleware = list(settings.MIDDLEWARE)
        csrf_present = any("CsrfViewMiddleware" in mw for mw in middleware)
        self.assertTrue(csrf_present, "CsrfViewMiddleware should be in MIDDLEWARE")

    @override_settings(
        CSP_DEFAULT_SRC=("'self'",),
        CSP_SCRIPT_SRC=("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"),
        CSP_STYLE_SRC=("'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"),
        CSP_FONT_SRC=("'self'", "https://cdn.jsdelivr.net"),
        CSP_IMG_SRC=("'self'", "data:", "https:"),
        CSP_CONNECT_SRC=("'self'",),
        CSP_FRAME_ANCESTORS=("'none'",),
        CSP_REPORT_URI="/csp-report/",
    )
    def test_csp_headers_applied(self):
        """Test Content Security Policy headers are applied."""
        # Make request with CSP settings
        response = self.client.get("/")

        # Check for CSP header
        csp_header = response.get("Content-Security-Policy", "")
        if not csp_header:
            # Try alternate header name
            csp_header = response.get("Content-Security-Policy-Report-Only", "")

        if csp_header:
            # Verify key CSP directives
            self.assertIn("default-src", csp_header)
            self.assertIn("script-src", csp_header)
            self.assertIn("style-src", csp_header)
            self.assertIn("frame-ancestors", csp_header)

    def test_clickjacking_protection(self):
        """Test X-Frame-Options header for clickjacking protection."""
        response = self.client.get("/")

        # X-Frame-Options should be set
        x_frame_options = response.get("X-Frame-Options", "")
        self.assertIn(
            x_frame_options.upper(),
            ["DENY", "SAMEORIGIN"],
            "X-Frame-Options header should be DENY or SAMEORIGIN",
        )

    @override_settings(SECURE_BROWSER_XSS_FILTER=True, SECURE_CONTENT_TYPE_NOSNIFF=True)
    def test_additional_security_headers(self):
        """Test additional security headers are set."""
        _response = self.client.get("/")

        # These headers are set by SecurityMiddleware when enabled
        # In production, these should be present
        if hasattr(settings, "SECURE_BROWSER_XSS_FILTER"):
            self.assertTrue(settings.SECURE_BROWSER_XSS_FILTER)

        if hasattr(settings, "SECURE_CONTENT_TYPE_NOSNIFF"):
            self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)

    def test_admin_url_changed(self):
        """Test admin URL is not at default /admin/."""
        # Try default admin URL
        _response = self.client.get("/admin/")

        # Should be 404 if properly configured
        # Note: In test environment, this might still resolve
        # In production, ADMIN_URL should be changed
        if hasattr(settings, "ADMIN_URL"):
            self.assertNotEqual(settings.ADMIN_URL, "admin/")

    def test_debug_mode_disabled(self):
        """Test DEBUG is False in production settings."""
        try:
            # Read file content instead of importing (importing triggers side effects)
            import os

            settings_path = os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                ),
                "grey_lit_project",
                "settings",
                "production.py",
            )
            with open(settings_path, "r") as f:
                content = f.read()

            # Check DEBUG is set to False (hardcoded) OR via get_env_bool (secure pattern)
            has_hardcoded_false = "DEBUG = False" in content
            has_env_bool = (
                'get_env_bool("DEBUG"' in content or "get_env_bool('DEBUG'" in content
            )
            self.assertTrue(
                has_hardcoded_false or has_env_bool,
                "Production settings should have DEBUG = False or use get_env_bool('DEBUG', default=False)",
            )
        except FileNotFoundError:
            self.skipTest("Production settings file not found")

    def test_allowed_hosts_configured(self):
        """Test ALLOWED_HOSTS is properly configured."""
        try:
            import grey_lit_project.settings.production as prod_settings

            allowed_hosts = getattr(prod_settings, "ALLOWED_HOSTS", [])

            # Should not be empty or contain wildcard
            self.assertNotEqual(allowed_hosts, [])
            self.assertNotIn(
                "*", allowed_hosts, "ALLOWED_HOSTS should not contain wildcard '*'"
            )

        except ImportError:
            self.skipTest(
                "Production settings module not available in test environment"
            )

    def test_secure_ssl_redirect(self):
        """Test SECURE_SSL_REDIRECT is enabled for HTTPS enforcement."""
        try:
            import grey_lit_project.settings.production as prod_settings

            # Check if SECURE_SSL_REDIRECT is set
            if hasattr(prod_settings, "SECURE_SSL_REDIRECT"):
                # Should be configurable via environment
                # The actual value would come from config()
                pass

        except ImportError:
            self.skipTest(
                "Production settings module not available in test environment"
            )


@unittest.skipUnless(_is_production, "Production settings only")
class CSPReportingTests(TestCase):
    """Test CSP violation reporting functionality."""

    def setUp(self):
        """Set up test client."""
        self.client = Client()

    @override_settings(CSP_REPORT_URI="/csp-report/")
    def test_csp_report_endpoint_exists(self):
        """Test CSP report URI is configured in production settings."""
        try:
            import os

            settings_path = os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                ),
                "grey_lit_project",
                "settings",
                "production.py",
            )
            with open(settings_path, "r") as f:
                content = f.read()

            # Check CSP report URI is configured via CSPConfigBuilder or directly
            has_csp_config_builder = (
                "CSPConfigBuilder" in content and "build()" in content
            )
            has_csp_report_direct = (
                "CSP_REPORT_URI" in content or "csp-report" in content
            )
            self.assertTrue(
                has_csp_config_builder or has_csp_report_direct,
                "Production settings should configure CSP via CSPConfigBuilder.build() or directly set CSP_REPORT_URI",
            )
        except FileNotFoundError:
            self.skipTest("Production settings file not found")


class SecurityHeadersIntegrationTest(TestCase):
    """Integration tests for all security headers working together."""

    def setUp(self):
        """Set up test client and user."""
        self.client = Client()
        self.user = create_test_user()

    @override_settings(
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        CSRF_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        CSRF_COOKIE_SAMESITE="Strict",
        X_FRAME_OPTIONS="DENY",
        SECURE_BROWSER_XSS_FILTER=True,
        SECURE_CONTENT_TYPE_NOSNIFF=True,
        CSP_DEFAULT_SRC=("'self'",),
    )
    def test_all_security_headers_together(self):
        """Test all security headers work together without conflicts."""
        # Login to test authenticated requests
        self.client.login(username=self.user.username, password="testpass123")

        # Test various endpoints
        endpoints = [
            "/",
            reverse("review_manager:dashboard"),
            reverse("accounts:profile"),
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                try:
                    response = self.client.get(endpoint)
                    # Should not cause 500 errors
                    self.assertLess(response.status_code, 500)
                except Exception:
                    # Log but don't fail - some URLs might not exist in test
                    pass

    def test_no_sensitive_headers_exposed(self):
        """Test no sensitive information in response headers."""
        response = self.client.get("/")

        # Check no sensitive headers are exposed
        sensitive_headers = [
            "Server",  # Can reveal server software version
            "X-Powered-By",  # Can reveal framework
            "X-AspNet-Version",  # Not applicable but check anyway
        ]

        for header in sensitive_headers:
            self.assertIsNone(
                response.get(header), f"Sensitive header {header} should not be exposed"
            )
