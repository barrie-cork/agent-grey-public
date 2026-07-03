"""
Main orchestration tasks for results processing pipeline.

This module contains the primary workflow coordination tasks that orchestrate
the entire results processing pipeline.
"""

import logging
from typing import Any

from celery import chain, current_task, group, shared_task
from celery.exceptions import CeleryError
from django.db import DatabaseError
from django.utils import timezone

from apps.core.utils.distributed_lock import DistributedLock, LockConfig
from apps.review_manager.models import SearchSession
from apps.serp_execution.models import RawSearchResult

from ..api_types import (
    NoResultsResponse,
    ProcessingError,
    ProcessingResult,
    ProcessingSessionInput,
    WorkflowCreationResult,
)
from ..constants import TaskConstants
from ..models import ProcessingSession
from ..services.error_handler import TaskErrorHandler
from ..services.task_deduplication import TaskDeduplicationService
from ..validation import (
    get_or_create_processing_record,
    validate_session_for_processing,
    validate_session_id,
)
from .processing import (
    finalize_processing_task,
    process_batch_task,
    run_deduplication_task,
)

logger = logging.getLogger(__name__)

# Legacy constants for compatibility
BATCH_SIZE = TaskConstants.BATCH_SIZE
MAX_RETRIES = TaskConstants.MAX_RETRIES
RETRY_DELAY = TaskConstants.RETRY_DELAY
REDIS_LOCK_TIMEOUT = TaskConstants.REDIS_LOCK_TIMEOUT
REDIS_LOCK_SLEEP = 0.1  # seconds


# Migration Note: redis_lock context manager has been removed.
# Use DistributedLock directly for distributed locking:
#   lock_config = LockConfig(...)
#   lock = DistributedLock(config=lock_config)
#   with lock.acquire(key, timeout=timeout): ...


def get_session_lock_key(session_id: str) -> str:
    """Generate Redis lock key for session processing."""
    return f"processing_session_{session_id}"


# Legacy task management functions removed - use TaskDeduplicationService instead
# The following functions have been replaced:
# - is_task_already_running() -> TaskDeduplicationService.check_and_register()
# - register_task_as_running() -> TaskDeduplicationService.check_and_register()
# - unregister_task() -> TaskDeduplicationService.cleanup()
# - get_or_create_task_mapping() -> TaskDeduplicationService._update_task_mapping()


def _validate_session(session_id: str):
    """Validate and retrieve search session."""
    from apps.review_manager.models import SearchSession

    try:
        return SearchSession.objects.get(id=session_id)
    except SearchSession.DoesNotExist:
        logger.error(f"SearchSession {session_id} not found")
        raise


def _get_or_create_processing_session(session) -> ProcessingSession:
    """Get or create processing session."""
    processing_session, created = ProcessingSession.objects.get_or_create(
        search_session=session, defaults={"status": "pending"}
    )
    return processing_session


def _check_already_completed(
    processing_session: ProcessingSession, session_id: str
) -> dict | None:
    """Check if session is already processed."""
    # Ensure we have the latest processing session state
    processing_session.refresh_from_db()
    if processing_session.status == "completed":
        logger.info(f"Session {session_id} already processed")
        return {
            "status": "already_completed",
            "session_id": session_id,
            "processed_count": processing_session.processed_count,
        }
    return None


def _get_raw_results_count(session) -> int:
    """Get count of all raw results for the session."""
    return RawSearchResult.objects.filter(execution__query__session=session).count()


def _handle_no_results(processing_session: ProcessingSession, session_id: str):
    """Handle case when no raw results found."""
    logger.warning(f"No raw results found for session {session_id}")
    logger.info(
        f"Session {session_id} - Zero results detected. Possible reasons: "
        f"1) Search queries too specific, 2) API returned no matches, "
        f"3) All results filtered during execution"
    )
    processing_session.status = "completed"
    processing_session.save()

    # Update SearchSession status using StateManager for atomic transition
    try:
        from apps.review_manager.models import SearchSession

        session = SearchSession.objects.get(id=session_id)
        completed_at = timezone.now()

        # Direct atomic status update
        session.status = "completed"
        session.status_detail = "Search completed with no results found"
        session.total_results = 0
        session.completed_at = completed_at
        session.save(
            update_fields=["status", "status_detail", "total_results", "completed_at"]
        )

        logger.info(
            f"Session {session_id} transitioned to completed state due to zero results."
        )

        return NoResultsResponse(
            status="no_results",
            session_id=str(session_id),
            message="Search completed with no results found",
            total_results=0,
            completed_at=completed_at.isoformat(),
            reason="No results found matching search criteria",
            automatic_transition=True,
        )
    except SearchSession.DoesNotExist:
        logger.error(f"SearchSession {session_id} not found in _handle_no_results")
        return ProcessingError(
            session_id=session_id,
            error="Session not found",
            error_type="SearchSession.DoesNotExist",
        )


