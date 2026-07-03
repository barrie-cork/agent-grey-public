"""
Search Result Processor Service

Service for processing and normalising raw search results.
Handles URL validation, metadata extraction, and batch storage.
"""

import logging
from typing import List, Tuple, TypedDict
from urllib.parse import urlparse

from django.db import DatabaseError, transaction
from django.utils import timezone

from .base import BaseService

logger = logging.getLogger(__name__)


class ResultProcessorConfig(TypedDict):
    batch_size: int
    cache_timeout: int
    max_retries: int
    url_validation_timeout: int


class SearchResultProcessor(BaseService[ResultProcessorConfig]):
    """
    Service for processing and normalizing raw search results.
    Handles URL validation, metadata extraction, and batch storage.
    """

    SERVICE_NAME = "SearchResultProcessor"
    SERVICE_VERSION = "2.0.0"

    def get_default_config(self) -> ResultProcessorConfig:
        """Get default result processor configuration."""
        return {
            "batch_size": 50,
            "cache_timeout": 300,
            "max_retries": 3,
            "url_validation_timeout": 5,
        }

    def _initialize(self) -> None:
        """Initialize result processor resources."""
        pass  # No special initialization needed

    @property
    def batch_size(self) -> int:
        """Backward compatibility property for batch size."""
        return self.config["batch_size"]

    def health_check(self) -> bool:
        """Check if result processor is healthy."""
        try:
            # Test URL validation with a simple URL
            test_result = self._is_valid_url("https://example.com")
            return test_result
        except (
            Exception
        ) as e:  # Intentional broad catch: health check tests service availability
            self._handle_error(e, operation="health_check")
            return False

    def process_search_results(  # noqa: C901 - Complex result processing with batch handling and error tracking
        self,
        raw_results: List[dict],
        execution=None,
        session=None,  # Keep backward compatibility - session renamed to status_updater internally
        execution_round: int = 1,
    ) -> Tuple[int, List[str]]:
        """
        Process raw search results from Serper API.

        Args:
            raw_results: Raw results from Serper
            execution: SearchExecution instance
            session: SearchSession instance for backward compatibility
            execution_round: Which iteration of the search strategy produced these results

        Returns:
            Tuple of (processed_count, errors)
        """
        with self._measure_performance("process_search_results"):
            processed_count = 0
            errors = []

            # Alias session to status_updater for internal consistency
            status_updater = session

            if status_updater:
                if hasattr(status_updater, "update_status_detail"):
                    status_updater.update_status_detail("Processing search results...")
                else:
                    self.logger.debug(
                        "Status updater provided but no update_status_detail method"
                    )

            # Handle both execution object and string query_id
            if execution is not None and hasattr(execution, "query_id"):
                query_id = execution.query_id
            elif isinstance(execution, str):
                query_id = execution
            else:
                query_id = None

            # Resolve string execution ID to SearchExecution object for FK operations
            if isinstance(execution, str):
                from apps.serp_execution.models import SearchExecution

                try:
                    execution = SearchExecution.objects.get(id=execution)
                except SearchExecution.DoesNotExist:
                    self.logger.warning(
                        "SearchExecution not found for id %s, "
                        "skipping raw result storage",
                        execution,
                    )
                    execution = None

            self.logger.info(
                f"Processing {len(raw_results)} results for query {query_id}"
            )

            # Import here to avoid circular imports
            from apps.results_manager.models import ProcessedResult
            from apps.serp_execution.models import RawSearchResult

            # Inherit WF2 review mode from session config (falls back to SINGLE/1).
            # Derived once: the session is already loaded, so no per-result query.
            review_mode, min_reviewers_required = "SINGLE", 1
            config = getattr(status_updater, "current_configuration", None)
            if config is not None:
                review_mode, min_reviewers_required = config.review_mode_defaults

            # Process in batches for memory efficiency
            batch_size = self.config["batch_size"]
            for i in range(0, len(raw_results), batch_size):
                batch = raw_results[i : i + batch_size]

                try:
                    with transaction.atomic():
                        for position, result in enumerate(
                            batch, start=i + 1
                        ):  # Position is 1-based
                            try:
                                # Extract and validate result data
                                title = result.get("title", "").strip()
                                link = result.get("link", "").strip()
                                snippet = result.get("snippet", "").strip()

                                # Validate required fields
                                if not title or not link:
                                    errors.append(
                                        f"Missing title or link at position {position}"
                                    )
                                    continue

                                # Validate URL
                                if not self._is_valid_url(link):
                                    errors.append(
                                        f"Invalid URL at position {position}: {link}"
                                    )
                                    continue

                                # Create RawSearchResult if we have an execution
                                if execution:
                                    RawSearchResult.objects.create(
                                        execution=execution,
                                        position=position,
                                        title=title,
                                        link=link,
                                        snippet=snippet,
                                        raw_data=result,
                                    )

                                # Also create ProcessedResult if we have a session
                                if status_updater:
                                    # Detect document type from URL
                                    doc_type = self._detect_document_type(link)

                                    # Link to raw result if we created one
                                    raw_result = None
                                    if execution:
                                        # Get the raw result we just created
                                        raw_result = RawSearchResult.objects.filter(
                                            execution=execution, position=position
                                        ).first()

                                    ProcessedResult.objects.create(
                                        session=status_updater,
                                        raw_result=raw_result,
                                        title=title,
                                        url=link,
                                        snippet=snippet,
                                        document_type=doc_type,
                                        is_pdf=(doc_type == "pdf"),
                                        processing_status="success",
                                        review_mode=review_mode,
                                        min_reviewers_required=min_reviewers_required,
                                        processed_at=timezone.now(),
                                        execution_round=execution_round,
                                    )

                                processed_count += 1

                            except (
                                DatabaseError,
                                ValueError,
                                KeyError,
                                AttributeError,
                            ) as e:
                                error_msg = (
                                    f"Error processing result {position}: {str(e)}"
                                )
                                errors.append(error_msg)
                                self._handle_error(
                                    e,
                                    {"position": position, "result": result},
                                    "process_result",
                                )
                                continue

                except (DatabaseError, ValueError) as e:
                    error_msg = f"Batch processing error: {str(e)}"
                    errors.append(error_msg)
                    self._handle_error(e, {"batch_start": i}, "process_batch")
                    continue

            self.logger.info(
                f"Processed {processed_count} results with {len(errors)} errors"
            )
            return processed_count, errors

    def _is_valid_url(self, url: str) -> bool:
        """Validate URL format."""
        try:
            parsed = urlparse(url)
            return bool(parsed.scheme and parsed.netloc)
        except ValueError:
            return False

    def _detect_document_type(self, url: str) -> str:
        """Detect document type from URL."""
        url_lower = url.lower()
        if url_lower.endswith(".pdf"):
            return "pdf"
        elif url_lower.endswith((".doc", ".docx")):
            return "word"
        else:
            return "webpage"
