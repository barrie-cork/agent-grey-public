"""
Batch processing tasks for results processing pipeline.

This module contains tasks responsible for processing results in batches,
deduplication, and finalization of the processing workflow.
"""

import logging

from celery import shared_task
from django.db import transaction

from apps.results_manager.utils.progress_validation import ensure_valid_counts
from apps.serp_execution.constants import ExecutionStatusMessages

from ..models import ProcessingSession
from ..services.processing_analytics_service import ProcessingAnalyticsService
from ..services.processors import (
    BatchProcessor,
    ProcessingErrorHandler,
    ResultNormalizer,
)
from ..validation import validate_session_id

processing_analytics_service = ProcessingAnalyticsService()

# Processors for batch processing
batch_processor = BatchProcessor(batch_size=50)
error_handler = ProcessingErrorHandler()
result_normalizer = ResultNormalizer()

get_processing_statistics = processing_analytics_service.get_processing_statistics

logger = logging.getLogger(__name__)

# Import constants from parent package
MAX_RETRIES = 3
RETRY_DELAY = 60  # seconds

# Legacy processing status and error categorization now handled by ProcessingErrorHandler


@shared_task(bind=True, max_retries=MAX_RETRIES)
def process_batch_task(
    self,
    session_id: str,
    processing_session_id: str,
    raw_result_ids: list,
    batch_num: int = 1,
    total_batches: int = 1,
):
    """
    Process a batch of raw results using the improved BatchProcessor.

    Args:
        session_id: UUID string of the SearchSession
        processing_session_id: UUID string of the ProcessingSession
        raw_result_ids: List of RawSearchResult IDs to process
        batch_num: Current batch number
        total_batches: Total number of batches

    Returns:
        Dictionary with batch processing results
    """
    try:
        # Validate session ID
        validate_session_id(session_id)

        # Validate batch parameters
        batch_processor.validate_batch_parameters(raw_result_ids)

        # Get processing session
        processing_session = ProcessingSession.objects.get(id=processing_session_id)

        # Prepare batch information
        batch_info = {
            "batch_num": batch_num,
            "total_batches": total_batches,
        }

        # Process batch using the new BatchProcessor
        result = batch_processor.process_batch(
            session_id=session_id,
            raw_result_ids=raw_result_ids,
            processing_session=processing_session,
            batch_info=batch_info,
        )

        # Enhanced batch completion logging
        total_attempted = len(raw_result_ids)
        logger.info(f"🏁 BATCH PROCESSING COMPLETE for session {session_id}:")
        logger.info(f"   📥 Total raw results: {total_attempted}")
        logger.info(f"   ✅ Successfully processed: {result['processed_count']}")
        logger.info(f"   ❌ Filtered (duplicates): {result['filtered_count']}")
        logger.info(f"   💥 Errors: {result['error_count']}")
        logger.info(f"   📊 Success rate: {result['success_rate']:.1f}%")

        if result["filtered_count"] > 0:
            logger.warning(
                f"⚠️  IMPORTANT: {result['filtered_count']} results were filtered out during processing"
            )

        # Return in the expected format for backward compatibility
        return {
            "status": "completed",
            "processed_count": result["processed_count"],
            "error_count": result["error_count"],
            "filtered_count": result["filtered_count"],
            "batch_size": len(raw_result_ids),
            "success_rate": result["success_rate"],
            "errors": result.get("errors", []),
        }

    except Exception as exc:
        logger.error(f"Batch processing failed for session {session_id}: {str(exc)}")

        if self.request.retries < MAX_RETRIES:
            retry_countdown = RETRY_DELAY * (2**self.request.retries)
            raise self.retry(countdown=retry_countdown, exc=exc)

        return {"status": "failed", "error": str(exc)}


# Legacy single result processing - now handled by BatchProcessor.process_single_result()
# This function has been replaced by the modular BatchProcessor service


# Legacy organization extraction - now handled by ResultNormalizer service