def _start_processing(
    session: SearchSession,
    processing_session: ProcessingSession,
    total_results: int,
    task_id: str,
) -> None:
    """Update session status and start processing."""
    session.status = "processing_results"
    session.save(update_fields=["status"])

    # Store Celery task ID (or our unique task ID if no Celery context)
    celery_id = (
        current_task.request.id if current_task and current_task.request.id else None
    ) or task_id

    # Pass metadata directly to start_processing
    processing_session.start_processing(
        total_raw_results=total_results,
        celery_task_id=celery_id,
        metadata={
            TaskConstants.METADATA_TASK_ID: task_id,
            TaskConstants.METADATA_STARTED_BY: "orchestration",
        },
    )


def _mark_processing_failed(session_id: str, exc: Exception) -> None:
    """Mark processing session as failed."""
    try:
        processing_session = ProcessingSession.objects.get(search_session_id=session_id)
        processing_session.fail_processing(
            error_message=f"Failed to start processing: {str(exc)}",
            error_details={"exception_type": type(exc).__name__},
        )
    except ProcessingSession.DoesNotExist:
        pass


def _handle_processing_error(session_id: str, exc: Exception, retries: int):
    """Handle processing errors and retries."""
    _mark_processing_failed(session_id, exc)

    # Check if should retry
    if retries < MAX_RETRIES:
        retry_countdown = RETRY_DELAY * (2**retries)
        logger.info(
            f"Retrying processing for session {session_id} in {retry_countdown}s"
        )
        # Caller will handle the retry
        raise

    return {"status": "failed", "error": str(exc)}


def _validate_input(session_id: str) -> tuple:
    """Validate and normalize session ID input."""
    try:
        validated_input: ProcessingSessionInput = {"session_id": str(session_id)}
        return True, validated_input["session_id"], None
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid session_id format: {e}")
        error_result = {
            "session_id": session_id,
            "error": f"Invalid session ID format: {str(e)}",
            "error_type": "validation_error",
        }
        return False, None, error_result


def _handle_deduplication(session_id: str) -> tuple:
    """Handle task deduplication logic."""
    dedup_service = TaskDeduplicationService(session_id)
    registration = dedup_service.check_and_register()

    if not registration["success"]:
        logger.info(
            f"Task registration failed for session {session_id}: {registration['reason']}"
        )
        skip_result = {
            "status": TaskConstants.STATUS_SKIPPED,
            "reason": registration["reason"],
            "message": f"Task registration failed: {registration['reason']}",
        }
        return False, None, skip_result, None

    return True, registration["task_id"], None, dedup_service


def _log_result_statistics(
    session_id: str, session: SearchSession, total_results: int
) -> None:
    """Log detailed result statistics for debugging."""
    logger.info(f"Session {session_id} - Result count tracking:")
    logger.info(f"  - Raw results to process: {total_results}")

    from apps.serp_execution.models import SearchExecution

    executions = SearchExecution.objects.filter(query__session=session).select_related(
        "query__strategy"
    )

    total_requested = sum(
        exec.query.strategy.search_config.get("max_results", 50) for exec in executions
    )
    logger.info(f"  - Total results requested from API: {total_requested}")
    logger.info(f"  - Search executions performed: {executions.count()}")


def _validate_and_prepare(session_id: str) -> dict:
    """
    Validate input and prepare task for processing.

    Returns:
        dict: Validation result with success status and data/error
    """
    logger.info(f"Starting results processing for session {session_id}")

    # Send initial progress update
    try:
        from apps.serp_execution.dependencies import get_notification_service

        notifier = get_notification_service()
        notifier.notify_progress(session_id, 55, "Initializing result processing...")
    except (ImportError, ConnectionError, OSError) as e:
        logger.warning(f"Failed to send initial progress update: {e}")

    # Validate input
    success, validated_session_id, error_result = _validate_input(session_id)
    if not success:
        return {"success": False, "result": error_result}

    # Handle deduplication
    success, task_id, skip_result, dedup_service = _handle_deduplication(
        validated_session_id
    )
    if not success:
        return {"success": False, "result": skip_result}

    return {
        "success": True,
        "session_id": validated_session_id,
        "task_id": task_id,
        "dedup_service": dedup_service,
    }


