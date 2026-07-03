"""
Enhanced result processor facade for serp_execution slice.
Provides additional functionality while leveraging the core ResultProcessor.
"""

import logging
from urllib.parse import urlparse

from django.db import IntegrityError, transaction
from django.db.models import Max

from apps.core.services.simple_services import (
    SearchResultProcessor as CoreResultProcessor,
)

logger = logging.getLogger(__name__)


class ResultProcessor(CoreResultProcessor):
    """Enhanced result processor extending core functionality with SERP-specific features."""

    def __init__(self, batch_size: int = 50):
        """Initialize with core functionality and SERP-specific enhancements."""
        # Initialize the base class first
        super().__init__()
        # Override the config's batch_size if different from default
        if batch_size != self.config["batch_size"]:
            self.config["batch_size"] = batch_size
        logger.info("Initialized enhanced ResultProcessor using core implementation")

    def process_search_results(  # noqa: C901 - Result processing
        self, execution_id: str, raw_results: list, batch_size: int | None = None
    ):
        """
        Enhanced search results processing with SERP-specific database integration.

        Args:
            execution_id: SearchExecution ID
            raw_results: List of raw results from Serper API
            batch_size: Batch size for processing (optional, uses instance default)

        Returns:
            Tuple of (processed_count, duplicate_count, errors)
        """
        batch_size = batch_size or self.batch_size
        processed_count = 0
        duplicate_count = 0
        errors = []

        logger.info(
            f"Starting enhanced processing of {len(raw_results)} raw results for execution {execution_id}"
        )

        # Use core processing functionality first
        try:
            _core_processed, core_errors = super().process_search_results(
                raw_results, execution=None, session=None
            )
            logger.info(
                f"Core processing completed: {_core_processed} results, {len(core_errors)} errors"
            )

            # Add core errors to our error list
            errors.extend(core_errors)

        except Exception as e:
            logger.error(f"Core processing failed: {str(e)}")
            errors.append(f"Core processing failed: {str(e)}")

        # Enhanced SERP-specific processing
        try:
            # Import here to avoid circular imports
            from apps.serp_execution.models import RawSearchResult

            logger.debug(
                f"Execution ID type: {type(execution_id)}, value: {execution_id}"
            )

            # Derive the next free position from existing rows so re-processing,
            # pagination, and retries append after what is already stored rather
            # than reusing 1-based list offsets (which collide with the
            # unique_execution_position constraint on (execution, position)).
            next_position = self._next_available_position(RawSearchResult, execution_id)

            # Process results in batches with SERP-specific enhancements
            for i in range(0, len(raw_results), batch_size):
                batch = raw_results[i : i + batch_size]
                logger.debug(
                    f"Processing SERP batch {i // batch_size + 1}: {len(batch)} results"
                )

                for result in batch:
                    processed_result = self._process_single_result(result)
                    if not processed_result:
                        logger.warning("Skipped result due to processing failure")
                        continue

                    # Check if result already exists (from core processing or a
                    # prior run) before consuming a position number.
                    existing = RawSearchResult.objects.filter(
                        execution_id=execution_id,
                        link=processed_result["url"],
                    ).first()
                    if existing:
                        duplicate_count += 1
                        logger.debug(
                            f"Duplicate result found: {processed_result['url'][:100]}"
                        )
                        continue

                    # Give each row its own savepoint so an IntegrityError on one
                    # row rolls back only that row and cannot poison the rest of
                    # the batch (which previously raised TransactionManagementError).
                    try:
                        with transaction.atomic():
                            RawSearchResult.objects.create(
                                execution_id=execution_id,
                                position=next_position,
                                title=processed_result["title"],
                                link=processed_result["url"],
                                snippet=processed_result["snippet"],
                                raw_data=result,
                                has_pdf=processed_result["is_pdf"],
                                display_link=processed_result["domain"],
                            )
                    except IntegrityError:
                        # A concurrent run may have stored this URL and/or claimed
                        # this position between the dedup check above and this
                        # insert. Re-check the URL first so a concurrent insert is
                        # counted as a duplicate rather than creating a second row,
                        # then recompute the position before retrying.
                        if RawSearchResult.objects.filter(
                            execution_id=execution_id,
                            link=processed_result["url"],
                        ).exists():
                            duplicate_count += 1
                            logger.debug(
                                f"Duplicate found on retry: {processed_result['url'][:100]}"
                            )
                            continue
                        next_position = self._next_available_position(
                            RawSearchResult, execution_id
                        )
                        try:
                            with transaction.atomic():
                                RawSearchResult.objects.create(
                                    execution_id=execution_id,
                                    position=next_position,
                                    title=processed_result["title"],
                                    link=processed_result["url"],
                                    snippet=processed_result["snippet"],
                                    raw_data=result,
                                    has_pdf=processed_result["is_pdf"],
                                    display_link=processed_result["domain"],
                                )
                        except IntegrityError as retry_error:
                            error_msg = (
                                "Failed to save enhanced result to database at "
                                f"position {next_position}: {str(retry_error)}"
                            )
                            errors.append(error_msg)
                            logger.error(
                                error_msg,
                                extra={
                                    "position": next_position,
                                    "result": result,
                                    "execution_id": execution_id,
                                },
                                exc_info=True,
                            )
                            continue

                    processed_count += 1
                    next_position += 1
                    logger.debug(
                        f"Saved enhanced result #{processed_count}: {processed_result['url'][:100]}"
                    )

            # Verification step
            try:
                saved_count = RawSearchResult.objects.filter(
                    execution_id=execution_id
                ).count()
                logger.info(
                    f"Enhanced verification: Found {saved_count} results in database for execution {execution_id}"
                )
            except Exception as verify_error:
                logger.error(f"Failed to verify enhanced results: {str(verify_error)}")

        except Exception as e:
            error_msg = f"Enhanced processing failed: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)

        logger.info(
            f"Enhanced processing complete: {processed_count} new results, "
            f"{duplicate_count} duplicates, {len(errors)} errors"
        )
        return processed_count, duplicate_count, errors

    @staticmethod
    def _next_available_position(raw_result_model, execution_id: str) -> int:
        """Return the next free 1-based position for an execution's raw results.

        Derives the value from the current maximum so newly stored rows append
        after any existing ones, avoiding collisions with the
        unique_execution_position constraint on (execution, position).
        """
        current_max = raw_result_model.objects.filter(
            execution_id=execution_id
        ).aggregate(max_position=Max("position"))["max_position"]
        return (current_max or 0) + 1

    def process_raw_results(self, raw_results: dict):
        """
        Legacy method: Process raw results without saving to database.

        Args:
            raw_results: Raw results dict from Serper API (with 'organic' key)

        Returns:
            List of processed result dictionaries
        """
        if not raw_results or "organic" not in raw_results:
            logger.warning("No organic results found in raw_results")
            return []

        processed_results = []

        for idx, result in enumerate(raw_results.get("organic", [])):
            processed = self._process_single_result(result)
            if processed:
                processed["position"] = idx + 1
                processed_results.append(processed)

        return processed_results

    def _process_single_result(self, result: dict):
        """
        Enhanced single result processing using core functionality.

        Args:
            result: Single result from Serper API

        Returns:
            Processed result dictionary or None if processing fails
        """
        # Use core URL validation
        url = result.get("link", "")
        if not url or not self._is_valid_url(url):
            logger.warning(f"Invalid or missing URL in result: {url}")
            return None

        try:
            # Extract basic metadata with enhanced processing
            title = result.get("title", "").strip()
            snippet = result.get("snippet", "").strip()

            # Process domain using core functionality
            domain = ""
            try:
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.replace("www.", "")
            except Exception as e:
                logger.warning(f"Failed to parse URL {url}: {str(e)}")

            # Enhanced document type detection
            is_pdf = url.lower().endswith(".pdf") or "[PDF]" in title.upper()
            doc_type = "pdf" if is_pdf else "website"

            # Create enhanced result dictionary
            processed_result = {
                "url": url,
                "title": title or "Untitled",
                "snippet": snippet,
                "domain": domain,
                "is_pdf": is_pdf,
                "document_type": doc_type,
                "raw_data": result,
            }

            return processed_result

        except Exception as e:
            logger.error(f"Failed to process enhanced single result: {str(e)}")
            return None

    def extract_metadata(self, result: dict):
        """
        Extract metadata from processed result.

        Args:
            result: Processed result dictionary

        Returns:
            Metadata dictionary
        """
        metadata = {
            "has_full_text": False,
            "publication_year": None,
            "file_size": None,
        }

        # Check for PDF indicators
        if result.get("is_pdf"):
            metadata["has_full_text"] = True

        # Try to extract year from title or snippet
        import re

        year_pattern = r"\b(19|20)\d{2}\b"

        text_to_search = f"{result.get('title', '')} {result.get('snippet', '')}"
        year_matches = re.findall(year_pattern, text_to_search)

        if year_matches:
            # Get the most recent year
            years = [int(y) for y in year_matches if y.startswith(("19", "20"))]
            if years:
                metadata["publication_year"] = max(years)

        return metadata

    def validate_url(self, url: str) -> bool:
        """
        Legacy compatibility wrapper for URL validation.

        Args:
            url: URL to validate

        Returns:
            True if URL is valid
        """
        # Use core implementation
        return self._is_valid_url(url)

    def calculate_processing_stats(
        self, total_results: int, processed: int, duplicates: int
    ):
        """
        Calculate processing statistics.

        Args:
            total_results: Total number of results
            processed: Number of processed results
            duplicates: Number of duplicates found

        Returns:
            Statistics dictionary
        """
        return {
            "total_results": total_results,
            "processed_count": processed,
            "duplicate_count": duplicates,
            "unique_count": processed - duplicates,
            "success_rate": (
                (processed / total_results * 100) if total_results > 0 else 0
            ),
            "duplicate_rate": (duplicates / processed * 100) if processed > 0 else 0,
        }