@shared_task(bind=True)
def run_deduplication_task(
    self, batch_results: list, session_id: str, processing_session_id: str
):
    """
    Run deduplication across all processed results for a session.

    Args:
        batch_results: Results from batch processing tasks
        session_id: UUID string of the SearchSession
        processing_session_id: UUID string of the ProcessingSession

    Returns:
        Dictionary with deduplication results
    """
    logger.info(f"Running deduplication for session {session_id}")

    processing_session = None
    try:
        processing_session = ProcessingSession.objects.get(id=processing_session_id)
        processing_session.update_progress("deduplication", 0)

        # Broadcast progress update
        try:
            from apps.review_manager.models import SearchSession

            session = SearchSession.objects.get(id=session_id)
            session.update_status_detail(
                ExecutionStatusMessages.CONDUCTING_DEDUPLICATION
            )
        except Exception as e:
            logger.warning(f"Progress broadcast failed: {e}")

        # Deduplication is handled by BatchProcessor via get_or_create on URL.
        # This task now just counts the duplicates already identified.
        from ..api import get_deduplication_stats

        dedup_stats = get_deduplication_stats(session_id)
        duplicate_count = dedup_stats.get("duplicates_removed", 0)
        logger.info(
            f"Deduplication summary for session {session_id}: "
            f"{duplicate_count} duplicates found by batch processor"
        )

        # Update progress - deduplication completed
        processing_session.update_progress(
            stage="finalization", stage_progress=0, duplicate_count=duplicate_count
        )

        # Broadcast progress update
        try:
            # Ensure total_count is at least as large as processed_count
            processed = processing_session.processed_count
            total = processing_session.total_raw_results or 0

            # Use validation utility to ensure counts are consistent
            processed, total = ensure_valid_counts(processed, total)

            session.update_status_detail(
                f"Deduplication complete - {duplicate_count} duplicates found"
            )
        except Exception as e:
            logger.warning(f"Progress broadcast failed: {e}")

        return {
            "status": "completed",
            "duplicates_removed": duplicate_count,
            "total_duplicates": duplicate_count,
        }

    except Exception as exc:
        logger.error(f"Deduplication failed for session {session_id}: {str(exc)}")
        if processing_session:
            processing_session.add_error(
                error_message=f"Deduplication failed: {str(exc)}"
            )
        else:
            logger.error(
                f"Could not retrieve ProcessingSession {processing_session_id}"
            )
        return {"status": "failed", "error": str(exc)}


