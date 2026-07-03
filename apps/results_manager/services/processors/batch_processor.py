"""
Core batch processing logic for results processing pipeline.

This module contains the BatchProcessor class which handles the main
batch processing workflow including progress tracking and result processing.
"""

import logging
from typing import Any, Dict, List, Optional

from django.db import transaction

from apps.results_manager.constants import DocumentType, ErrorCategory
from apps.results_manager.models import ProcessedResult, ProcessingSession
from apps.search_strategy.models import SearchStrategy
from apps.serp_execution.constants import ExecutionStatusMessages
from apps.serp_execution.models import RawSearchResult

from .error_handler import ProcessingErrorHandler, ProcessingStatus
from .result_normalizer import ResultNormalizer

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles batch processing of search results."""

    def __init__(self, batch_size: int = 50):
        """
        Initialize the batch processor.

        Args:
            batch_size: Size of batches to process
        """
        self.batch_size = batch_size
        self.error_handler = ProcessingErrorHandler()
        self.normalizer = ResultNormalizer()
        self.logger = logging.getLogger(self.__class__.__name__)

    def process_batch(
        self,
        session_id: str,
        raw_result_ids: List[str],
        processing_session: ProcessingSession,
        batch_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process a batch of raw search results.

        Args:
            session_id: UUID string of the SearchSession
            raw_result_ids: List of RawSearchResult IDs to process
            processing_session: ProcessingSession instance
            batch_info: Optional batch metadata (batch_num, total_batches, etc.)

        Returns:
            Dictionary with batch processing results
        """
        batch_info = batch_info or {}
        batch_num = batch_info.get("batch_num", 1)
        total_batches = batch_info.get("total_batches", 1)

        self.logger.info(
            f"Processing batch {batch_num}/{total_batches} of {len(raw_result_ids)} results for session {session_id}"
        )

        try:
            # Update progress tracking
            processing_session.update_progress("url_normalization", 10)
            self._update_session_progress(session_id, batch_num, total_batches)

            # Retrieve strategy file type restrictions (once per batch)
            required_file_types = self._get_required_file_types(session_id)
            if required_file_types:
                self.logger.info(
                    f"File type filter active for session {session_id}: {required_file_types}"
                )

            # Retrieve review mode from session config (once per batch)
            review_mode, min_reviewers_required = self._get_review_mode_defaults(
                session_id
            )

            # Get raw results with related data
            raw_results = RawSearchResult.objects.filter(
                id__in=raw_result_ids
            ).select_related("execution", "execution__query")

            if not raw_results.exists():
                self.logger.warning(f"No raw results found for batch {batch_num}")
                return self._create_batch_result(0, 0, 0, [])

            # Process results
            results = self._process_results_batch(
                raw_results,
                session_id,
                batch_info,
                required_file_types,
                review_mode,
                min_reviewers_required,
            )

            # Update final progress
            processing_session.update_progress(
                stage="metadata_extraction",
                stage_progress=50,
                processed_count=processing_session.processed_count
                + results["processed_count"],
                error_count=processing_session.error_count + results["error_count"],
            )

            # Update session progress one more time
            self._update_session_progress(
                session_id, batch_num, total_batches, final=True
            )

            return results

        except Exception as e:
            self.logger.error(f"Batch processing failed for session {session_id}: {e}")
            return self._create_batch_result(0, 0, len(raw_result_ids), [])

    def _process_results_batch(  # noqa: C901 - Complex batch processing with error tracking and validation
        self,
        raw_results,
        session_id: str,
        batch_info: Dict[str, Any],
        required_file_types: Optional[List[str]] = None,
        review_mode: str = "SINGLE",
        min_reviewers_required: int = 1,
    ) -> Dict[str, Any]:
        """Process a batch of raw results with verification."""
        processed_count = 0
        error_count = 0
        filtered_count = 0
        errors = []

        # Enhanced batch logging
        self.logger.info(f"📊 BATCH PROCESSING SUMMARY for session {session_id}:")
        self.logger.info(f"   Starting batch of {len(raw_results)} raw results")

        # Get initial ProcessedResult count for verification
        initial_processed_count = ProcessedResult.objects.filter(
            session_id=session_id
        ).count()
        self.logger.info(
            f"   📈 Initial ProcessedResult count: {initial_processed_count}"
        )

        # Process each raw result
        for idx, raw_result in enumerate(raw_results, 1):
            try:
                # Update batch info with current item
                current_batch_info = batch_info.copy()
                current_batch_info.update(
                    {"item_num": idx, "total_items": len(raw_results)}
                )

                processed_result, is_new = self._process_single_result(
                    raw_result,
                    session_id,
                    current_batch_info,
                    review_mode,
                    min_reviewers_required,
                )
                if processed_result:
                    if not is_new:
                        # Duplicate URL - count as filtered but don't change database
                        filtered_count += 1
                    elif (
                        required_file_types
                        and processed_result.processing_status
                        == ProcessingStatus.SUCCESS
                        and not self._matches_file_type(
                            processed_result.document_type, required_file_types
                        )
                    ):
                        # File type mismatch -- mark as filtered
                        processed_result.processing_status = ProcessingStatus.FILTERED
                        processed_result.processing_error_category = (
                            ErrorCategory.FILE_TYPE_MISMATCH
                        )
                        processed_result.save(
                            update_fields=[
                                "processing_status",
                                "processing_error_category",
                            ]
                        )
                        self.logger.info(
                            f"🚫 FILE TYPE FILTERED: {processed_result.document_type} "
                            f"not in {required_file_types} for {processed_result.url[:80]}"
                        )
                        filtered_count += 1
                    else:
                        # Categorize result based on processing status
                        if (
                            processed_result.processing_status
                            == ProcessingStatus.SUCCESS
                        ):
                            processed_count += 1
                        elif (
                            processed_result.processing_status
                            == ProcessingStatus.FILTERED
                        ):
                            filtered_count += 1
                        elif (
                            processed_result.processing_status == ProcessingStatus.ERROR
                        ):
                            error_count += 1

                    # Mark raw result as processed
                    raw_result.is_processed = True
                    raw_result.save(update_fields=["is_processed"])
                else:
                    # Complete failure case
                    self.logger.error(
                        f"💀 CRITICAL: process_single_result returned None for {raw_result.id}"
                    )
                    error_count += 1

            except Exception as exc:
                # Handle processing error
                error_info = self.error_handler.handle_batch_error(
                    exc, raw_result, processing_session=None
                )
                errors.append(error_info)
                error_count += 1

        # Verify ProcessedResult count after batch
        final_processed_count = ProcessedResult.objects.filter(
            session_id=session_id
        ).count()

        # Calculate expected count: initial + new successes + errors (not filtered duplicates)
        expected_new_results = processed_count + error_count
        actual_new_results = final_processed_count - initial_processed_count

        self.logger.info(
            f"   📊 BATCH COMPLETE:\n"
            f"      ✅ SUCCESS: {processed_count} new unique results\n"
            f"      🔄 FILTERED: {filtered_count} duplicates\n"
            f"      ❌ ERRORS: {error_count} processing errors\n"
            f"      📈 Database verification:\n"
            f"         - Initial count: {initial_processed_count}\n"
            f"         - Final count: {final_processed_count}\n"
            f"         - Expected new: {expected_new_results}\n"
            f"         - Actual new: {actual_new_results}"
        )

        # Alert if counts don't match
        if actual_new_results != expected_new_results:
            self.logger.error(
                f"⚠️  DATABASE MISMATCH: Expected {expected_new_results} new ProcessedResults, "
                f"but found {actual_new_results}. Difference: {actual_new_results - expected_new_results}"
            )

        # Check if any SUCCESS results actually exist in database
        success_results_in_db = ProcessedResult.objects.filter(
            session_id=session_id, processing_status=ProcessingStatus.SUCCESS
        ).count()

        self.logger.info(
            f"   🔍 Verification: {success_results_in_db} ProcessedResults with SUCCESS status in database"
        )

        if processed_count > 0 and success_results_in_db == 0:
            self.logger.error(
                f"💥 CRITICAL BUG: Batch reported {processed_count} SUCCESS results, "
                f"but database shows 0 with SUCCESS status!"
            )

        return self._create_batch_result(
            processed_count, error_count, filtered_count, errors
        )

    def _process_single_result(
        self,
        raw_result: RawSearchResult,
        session_id: str,
        batch_info: Dict[str, Any],
        review_mode: str = "SINGLE",
        min_reviewers_required: int = 1,
    ) -> tuple[Optional[ProcessedResult], bool]:
        """
        Process a single raw search result with enhanced diagnostics.

        Args:
            raw_result: RawSearchResult to process
            session_id: Session ID for tracking
            batch_info: Batch processing context

        Returns:
            Tuple of (ProcessedResult or None, is_new). is_new is True when
            a new record was created, False when a duplicate URL was found.
            Returns (None, False) on error.
        """
        try:
            # Normalize the result data
            normalized_data = self.normalizer.normalize_result(raw_result)
            self.normalizer.extract_metadata(normalized_data)

            # Enhanced diagnostic logging
            self.logger.info(
                f"🔍 PROCESSING: RawResult {raw_result.id} | "
                f"URL: {normalized_data['url'][:80]} | "
                f"Session: {session_id}"
            )

            # Create or update ProcessedResult
            with transaction.atomic():
                processed_result, created = ProcessedResult.objects.get_or_create(
                    session_id=session_id,
                    url=normalized_data["url"],
                    defaults={
                        "title": normalized_data["title"],
                        "snippet": normalized_data["snippet"],
                        "document_type": normalized_data["document_type"],
                        "is_pdf": normalized_data["document_type"] == DocumentType.PDF,
                        "processing_status": ProcessingStatus.SUCCESS,
                        "review_mode": review_mode,
                        "min_reviewers_required": min_reviewers_required,
                    },
                )

                if not created:
                    # Duplicate URL found - DO NOT modify the existing result
                    self.logger.info(
                        f"🔄 DUPLICATE: Found existing result ID {processed_result.id} "
                        f"(Status: {processed_result.processing_status}) for URL {normalized_data['url'][:80]} "
                        f"- preserving original status, counting as filtered"
                    )
                    return processed_result, False

                # SUCCESS: New result created
                self.logger.info(
                    f"✅ SUCCESS: Created ProcessedResult {processed_result.id} | "
                    f"Status: {processed_result.processing_status} | "
                    f"Title: {processed_result.title[:50]}..."
                )

                # Verify the result was actually saved with SUCCESS status
                if processed_result.processing_status != ProcessingStatus.SUCCESS:
                    self.logger.error(
                        f"⚠️  WARNING: ProcessedResult {processed_result.id} created with unexpected status: "
                        f"{processed_result.processing_status} (expected SUCCESS)"
                    )

                return processed_result, True

        except Exception as e:
            self.logger.error(
                f"💥 ERROR processing RawResult {raw_result.id}: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            # Create an error result
            try:
                error_result = ProcessedResult.objects.create(
                    session_id=session_id,
                    url=raw_result.link,
                    title=raw_result.title or "Processing Error",
                    snippet=f"Error: {str(e)[:200]}",
                    document_type=DocumentType.WEBPAGE,
                    processing_status=ProcessingStatus.ERROR,
                    review_mode=review_mode,
                    min_reviewers_required=min_reviewers_required,
                )
                self.logger.warning(
                    f"📝 ERROR RESULT: Created error ProcessedResult "
                    f"{error_result.id} for failed RawResult {raw_result.id}"
                )
                return error_result, True
            except Exception as creation_error:
                self.logger.error(
                    f"💀 FATAL: Failed to create error result for {raw_result.id}: {creation_error}",
                    exc_info=True,
                )
                return None, False

    def _get_review_mode_defaults(self, session_id: str) -> tuple[str, int]:
        """Read review_mode and min_reviewers_required from the session config.

        Reads the session's active ReviewConfiguration once per batch to avoid
        per-result queries. Mirrors the WF2-aware logic in ManualResultService.

        Returns:
            Tuple of (review_mode string, min_reviewers_required int).
            Falls back to ("SINGLE", 1) on any error or if no WF2 config found.
        """
        try:
            from apps.review_manager.models import SearchSession

            session = SearchSession.objects.select_related("current_configuration").get(
                id=session_id
            )
            config = session.current_configuration
            if config is not None:
                return config.review_mode_defaults
        except Exception as e:
            self.logger.warning(
                f"Could not retrieve review configuration for session {session_id}: {e}"
            )
        return "SINGLE", 1

    def _get_required_file_types(self, session_id: str) -> Optional[List[str]]:
        """Get file type restrictions from the session's search strategy."""
        try:
            strategy = SearchStrategy.objects.filter(session_id=session_id).first()
            if strategy and strategy.search_config:
                file_types = strategy.search_config.get("file_types", [])
                return file_types if file_types else None
        except Exception as e:
            self.logger.warning(f"Could not retrieve file type config: {e}")
        return None

    @staticmethod
    def _matches_file_type(document_type: str, required_file_types: List[str]) -> bool:
        """Check if a document type matches the required file types."""
        doc_type_to_file_type = {
            DocumentType.PDF: "pdf",
            DocumentType.WORD: "doc",
        }
        file_type = doc_type_to_file_type.get(document_type)
        return file_type is not None and file_type in required_file_types

    def _update_session_progress(
        self, session_id: str, batch_num: int, total_batches: int, final: bool = False
    ) -> None:
        """Update session progress for batch processing."""
        try:
            from apps.review_manager.models import SearchSession

            session = SearchSession.objects.get(id=session_id)
            session.update_status_detail(ExecutionStatusMessages.DENORMALIZING_URLS)

        except Exception as e:
            self.logger.warning(f"Progress broadcast failed: {e}")

    def _create_batch_result(
        self,
        processed_count: int,
        error_count: int,
        filtered_count: int,
        errors: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create standardized batch result dictionary."""
        return {
            "processed_count": processed_count,
            "error_count": error_count,
            "filtered_count": filtered_count,
            "total_processed": processed_count + error_count + filtered_count,
            "success_rate": (
                processed_count / max(processed_count + error_count + filtered_count, 1)
            )
            * 100,
            "errors": errors,
            "error_summary": (
                self.error_handler.get_error_summary(errors) if errors else None
            ),
        }

    def validate_batch_parameters(self, raw_result_ids: List[str]) -> None:
        """
        Validate batch processing parameters.

        Args:
            raw_result_ids: List of raw result IDs to validate

        Raises:
            ValueError: If parameters are invalid
        """
        if not raw_result_ids:
            raise ValueError("raw_result_ids cannot be empty")

        if len(raw_result_ids) > self.batch_size * 2:
            self.logger.warning(
                f"Batch size {len(raw_result_ids)} exceeds recommended maximum {self.batch_size * 2}"
            )

        # Validate that IDs are strings/UUIDs
        for result_id in raw_result_ids:
            if not isinstance(result_id, str) or len(result_id) == 0:
                raise ValueError(f"Invalid raw_result_id: {result_id}")

    def get_batch_stats(self) -> Dict[str, Any]:
        """Get current batch processor statistics."""
        return {
            "batch_size": self.batch_size,
            "processor_name": self.__class__.__name__,
            "error_handler": self.error_handler.__class__.__name__,
            "normalizer": self.normalizer.__class__.__name__,
        }
