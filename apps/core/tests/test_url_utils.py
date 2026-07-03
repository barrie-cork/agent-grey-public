"""
Unit tests for URL utilities.
"""

from django.test import TestCase

from apps.core.utils.url_utils import extract_domain, normalize_url, _is_valid_domain


class ExtractDomainTestCase(TestCase):
    """Test domain extraction functionality."""

    def test_basic_domain_extraction(self):
        """Test basic domain extraction from HTTPS URL."""
        self.assertEqual(
            extract_domain("https://www.nice.org.uk/guidance"), "www.nice.org.uk"
        )

    def test_lowercase_normalization(self):
        """Test domain is lowercased by default."""
        self.assertEqual(extract_domain("https://WWW.NICE.ORG.UK"), "www.nice.org.uk")

    def test_no_lowercase(self):
        """Test domain preserves case when lowercase=False."""
        self.assertEqual(
            extract_domain("https://WWW.NICE.ORG.UK", lowercase=False),
            "WWW.NICE.ORG.UK",
        )

    def test_strip_auth_credentials(self):
        """Test authentication credentials are stripped."""
        self.assertEqual(
            extract_domain("https://user:password@nice.org.uk"), "nice.org.uk"
        )

    def test_missing_protocol(self):
        """Test URL without protocol is handled."""
        self.assertEqual(extract_domain("nice.org.uk"), "nice.org.uk")

    def test_with_port(self):
        """Test domain with port number."""
        self.assertEqual(extract_domain("https://localhost:8000"), "localhost:8000")

    def test_empty_url(self):
        """Test empty URL returns empty string."""
        self.assertEqual(extract_domain(""), "")

    def test_invalid_url(self):
        """Test invalid URL returns empty string."""
        # Test with special characters that make domain invalid
        self.assertEqual(extract_domain("http://invalid_domain.com"), "")
        # Test with starting hyphen
        self.assertEqual(extract_domain("http://-invalid.com"), "")

    def test_strip_www(self):
        """Test www prefix is stripped when requested."""
        self.assertEqual(
            extract_domain("https://www.nice.org.uk", strip_www=True), "nice.org.uk"
        )

    def test_http_protocol(self):
        """Test HTTP (non-secure) URLs work."""
        self.assertEqual(extract_domain("http://example.com"), "example.com")

    def test_subdomain(self):
        """Test subdomain extraction."""
        self.assertEqual(extract_domain("https://api.github.com"), "api.github.com")

    def test_complex_url_with_path(self):
        """Test domain extraction from URL with path and query."""
        self.assertEqual(
            extract_domain("https://www.bmj.com/content/123/456/article?page=1"),
            "www.bmj.com",
        )


class ValidateDomainTestCase(TestCase):
    """Test domain validation logic."""

    def test_valid_domain(self):
        """Test valid domain passes validation."""
        self.assertTrue(_is_valid_domain("nice.org.uk"))

    def test_valid_domain_with_port(self):
        """Test valid domain with port passes validation."""
        self.assertTrue(_is_valid_domain("localhost:8000"))

    def test_invalid_double_dots(self):
        """Test domain with double dots fails validation."""
        self.assertFalse(_is_valid_domain("invalid..domain"))

    def test_invalid_starts_with_dash(self):
        """Test domain starting with dash fails validation."""
        self.assertFalse(_is_valid_domain("-invalid.com"))

    def test_empty_domain(self):
        """Test empty domain fails validation."""
        self.assertFalse(_is_valid_domain(""))

    def test_single_label_domain(self):
        """Test single-label domain (localhost) passes validation."""
        self.assertTrue(_is_valid_domain("localhost"))

    def test_valid_subdomain(self):
        """Test valid subdomain passes validation."""
        self.assertTrue(_is_valid_domain("api.example.com"))


class NormalizeURLTestCase(TestCase):
    """Test URL normalisation functionality."""

    def test_strip_tracking_params(self):
        """Test tracking parameters are removed."""
        url = "https://nice.org.uk/page?utm_source=email&id=123"
        normalized = normalize_url(url)
        self.assertIn("id=123", normalized)
        self.assertNotIn("utm_source", normalized)

    def test_strip_fragment(self):
        """Test URL fragment is removed."""
        url = "https://nice.org.uk/page#section"
        normalized = normalize_url(url)
        self.assertNotIn("#section", normalized)

    def test_keep_valid_params(self):
        """Test non-tracking parameters are preserved."""
        url = "https://nice.org.uk/page?id=123&lang=en"
        normalized = normalize_url(url)
        self.assertIn("id=123", normalized)
        self.assertIn("lang=en", normalized)

    def test_multiple_tracking_params(self):
        """Test multiple tracking parameters are removed."""
        url = (
            "https://nice.org.uk/page?utm_source=email&utm_campaign=test&fbclid=abc123"
        )
        normalized = normalize_url(url)
        self.assertNotIn("utm_source", normalized)
        self.assertNotIn("utm_campaign", normalized)
        self.assertNotIn("fbclid", normalized)

    def test_no_params(self):
        """Test URL without parameters is unchanged."""
        url = "https://nice.org.uk/page"
        normalized = normalize_url(url)
        self.assertEqual(normalized, url)

    def test_keep_fragment_option(self):
        """Test fragment can be preserved when requested."""
        url = "https://nice.org.uk/page#section"
        normalized = normalize_url(url, strip_fragment=False)
        self.assertIn("#section", normalized)

    def test_keep_params_option(self):
        """Test parameters can be preserved when requested."""
        url = "https://nice.org.uk/page?utm_source=email"
        normalized = normalize_url(url, strip_params=False)
        self.assertIn("utm_source", normalized)