def validate_state_for_finalization(session_status: str) -> tuple:
    """
    Validate that session is in correct state for finalization.

    Args:
        session_status: Current status of the session

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Only sessions in 'processing_results' can be finalized
    if session_status != "processing_results":
        return (
            False,
            f"Cannot finalize session in state '{session_status}'. Expected 'processing_results'",
        )

    return True, ""


def ensure_processing_session_ready(processing_session: ProcessingSession) -> tuple:
    """
    Ensure processing session is ready for finalization.

    Args:
        processing_session: The ProcessingSession instance

    Returns:
        Tuple of (is_ready, error_message)
    """
    if processing_session.status == "completed":
        return False, "Processing session already completed"

    if processing_session.status == "failed":
        return False, "Cannot finalize failed processing session"

    if processing_session.status not in ["processing", "in_progress"]:
        return (
            False,
            f"Processing session in unexpected state: {processing_session.status}",
        )

    return True, ""


@shared_task(bind=True, max_retries=MAX_RETRIES)
def finalize_processing_task(  # noqa: C901 - Complex finalization logic with state validation and error handling
    self, dedup_results: dict, session_id: str, processing_session_id: str
):
    """
    Finalize results processing with atomic state transition.

    This task ensures atomic transition from 'processing_results' to 'ready_for_review'
    with comprehensive validation and error handling.

    Args:
        dedup_results: Results from deduplication task
        session_id: UUID string of the SearchSession
        processing_session_id: UUID string of the ProcessingSession

    Returns:
        Dictionary with final processing results
    """
    logger.info(f"Starting finalization for session {session_id}")

    processing_session = None
    transition_metadata = {
        "trigger": "processing_complete",
        "automatic_transition": True,
        "dedup_results": dedup_results,
    }

    try:
        # Step 1: First transaction - validate and update processing session
        with transaction.atomic():
            # Lock processing_session for update
            processing_session = ProcessingSession.objects.select_for_update().get(
                id=processing_session_id
            )

            # Validate processing session
            is_ready, error_msg = ensure_processing_session_ready(processing_session)
            if not is_ready:
                logger.error(f"Processing session not ready: {error_msg}")
                return {
                    "status": "failed",
                    "error": error_msg,
                    "processing_session_status": processing_session.status,
                }

            # Update progress
            processing_session.update_progress("finalization", 100)

        # Get session without lock for validation
        from apps.review_manager.models import SearchSession

        session = SearchSession.objects.get(id=session_id)

        # Validate current state
        is_valid, error_msg = validate_state_for_finalization(session.status)
        if not is_valid:
            logger.error(
                f"State validation failed for session {session_id}: {error_msg}"
            )
            return {
                "status": "failed",
                "error": error_msg,
                "session_id": session_id,
                "current_state": session.status,
            }

        # Send progress update BEFORE state transition to avoid race conditions
        try:
            # First send "Finalising results" message (UK English)
            session.update_status_detail(ExecutionStatusMessages.FINALIZING_RESULTS)
        except Exception as e:
            logger.warning(f"Progress broadcast failed: {e}")

        # Get final statistics before state transition
        stats = get_processing_statistics(session_id)

        # Enhanced logging for result count tracking (Issue #13)
        logger.info(f"Session {session_id} - Final result count tracking:")
        logger.info(
            f"  - Total results before deduplication: {stats.get('total_results', 0)}"
        )
        logger.info(
            f"  - Duplicates removed: {dedup_results.get('duplicates_removed', 0)}"
        )
        logger.info(f"  - Final unique results: {stats.get('processed_results', 0)}")

        # Special logging for small result sets (Issue #50)
        if stats.get("total_results", 0) < 20:
            logger.info(
                f"Session {session_id} - Small result set detected ({stats.get('total_results', 0)} results)"
            )
            logger.info(
                "  - Small result sets may complete rapidly, frontend polling adjusted"
            )

        # Complete processing session
        processing_session.complete_processing()

        # Step 2: Second transaction - state transition
        with transaction.atomic():
            from apps.review_manager.models import SearchSession, SessionActivity
            from apps.review_manager.services.state_manager import (
                SessionStateManager,
                StateTransitionError,
            )

            # Lock session for state transition
            session = SearchSession.objects.select_for_update().get(id=session_id)

            # Verify state hasn't changed
            if session.status != "processing_results":
                logger.warning(
                    f"Session state changed during processing: {session.status}"
                )
                return {
                    "status": "failed",
                    "error": f"Session state changed to {session.status}",
                    "session_id": session_id,
                }

            # Use StateManager for atomic transition
            try:
                state_manager = SessionStateManager(session)
                transition_success, error = state_manager.transition_to(
                    "ready_for_review", metadata=transition_metadata
                )

                if not transition_success:
                    raise StateTransitionError(
                        f"State transition failed: {error or 'Unknown error'}"
                    )

            except StateTransitionError as e:
                # Log the error but don't fail the entire task
                logger.error(f"State transition failed: {str(e)}")

                # Try force transition as fallback (for recovery)
                session.status = "ready_for_review"
                session.save(update_fields=["status", "updated_at"])

                # Log manual transition
                SessionActivity.objects.create(
                    session=session,
                    activity_type="state_change",
                    description="Forced transition to ready_for_review due to StateManager error",
                    user=session.owner,
                    metadata={"forced": True, "error": str(e), **transition_metadata},
                )

        # Final verification (outside transaction)
        session.refresh_from_db()
        if session.status != "ready_for_review":
            raise StateTransitionError(
                f"Final state verification failed. Expected 'ready_for_review', "
                f"got '{session.status}'"
            )

        # Step 3: Send SSE notification for successful transition
        # Send state change notification via SSE
        try:
            # State change notifications are now handled via event bus
            logger.info(
                f"State transition: processing_results -> ready_for_review for session {session.id}",
                extra={
                    "session_id": str(session.id),
                    "total_results": stats.get("processed_results", 0),
                    "duplicates_removed": dedup_results.get("duplicates_removed", 0),
                    "automatic_transition": True,
                    "message": "Processing complete. Ready for review.",
                },
            )

            # Send final progress update
            session.update_status_detail(ExecutionStatusMessages.READY_FOR_REVIEW)

            logger.info("Sent progress notifications for ready_for_review transition")
        except Exception as notify_error:
            # Don't fail the task if notification fails
            logger.warning(f"Failed to send notification: {notify_error}")

        logger.info(
            f"Successfully finalized session {session_id}. "
            f"Status: {session.status}, "
            f"Processed: {stats.get('processed_results', 0)} results"
        )

        return {
            "status": "success",
            "session_id": session_id,
            "final_status": session.status,
            "statistics": stats,
            "duplicates_removed": dedup_results.get("duplicates_removed", 0),
        }

    except SearchSession.DoesNotExist:
        logger.error(f"Session {session_id} not found")
        return {"status": "failed", "error": f"Session {session_id} not found"}

    except ProcessingSession.DoesNotExist:
        logger.error(f"ProcessingSession {processing_session_id} not found")
        return {
            "status": "failed",
            "error": f"ProcessingSession {processing_session_id} not found",
        }

    except Exception as exc:
        logger.error(
            f"Finalization failed for session {session_id}: {str(exc)}", exc_info=True
        )

        # Mark processing as failed if we have the object
        if processing_session:
            try:
                processing_session.fail_processing(
                    error_message=f"Finalization failed: {str(exc)}",
                    error_details={"exception_type": type(exc).__name__},
                )
            except Exception as e:
                logger.error(f"Could not mark processing as failed: {str(e)}")

        # Check if we should retry
        if self.request.retries < MAX_RETRIES:
            retry_countdown = RETRY_DELAY * (2**self.request.retries)
            logger.info(f"Retrying finalization in {retry_countdown} seconds")
            raise self.retry(countdown=retry_countdown, exc=exc)

        return {"status": "failed", "error": str(exc), "error_type": type(exc).__name__}
