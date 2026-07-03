"""
URL Deduplication Service

Conservative URL-only deduplication service.
Implements cross-query deduplication as specified in CORE_REQUIREMENTS.md.
"""

import logging
from typing import List, TypedDict
from urllib.parse import parse_qs, urlencode, urlparse

from django.db import transaction

from .base import BaseService

logger = logging.getLogger(__name__)


class DeduplicationConfig(TypedDict):
    tracking_params: List[str]
    cache_timeout: int
    batch_size: int


class URLDeduplicationService(BaseService[DeduplicationConfig]):
    """
    Conservative URL-only deduplication service.
    Implements cross-query deduplication as specified in CORE_REQUIREMENTS.md.
    """

    SERVICE_NAME = "URLDeduplicationService"
    SERVICE_VERSION = "2.0.0"

    def get_default_config(self) -> DeduplicationConfig:
        """Get default deduplication configuration."""
        return {
            "tracking_params": [
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_term",
                "utm_content",
                "fbclid",
                "gclid",
                "msclkid",
                "mc_eid",
                "mc_cid",
                "_ga",
                "_gl",
                "ref",
                "referrer",
            ],
            "cache_timeout": 3600,
            "batch_size": 100,
        }

    def _initialize(self) -> None:
        """Initialize deduplication service."""
        # Convert tracking params list to set for faster lookups
        self._tracking_params = set(self.config["tracking_params"])

    def health_check(self) -> bool:
        """Check if deduplication service is healthy."""
        try:
            # Test URL normalization with a sample URL
            test_url = "https://example.com/test?utm_source=test&param=value"
            normalized = self.normalize_url(test_url)
            return "utm_source" not in normalized
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def normalize_url(self, url: str) -> str:
        """
        Conservative URL normalization for deduplication.

        Args:
            url: Original URL

        Returns:
            Normalized URL for comparison
        """
        if not url:
            return ""

        try:
            parsed = urlparse(url.lower().strip())

            # Parse and filter query parameters
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            clean_params = {
                k: v for k, v in query_params.items() if k not in self._tracking_params
            }

            # Rebuild query string
            clean_query = urlencode(clean_params, doseq=True)

            # Normalize path (remove trailing slash, but keep meaningful paths)
            path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

            # Remove www prefix for comparison
            netloc = parsed.netloc
            if netloc.startswith("www."):
                netloc = netloc[4:]

            # Reconstruct normalized URL
            normalized = f"{parsed.scheme}://{netloc}{path}"
            if clean_query:
                normalized += f"?{clean_query}"

            return normalized

        except Exception as e:
            self._handle_error(e, {"url": url[:100]}, "normalize_url")
            return url  # Return original if normalization fails

    def deduplicate_session_results(self, session) -> dict:
        """
        Remove duplicate results across all queries in session.

        Args:
            session: SearchSession instance

        Returns:
            Dict with deduplication stats:
                - total_duplicates: int
                - per_iteration: {round: {"total": int, "duplicates": int}}
            For backward compatibility, the dict also supports int() conversion.
        """
        with self._measure_performance("deduplicate_session_results"):
            if hasattr(session, "update_status_detail"):
                session.update_status_detail("Conducting cross-query deduplication...")
            else:
                self.logger.debug("Session provided but no update_status_detail method")

            # Import here to avoid circular imports
            from apps.results_manager.models import ProcessedResult

            seen_urls = set()
            duplicates_removed = 0
            per_iteration: dict[int, dict[str, int]] = {}

            # Process all results in session, ordered by created_at (first come, first serve)
            results = ProcessedResult.objects.filter(session=session).order_by(
                "created_at"
            )

            # Get count safely - handle both QuerySet and list
            from django.db.models import QuerySet

            total_results = (
                results.count() if isinstance(results, QuerySet) else len(results)
            )
            self.logger.info(
                f"Deduplicating {total_results} results for session {session.id}"
            )

            with transaction.atomic():
                for result in results:
                    # Track per-iteration stats
                    round_num = getattr(result, "execution_round", 1)
                    if round_num not in per_iteration:
                        per_iteration[round_num] = {"total": 0, "duplicates": 0}
                    per_iteration[round_num]["total"] += 1

                    canonical_url = self.normalize_url(result.url)  # Use url not link

                    if canonical_url in seen_urls:
                        # Mark as filtered (duplicate) using existing processing_status field
                        result.processing_status = "filtered"
                        result.processing_error_category = "duplicate"
                        result.processing_error_message = "URL duplicate across queries"
                        result.save(
                            update_fields=[
                                "processing_status",
                                "processing_error_category",
                                "processing_error_message",
                            ]
                        )
                        duplicates_removed += 1
                        per_iteration[round_num]["duplicates"] += 1

                        self.logger.debug(f"Duplicate found: {result.url}")
                    else:
                        seen_urls.add(canonical_url)
                        # Ensure non-duplicates are marked as success
                        if (
                            result.processing_status == "filtered"
                            and result.processing_error_category == "duplicate"
                        ):
                            result.processing_status = "success"
                            result.processing_error_category = ""
                            result.processing_error_message = ""
                            result.save(
                                update_fields=[
                                    "processing_status",
                                    "processing_error_category",
                                    "processing_error_message",
                                ]
                            )

            if hasattr(session, "update_status_detail"):
                session.update_status_detail(
                    f"Removed {duplicates_removed} URL duplicates"
                )
            self.logger.info(
                f"Deduplication complete: {duplicates_removed} duplicates found"
            )

            return {
                "total_duplicates": duplicates_removed,
                "per_iteration": per_iteration,
            }