def _get_processing_lock(session_id: str):
    """
    Create and return distributed lock for session processing.

    Returns:
        DistributedLock: Configured lock instance
    """
    lock_key = get_session_lock_key(session_id)
    lock_config = LockConfig(
        timeout=REDIS_LOCK_TIMEOUT,
        retry_count=3,
        retry_delay=1.0,
        use_exponential_backoff=True,
        timeout_buffer=3,
    )
    return DistributedLock(config=lock_config), lock_key


def _validate_processing_session(session_id: str) -> tuple:
    """
    Validate session and create processing record.

    Returns:
        tuple: (session, processing_session)
    """
    validate_session_id(session_id)
    session = _validate_session(session_id)
    validate_session_for_processing(session)
    processing_session = get_or_create_processing_record(session)

    return session, processing_session


def _check_early_termination_conditions(
    processing_session, session_id: str, session
) -> dict:
    """
    Check if processing should terminate early (already completed or no results).

    Returns:
        dict: Result if early termination needed, None otherwise
    """
    # Check if already completed
    completed_result = _check_already_completed(processing_session, session_id)
    if completed_result:
        logger.info(f"Session {session_id} already completed")
        result = ProcessingResult(
            status=TaskConstants.STATUS_ALREADY_COMPLETED,
            session_id=session_id,
            processed_count=completed_result.get("processed_count", 0),
            message="Session already processed",
        )
        return {"terminate": True, "result": result}

    # Check for no results
    total_results = _get_raw_results_count(session)
    _log_result_statistics(session_id, session, total_results)

    if total_results == 0:
        no_results_response = _handle_no_results(processing_session, session_id)
        return {"terminate": True, "result": no_results_response}

    return {"terminate": False, "total_results": total_results}


def _execute_processing_workflow(
    session_id: str, task_id: str, session, processing_session, total_results: int
) -> ProcessingResult:
    """
    Execute the main processing workflow.

    Returns:
        dict: Processing result
    """
    # Start processing workflow
    _start_processing(session, processing_session, total_results, task_id)

    # Send progress update for starting batch processing
    try:
        from apps.serp_execution.dependencies import get_notification_service

        notifier = get_notification_service()
        notifier.notify_progress(
            session_id, 60, f"Processing {total_results} results in batches..."
        )
    except (ImportError, ConnectionError, OSError) as e:
        logger.warning(f"Failed to send batch processing progress update: {e}")

    workflow = create_processing_workflow.delay(
        session_id=session_id, processing_session_id=str(processing_session.id)
    )

    logger.info(f"Successfully started processing workflow for session {session_id}")

    result = ProcessingResult(
        status=TaskConstants.STATUS_STARTED,
        session_id=session_id,
        total_results=total_results,
        workflow_task_id=workflow.id,
        message="Processing workflow started successfully",
    )
    return result


def _handle_lock_acquisition_error(session_id: str, exc: Exception) -> ProcessingResult:
    """
    Handle errors related to lock acquisition.

    Returns:
        dict: Error response
    """
    if "Could not acquire lock" in str(exc):
        logger.info(f"Session {session_id} is already being processed")
        result = ProcessingResult(
            status=TaskConstants.STATUS_ALREADY_PROCESSING,
            session_id=session_id,
            message="Session is already being processed by another task",
        )
        return result
    # Re-raise if not a lock error
    raise exc


