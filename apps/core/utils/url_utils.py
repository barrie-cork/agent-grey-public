"""
URL manipulation utilities for domain extraction and normalisation.

Consolidates domain extraction logic from:
- SerperProcessor._extract_domain()
- RawSearchResult.get_domain()
- ProcessedResult.get_display_url()
- ResultNormalizer inline extraction
"""

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def extract_domain(  # noqa: C901 - Complex URL parsing with multiple normalization options
    url: str,
    lowercase: bool = True,
    strip_www: bool = False,
    strip_auth: bool = True,
    sanitize: bool = False,
) -> str:
    """
    Extract domain from URL with comprehensive normalisation options.

    Args:
        url: URL string to extract domain from
        lowercase: Convert domain to lowercase (default: True)
        strip_www: Remove 'www.' prefix (default: False)
        strip_auth: Remove username:password@ credentials (default: True)
        sanitize: Remove potentially dangerous characters (default: False)

    Returns:
        Extracted domain string, empty string on error

    Examples:
        >>> extract_domain("https://www.nice.org.uk/guidance")
        'www.nice.org.uk'

        >>> extract_domain("https://user:pass@nice.org.uk")
        'nice.org.uk'

        >>> extract_domain("nice.org.uk", lowercase=False)
        'nice.org.uk'
    """
    try:
        if not url:
            return ""

        # Handle missing protocols (common in user input)
        if not url.startswith(("http://", "https://", "//")):
            url = "https://" + url

        # Parse URL
        parsed = urlparse(url)
        domain = parsed.netloc or ""

        if not domain:
            logger.debug(f"Could not extract domain from URL: {url}")
            return ""

        # Strip authentication credentials (username:password@domain)
        if strip_auth and "@" in domain:
            domain = domain.split("@")[-1]

        # Sanitize dangerous characters if requested
        if sanitize:
            # Allow only alphanumeric, dots, hyphens, and colons (for port)
            domain = re.sub(r"[^a-zA-Z0-9\.\-:]", "", domain)

        # Strip www prefix if requested
        if strip_www and domain.startswith("www."):
            domain = domain[4:]

        # Apply lowercase normalisation
        if lowercase:
            domain = domain.lower()

        # Validate domain format
        if not _is_valid_domain(domain):
            logger.debug(f"Invalid domain format: {domain}")
            return ""

        return domain

    except Exception as e:
        logger.debug(f"Error extracting domain from {url}: {e}")
        return ""


def _is_valid_domain(domain: str) -> bool:
    """
    Validate domain format.

    Args:
        domain: Domain string to validate

    Returns:
        True if domain format is valid, False otherwise

    Examples:
        >>> _is_valid_domain("nice.org.uk")
        True

        >>> _is_valid_domain("invalid..domain")
        False
    """
    if not domain:
        return False

    # Split port if present
    domain_part = domain.split(":")[0]

    # Basic validation: must contain at least one dot, valid characters
    domain_regex = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"

    return bool(re.match(domain_regex, domain_part))


def normalize_url(
    url: str, strip_params: bool = True, strip_fragment: bool = True
) -> str:
    """
    Normalise URL by removing tracking parameters and fragments.

    Args:
        url: URL to normalise
        strip_params: Remove tracking query parameters (default: True)
        strip_fragment: Remove URL fragment (default: True)

    Returns:
        Normalised URL string

    Examples:
        >>> normalize_url("https://nice.org.uk/page?utm_source=email#section")
        'https://nice.org.uk/page'
    """
    try:
        parsed = urlparse(url)

        # Remove tracking parameters
        if strip_params and parsed.query:
            from urllib.parse import parse_qs, urlencode

            tracking_params = {
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_content",
                "utm_term",
                "fbclid",
                "gclid",
                "ref",
                "source",
                "campaign",
            }

            query_params = parse_qs(parsed.query)
            clean_params = {
                k: v for k, v in query_params.items() if k not in tracking_params
            }

            query_string = urlencode(clean_params, doseq=True) if clean_params else ""
        else:
            query_string = parsed.query if not strip_params else ""

        # Rebuild URL
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc
        path = parsed.path
        fragment = "" if strip_fragment else parsed.fragment

        normalized = f"{scheme}://{netloc}{path}"
        if query_string:
            normalized += f"?{query_string}"
        if fragment:
            normalized += f"#{fragment}"

        return normalized

    except Exception as e:
        logger.warning(f"Failed to normalise URL {url}: {e}")
        return url
