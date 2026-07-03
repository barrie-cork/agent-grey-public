"""Regression tests for extension CORS hardening (plan 001)."""

from django.conf import settings
from django.test import SimpleTestCase

WILDCARD_REGEX = r"^chrome-extension://[a-z]{32}$"


class ExtensionCorsScopeTest(SimpleTestCase):
    def test_cors_scoped_to_extension_path_only(self):
        # Must not grant extension origins CORS on the whole /api/ namespace.
        self.assertEqual(settings.CORS_URLS_REGEX, r"^/api/extension/.*$")

    def test_no_overbroad_extension_origin_regex(self):
        # Environment-independent contract. The CORS block is evaluated at import
        # time, and Django's test runner forces settings.DEBUG=False at runtime,
        # so the test cannot read DEBUG to tell which branch ran. What must hold
        # in *every* configuration is that the extension-origin regex list never
        # contains anything looser than the documented fixed-length wildcard:
        #   - ALLOWED_EXTENSION_IDS set  -> []   (explicit origins instead)
        #   - DEBUG, no ids              -> [WILDCARD_REGEX]
        #   - non-DEBUG, no ids          -> []
        # A broader pattern (e.g. chrome-extension://.*) sneaking in would fail.
        regexes = set(getattr(settings, "CORS_ALLOWED_ORIGIN_REGEXES", []))
        self.assertTrue(
            regexes.issubset({WILDCARD_REGEX}),
            f"Unexpected CORS extension origin regex(es): {regexes - {WILDCARD_REGEX}}",
        )