@shared_task(bind=True, max_retries=MAX_RETRIES)
def process_session_results_task(
    self, session_id: str
) -> ProcessingResult | ProcessingError | dict[str, Any]:
    """
    Main orchestration task - delegates to focused functions.

    This is the main entry point that coordinates the entire processing pipeline
    by delegating to smaller, focused helper functions.

    Args:
        session_id: UUID string of the SearchSession

    Returns:
        dict: Processing results and statistics
    """
    # Step 1: Validate and prepare
    validation_result = _validate_and_prepare(session_id)
    if not validation_result["success"]:
        return validation_result["result"]

    session_id = validation_result["session_id"]
    task_id = validation_result["task_id"]
    dedup_service = validation_result["dedup_service"]

    error_handler = TaskErrorHandler(session_id)

    try:
        # Step 2: Acquire lock and process
        lock, lock_key = _get_processing_lock(session_id)

        with lock.acquire(lock_key, timeout=REDIS_LOCK_TIMEOUT):
            logger.info(f"Acquired processing lock for session {session_id}")

            # Step 3: Validate session and processing record
            session, processing_session = _validate_processing_session(session_id)

            # Step 4: Check early termination conditions
            termination_check = _check_early_termination_conditions(
                processing_session, session_id, session
            )
            if termination_check["terminate"]:
                return termination_check["result"]

            # Step 5: Execute processing workflow
            return _execute_processing_workflow(
                session_id,
                task_id,
                session,
                processing_session,
                termination_check["total_results"],
            )

    except SearchSession.DoesNotExist:
        logger.error(f"SearchSession {session_id} not found")
        return error_handler.handle_exception(
            SearchSession.DoesNotExist(f"Session {session_id} not found"),
            self.request.retries,
        )
    except (
        Exception
    ) as exc:  # Intentional broad catch: Celery task last-resort error handler
        # Handle lock-specific errors
        try:
            return _handle_lock_acquisition_error(session_id, exc)
        except Exception:  # Broad catch required: _handle_lock_acquisition_error re-raises non-lock errors
            # Handle other processing errors
            logger.error(f"Error processing session {session_id}: {str(exc)}")
            error_handler.mark_processing_failed(exc)

            # Check if should retry
            if error_handler.should_retry(exc, self.request.retries):
                retry_delay = error_handler.get_retry_delay(self.request.retries)
                raise self.retry(countdown=retry_delay, exc=exc)

            # Return error result
            return error_handler.handle_exception(exc, self.request.retries)
    finally:
        # Clean up using deduplication service
        if dedup_service:
            dedup_service.cleanup()


@shared_task(bind=True)
def create_processing_workflow(
    self, session_id: str, processing_session_id: str
) -> WorkflowCreationResult:
    """
    Create and execute the processing workflow.

    Args:
        session_id: UUID string of the SearchSession
        processing_session_id: UUID string of the ProcessingSession

    Returns:
        Dictionary with workflow execution results (WorkflowCreationResult schema)
    """
    processing_session = None
    try:
        processing_session = ProcessingSession.objects.get(id=processing_session_id)

        # Get raw results in batches
        raw_results = RawSearchResult.objects.filter(
            execution__query__session_id=session_id, is_processed=False
        ).values_list("id", flat=True)

        batch_ids = [
            list(raw_results[i : i + BATCH_SIZE])
            for i in range(0, len(raw_results), BATCH_SIZE)
        ]

        # Create batch processing tasks
        batch_tasks = [
            process_batch_task.s(session_id, processing_session_id, batch)
            for batch in batch_ids
        ]

        # Create workflow: batch processing -> deduplication -> finalization
        workflow = chain(
            group(*batch_tasks),
            run_deduplication_task.s(session_id, processing_session_id),
            finalize_processing_task.s(session_id, processing_session_id),
        )

        # Execute workflow
        result = workflow.apply_async()

        # Note: Issue #50 (small result sets) is now handled by frontend state reconciliation
        # The previous time.sleep() was ineffective as it didn't delay the async Celery tasks
        if len(raw_results) < 20:
            logger.info(
                f"Small result set ({len(raw_results)} results) - frontend will use enhanced polling"
            )

        # Return validated WorkflowCreationResult
        workflow_result = WorkflowCreationResult(
            status="workflow_created",
            session_id=session_id,
            processing_session_id=processing_session_id,
            batch_count=len(batch_tasks),
            workflow_id=result.id,
        )
        return workflow_result
    except (
        DatabaseError,
        ValueError,
        CeleryError,
        ProcessingSession.DoesNotExist,
    ) as exc:
        logger.error(f"Error creating workflow for session {session_id}: {str(exc)}")
        if processing_session:
            processing_session.fail_processing(
                error_message=f"Workflow creation failed: {str(exc)}"
            )
        else:
            logger.error(
                f"Could not retrieve ProcessingSession {processing_session_id}"
            )

        # Return validated error result
        error_result = WorkflowCreationResult(
            status="failed",
            session_id=session_id,
            processing_session_id=processing_session_id,
            error=str(exc),
        )
        return error_result
