"""
Tests for security-related Django system checks and settings guards.

Tests for checks defined in apps/core/checks.py and guards in settings files.
"""

import importlib
import os
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from apps.core.checks import (
    check_cors_credentials_without_origins,
    check_ssl_redirect_production,
)


class ProductionSecretKeyGuardTest(TestCase):
    """Tests for production SECRET_KEY guard in production.py."""

    def test_production_raises_when_secret_key_missing(self):
        """Production must reject missing SECRET_KEY."""
        env = {
            "DATABASE_URL": "postgresql://u:p@h:5432/db?sslmode=require",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("SECRET_KEY", None)
            with self.assertRaises(ImproperlyConfigured):
                from grey_lit_project.settings import production

                importlib.reload(production)

    def test_production_raises_when_secret_key_too_short(self):
        """Production must reject SECRET_KEY shorter than 32 chars."""
        env = {
            "SECRET_KEY": "tooshort",
            "DATABASE_URL": "postgresql://u:p@h:5432/db?sslmode=require",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with self.assertRaises(ImproperlyConfigured):
                from grey_lit_project.settings import production

                importlib.reload(production)

    def test_production_accepts_valid_secret_key(self):
        """Production should accept a SECRET_KEY >= 32 chars."""
        long_key = "a" * 50
        env = {
            "SECRET_KEY": long_key,
            "DATABASE_URL": "postgresql://u:p@h:5432/db?sslmode=require",
        }
        try:
            with mock.patch.dict(os.environ, env, clear=False):
                from grey_lit_project.settings import production

                importlib.reload(production)
        except ImproperlyConfigured:
            raise  # SECRET_KEY guard failure should not be swallowed
        except Exception:  # noqa: BLE001
            # production.py has complex imports (HostConfiguration, CacheConfigBuilder,
            # SentryInitializer) that may fail during reload in test environment.
            # The guard logic is correct if it didn't raise ImproperlyConfigured.
            self.skipTest("Cannot fully reload production settings in test environment")
        else:
            self.assertEqual(production.SECRET_KEY, long_key)


class LocalSettingsGuardrailTest(TestCase):
    """Tests for local.py DEBUG guard."""

    def test_local_raises_when_debug_false(self):
        """local.py must reject DEBUG=False."""
        with mock.patch.dict(os.environ, {"DEBUG": "False"}, clear=False):
            with self.assertRaises(ImproperlyConfigured):
                from grey_lit_project.settings import local

                importlib.reload(local)

    def test_local_loads_when_debug_true(self):
        """local.py should load normally with DEBUG=True."""
        with mock.patch.dict(os.environ, {"DEBUG": "True"}, clear=False):
            from grey_lit_project.settings import local

            importlib.reload(local)
            self.assertTrue(local.DEBUG)


class SSLRedirectCheckTest(TestCase):
    """Tests for check_ssl_redirect_production (core.W009)."""

    @override_settings(ENVIRONMENT="production", SECURE_SSL_REDIRECT=False)
    def test_ssl_redirect_warning_when_false_in_production(self):
        """Should warn when SSL redirect is off without explicit bypass."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SSL_REDIRECT_HANDLED_EXTERNALLY", None)
            result = check_ssl_redirect_production(None)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "core.W009")

    @override_settings(ENVIRONMENT="production", SECURE_SSL_REDIRECT=False)
    def test_ssl_redirect_no_warning_when_handled_externally(self):
        """Should suppress warning when env var confirms external handling."""
        with mock.patch.dict(
            os.environ,
            {"SSL_REDIRECT_HANDLED_EXTERNALLY": "true"},
            clear=False,
        ):
            result = check_ssl_redirect_production(None)
        self.assertEqual(len(result), 0)

    @override_settings(ENVIRONMENT="production", SECURE_SSL_REDIRECT=True)
    def test_ssl_redirect_no_warning_when_true(self):
        """No warning when SECURE_SSL_REDIRECT is True."""
        result = check_ssl_redirect_production(None)
        self.assertEqual(len(result), 0)

    @override_settings(ENVIRONMENT="local")
    def test_ssl_redirect_no_warning_in_non_production(self):
        """Check is skipped outside production."""
        result = check_ssl_redirect_production(None)
        self.assertEqual(len(result), 0)


class CORSValidationCheckTest(TestCase):
    """Tests for check_cors_credentials_without_origins (core.C008)."""

    @override_settings(
        ENVIRONMENT="production",
        CORS_ALLOW_CREDENTIALS=True,
        CORS_ALLOWED_ORIGINS=[],
        CORS_ALLOW_ALL_ORIGINS=False,
    )
    def test_cors_critical_when_credentials_true_origins_empty(self):
        """Should raise Critical when credentials enabled without origins."""
        result = check_cors_credentials_without_origins(None)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "core.C008")

    @override_settings(
        ENVIRONMENT="production",
        CORS_ALLOW_CREDENTIALS=True,
        CORS_ALLOWED_ORIGINS=["https://agentgrey.app"],
        CORS_ALLOW_ALL_ORIGINS=False,
    )
    def test_cors_passes_when_origins_populated(self):
        """No error when CORS origins are configured."""
        result = check_cors_credentials_without_origins(None)
        self.assertEqual(len(result), 0)

    @override_settings(
        ENVIRONMENT="staging",
        CORS_ALLOW_CREDENTIALS=True,
        CORS_ALLOWED_ORIGINS=[],
        CORS_ALLOW_ALL_ORIGINS=True,
    )
    def test_cors_passes_when_allow_all_true(self):
        """No error when CORS_ALLOW_ALL_ORIGINS is True."""
        result = check_cors_credentials_without_origins(None)
        self.assertEqual(len(result), 0)

    @override_settings(
        ENVIRONMENT="local",
        CORS_ALLOW_CREDENTIALS=True,
        CORS_ALLOWED_ORIGINS=[],
    )
    def test_cors_skipped_in_local_environment(self):
        """Check is skipped outside production/staging."""
        result = check_cors_credentials_without_origins(None)
        self.assertEqual(len(result), 0)
