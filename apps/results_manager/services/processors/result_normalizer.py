"""
Result normalization and metadata extraction.

This module handles URL normalization, content extraction, and metadata
processing for raw search results.
"""

import logging
import re
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from apps.core.utils import extract_domain
from apps.results_manager.constants import DocumentType

logger = logging.getLogger(__name__)


class ResultNormalizer:
    """Handles URL normalization and content extraction for search results."""

    # Document type detection patterns
    PDF_PATTERNS = [r"\.pdf(\?|$)", r"filetype.*pdf", r"application/pdf"]
    WORD_PATTERNS = [r"\.docx?(\?|$)", r"filetype.*(doc|docx)", r"application/msword"]

    # Organization extraction patterns
    ORG_PATTERNS = {
        "academic": [
            r"\.edu(\.|/)",
            r"\.ac\.(uk|au|nz|za)(\.|/)",
            r"university",
            r"college",
            r"research",
        ],
        "government": [
            r"\.gov(\.|/)",
            r"\.gov\.(uk|au|ca)(\.|/)",
            r"department",
            r"ministry",
        ],
        "organization": [r"\.org(\.|/)", r"foundation", r"institute"],
    }

    def __init__(self):
        """Initialize the result normalizer."""
        self.logger = logging.getLogger(self.__class__.__name__)

    def normalize_url(self, url: str) -> str:
        """
        Normalize a URL by removing tracking parameters and fragments.

        Args:
            url: Raw URL to normalize

        Returns:
            Normalized URL string
        """
        try:
            parsed = urlparse(url)

            # Remove common tracking parameters
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

            if parsed.query:
                query_params = parse_qs(parsed.query)
                # Remove tracking parameters
                clean_params = {
                    k: v for k, v in query_params.items() if k not in tracking_params
                }

                # Rebuild query string
                if clean_params:
                    from urllib.parse import urlencode

                    query_string = urlencode(clean_params, doseq=True)
                else:
                    query_string = ""
            else:
                query_string = ""

            # Rebuild URL without fragment and with clean query
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if query_string:
                normalized += f"?{query_string}"

            return normalized

        except Exception as e:
            self.logger.warning(f"Failed to normalize URL {url}: {e}")
            return url  # Return original URL if normalization fails

    def detect_document_type(self, url: str, title: str = "", snippet: str = "") -> str:
        """
        Detect the document type based on URL, title, and snippet content.

        Args:
            url: URL of the document
            title: Title of the document
            snippet: Snippet or description text

        Returns:
            Document type constant (pdf, word, webpage)
        """
        content_text = f"{url} {title} {snippet}".lower()

        # Check for PDF indicators
        if any(re.search(pattern, content_text) for pattern in self.PDF_PATTERNS):
            return DocumentType.PDF

        # Check for Word document indicators
        if any(re.search(pattern, content_text) for pattern in self.WORD_PATTERNS):
            return DocumentType.WORD

        # Default to webpage
        return DocumentType.WEBPAGE

    def extract_organization(self, url: str) -> str:
        """
        Extract organization information from URL.

        Args:
            url: URL to analyze

        Returns:
            Extracted organization name or domain
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]

            # Check for organization type patterns
            for org_type, patterns in self.ORG_PATTERNS.items():
                if any(re.search(pattern, domain) for pattern in patterns):
                    # Return a more specific organization name if possible
                    domain_parts = domain.split(".")
                    if len(domain_parts) >= 2:
                        return domain_parts[0].title()  # Capitalize first part

            # Default to domain name
            domain_parts = domain.split(".")
            if domain_parts:
                return domain_parts[0].title()

            return domain

        except Exception as e:
            self.logger.warning(f"Failed to extract organization from {url}: {e}")
            return "Unknown"

    def normalize_result(self, raw_result) -> Dict[str, Any]:
        """
        Normalize a raw search result into standardized metadata.

        Args:
            raw_result: RawSearchResult instance

        Returns:
            Dictionary with normalized result data
        """
        try:
            normalized_data = {
                "url": self.normalize_url(raw_result.link),
                "title": raw_result.title or "Untitled",
                "snippet": raw_result.snippet or "",
                "document_type": self.detect_document_type(
                    raw_result.link, raw_result.title or "", raw_result.snippet or ""
                ),
                "organization": self.extract_organization(raw_result.link),
                "original_url": raw_result.link,
                "search_query": (
                    raw_result.execution.query.query_text
                    if raw_result.execution
                    else None
                ),
            }

            # Add any additional metadata from raw result
            if hasattr(raw_result, "date") and raw_result.date:
                normalized_data["published_date"] = raw_result.date

            if hasattr(raw_result, "displayed_link") and raw_result.displayed_link:
                normalized_data["display_url"] = raw_result.displayed_link

            return normalized_data

        except Exception as e:
            self.logger.error(f"Failed to normalize result {raw_result.id}: {e}")
            # Return minimal normalized data
            return {
                "url": raw_result.link,
                "title": raw_result.title or "Untitled",
                "snippet": raw_result.snippet or "",
                "document_type": DocumentType.WEBPAGE,
                "organization": "Unknown",
                "original_url": raw_result.link,
                "search_query": None,
            }

    def extract_metadata(self, normalized_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract additional metadata from normalized result data.

        Args:
            normalized_data: Dictionary with normalized result data

        Returns:
            Dictionary with extracted metadata
        """
        metadata = {
            "url_length": len(normalized_data["url"]),
            "title_length": len(normalized_data["title"]),
            "snippet_length": len(normalized_data["snippet"]),
            "is_academic": self._is_academic_source(normalized_data["url"]),
            "is_government": self._is_government_source(normalized_data["url"]),
            "domain": extract_domain(normalized_data["url"], lowercase=True),
        }

        return metadata

    def _is_academic_source(self, url: str) -> bool:
        """Check if URL appears to be from an academic source."""
        return any(
            re.search(pattern, url.lower()) for pattern in self.ORG_PATTERNS["academic"]
        )

    def _is_government_source(self, url: str) -> bool:
        """Check if URL appears to be from a government source."""
        return any(
            re.search(pattern, url.lower())
            for pattern in self.ORG_PATTERNS["government"]
        )
