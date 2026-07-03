"""
Helper functions for monitoring tasks.
Extracted to reduce main task function complexity.
"""

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


def check_and_handle_stuck_executions(
    session: Any, stuck_timeout: timedelta | None = None
) -> int:
    """
    Check for and handle stuck executions in a session.

    Args:
        session: SearchSession instance
        stuck_timeout: Timeout duration for stuck executions

    Returns:
        int: Number of stuck executions found and handled
    """
    from apps.serp_execution.models import SearchExecution

    if not stuck_timeout:
        stuck_timeout = timedelta(minutes=2)  # Default timeout

    now = timezone.now()
    executions = SearchExecution.objects.filter(query__session=session)

    stuck_executions = executions.filter(
        status="running", started_at__lt=now - stuck_timeout
    )

    if not stuck_executions.exists():
        return 0

    stuck_count = stuck_executions.count()
    logger.warning(
        f"Found {stuck_count} stuck executions for session {session.id}, "
        f"marking as failed to allow progression"
    )

    for execution in stuck_executions:
        execution.status = "failed"
        execution.completed_at = now
        execution.error_message = f"Execution timeout - stuck for over {stuck_timeout}"
        execution.save(update_fields=["status", "completed_at", "error_message"])
        logger.warning(f"Marked execution {execution.id} as failed due to timeout")

    return stuck_count


def force_fail_pending_executions(session: Any, reason: str = "Force failed") -> int:
    """
    Force fail all pending/running executions in a session.

    Args:
        session: SearchSession instance
        reason: Reason for force failing

    Returns:
        int: Number of executions force failed
    """
    from apps.serp_execution.models import SearchExecution

    executions = SearchExecution.objects.filter(query__session=session)
    pending_executions = executions.filter(status__in=["pending", "running"])

    count = 0
    for execution in pending_executions:
        execution.status = "failed"
        execution.completed_at = timezone.now()
        execution.error_message = f"{reason} - session monitoring timeout"
        execution.save(update_fields=["status", "completed_at", "error_message"])
        count += 1

    return count


def validate_monitoring_conditions(
    completed: int,
    total: int,
    session: Any = None,
    monitor_count: int = 0,
    max_attempts: int = 8,
) -> bool:
    """
    Validate if monitoring should continue based on conditions.

    Args:
        completed: Number of completed executions
        total: Total number of executions
        session: Optional SearchSession for advanced checks
        monitor_count: Current monitoring attempt count
        max_attempts: Maximum monitoring attempts allowed

    Returns:
        bool: True if monitoring should continue, False otherwise
    """
    # All executions complete
    if completed >= total:
        return False

    # Check for stuck executions if session provided
    if session:
        check_and_handle_stuck_executions(session)

    # Check if exceeded max monitoring attempts
    if monitor_count >= max_attempts and session:
        logger.error(
            f"Session {session.id} monitoring exceeded maximum attempts ({max_attempts}). "
            f"Forcing completion with partial results."
        )
        force_fail_pending_executions(session, "Force failed")
        return False

    return True


def calculate_session_statistics(executions: Any) -> dict:
    """
    Calculate comprehensive statistics for session executions.

    Args:
        executions: QuerySet of SearchExecution objects

    Returns:
        dict: Statistics including successful/failed counts and total results
    """
    successful_executions = executions.filter(status="completed")
    failed_executions = executions.filter(status="failed")

    total_results = sum(e.results_count for e in successful_executions)
    successful_count = successful_executions.count()
    failed_count = failed_executions.count()

    return {
        "total_results": total_results,
        "successful_count": successful_count,
        "failed_count": failed_count,
        "successful_executions": successful_executions,
        "failed_executions": failed_executions,
    }


def handle_session_state_transition(
    session: Any,
    state_manager: Any,  # Note: This parameter is no longer used but kept for backwards compatibility
    target_state: str,
    metadata: dict | None = None,
) -> bool:
    """
    Handle session state transition with fallback logic.

    Args:
        session: SearchSession instance
        state_manager: Deprecated - kept for backwards compatibility
        target_state: Target state to transition to
        metadata: Optional metadata for the transition

    Returns:
        bool: True if transition successful, False otherwise
    """
    from apps.core.services.simple_services import DatabaseStateManager

    try:
        # Create descriptive status detail from metadata
        detail = ""
        if metadata:
            if metadata.get("total_results"):
                detail = f"Found {metadata['total_results']} results"
            elif metadata.get("reason"):
                detail = metadata["reason"]

        # Use simple state manager for direct status updates
        state_mgr = DatabaseStateManager()
        success = state_mgr.set_session_status(session, target_state, detail)

        if success:
            logger.info(f"Transitioned session {session.id} to {target_state}")
        else:
            logger.error(f"Failed to transition session {session.id} to {target_state}")

        return success

    except Exception as e:
        logger.error(f"Session state transition failed: {str(e)}")
        return False


def prepare_monitoring_result(
    session_id: str,
    status: str,
    summary: dict | None = None,
    error: str | None = None,
    progress: str | None = None,
) -> dict:
    """
    Prepare standardized monitoring result dictionary.

    Args:
        session_id: Session ID
        status: Current status
        summary: Optional execution summary
        error: Optional error message
        progress: Optional progress string

    Returns:
        dict: Standardized result dictionary
    """
    result = {"session_id": str(session_id), "status": status}

    if summary:
        result.update(
            {
                "successful": summary.get("successful_count", 0),
                "failed": summary.get("failed_count", 0),
                "total_results": summary.get("total_results", 0),
            }
        )

    if error:
        result["error"] = error

    if progress:
        result["progress"] = progress

    return result


def process_monitoring_check(session_id: str, monitor_count: int = 0):
    """
    Process a single monitoring check for session completion.

    Args:
        session_id: Session ID to monitor
        monitor_count: Current monitoring attempt count

    Returns:
        tuple: (should_continue, result) where should_continue is bool
    """
    from django.db import transaction

    from apps.review_manager.models import SearchSession
    from apps.serp_execution.tasks.helpers import _send_session_notification
    from apps.serp_execution.tasks.monitoring import (
        _calculate_execution_summary,
        _get_execution_stats,
        _handle_all_failed,
        _schedule_retry_monitoring,
        _should_continue_monitoring,
        _transition_to_processing,
        _trigger_result_processing,
        _validate_session,
    )

    # First, attempt state reconciliation
    reconciliation = reconcile_session_states(session_id)
    if reconciliation["reconciled"]:
        logger.info(
            f"State reconciliation performed for session {session_id}: {reconciliation['changes']}"
        )
        # Re-fetch session after reconciliation
        session = SearchSession.objects.get(id=session_id)
        if session.status in ["ready_for_review", "processing_results", "completed"]:
            # Reconciliation moved us forward, adjust monitoring accordingly
            return False, prepare_monitoring_result(
                session_id,
                session.status,
                {"reconciled": True, "changes": reconciliation["changes"]},
            )

    # Initialize monitoring context
    session = _validate_session(session_id)
    state_manager = (
        None  # No longer needed with new state machine, kept for compatibility
    )
    total, completed, executions = _get_execution_stats(session)

    # Check if should continue monitoring
    if _should_continue_monitoring(completed, total, session, monitor_count):
        return True, _schedule_retry_monitoring(
            session_id, monitor_count, progress=f"{completed}/{total}"
        )

    # Process completion
    summary = _calculate_execution_summary(executions)

    # Handle all failed case
    if (
        summary["failed_executions"].exists()
        and not summary["successful_executions"].exists()
    ):
        return False, _handle_all_failed(
            session, state_manager, summary["failed_count"]
        )

    # Transition and notify
    if not _transition_to_processing(session, state_manager, summary):
        return False, prepare_monitoring_result(
            session_id, "transition_failed", summary
        )

    _send_session_notification(
        session,
        f"Search execution completed for '{session.title}'. "
        f"Found {summary['total_results']} results across {summary['successful_count']} queries.",
    )

    # Schedule next phase
    transaction.on_commit(lambda: _trigger_result_processing(session_id))

    return False, prepare_monitoring_result(session_id, "processing_results", summary)


def reconcile_session_states(session_id: str) -> dict:
    """
    Reconcile state mismatches between SearchSession and ProcessingSession.

    This function detects and corrects state desynchronization issues that can
    occur due to race conditions or async task failures.

    Args:
        session_id: Session ID to reconcile

    Returns:
        dict: Reconciliation results with keys:
            - reconciled: bool, whether reconciliation was performed
            - changes: list of changes made
            - errors: list of any errors encountered
    """
    from django.db import transaction

    from apps.core.state_machine import state_machine
    from apps.results_manager.models import ProcessingSession
    from apps.review_manager.models import SearchSession, SessionActivity
    from apps.serp_execution.models import SearchExecution

    result = {
        "reconciled": False,
        "changes": [],
        "errors": [],
        "session_id": str(session_id),
    }

    try:
        # Extended transaction scope - wrap entire function body
        with transaction.atomic():
            # Get the search session with lock for update to prevent concurrent modifications
            session = SearchSession.objects.select_for_update().get(id=session_id)
            current_state = session.status

            # Check for ProcessingSession state mismatch
            processing_sessions = ProcessingSession.objects.filter(
                search_session=session  # Fixed: Correct field reference
            ).order_by("-created_at")

            latest_processing = processing_sessions.first()
            if latest_processing is not None:
                # Reconcile based on ProcessingSession status
                if (
                    latest_processing.status == "completed"
                    and current_state == "processing_results"
                ):
                    # Processing is complete but session stuck in processing_results
                    logger.warning(
                        f"State mismatch detected for session {session_id}: "
                        f"SearchSession={current_state}, ProcessingSession=completed"
                    )

                    try:
                        state_machine.transition(
                            session.id,
                            "ready_for_review",
                            metadata={
                                "reason": "state_reconciliation",
                                "processing_session_id": str(latest_processing.id),
                                "reconciliation_type": "processing_complete",
                            },
                            triggered_by="reconciliation",
                        )
                        result["reconciled"] = True
                        result["changes"].append(
                            f"Transitioned from {current_state} to ready_for_review"
                        )

                        # Log the reconciliation
                        SessionActivity.objects.create(
                            session=session,
                            activity_type="state_reconciliation",
                            description=f"Reconciled state mismatch: processing complete but session stuck in {current_state}",
                            metadata={
                                "previous_state": current_state,
                                "new_state": "ready_for_review",
                                "processing_session_status": latest_processing.status,
                            },
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to reconcile state for session {session_id}: {e}"
                        )
                        result["errors"].append(str(e))

            # Check SearchExecution states vs session state
            executions = SearchExecution.objects.filter(query__session=session)
            total = executions.count()
            completed = executions.filter(
                status__in=["completed", "failed", "cancelled"]
            ).count()

            # Enhanced logging for reconciliation check
            logger.info(
                f"Reconciliation check for session {session_id}: "
                f"current_state={current_state}, "
                f"executions={total}, completed={completed}"
            )

            if total > 0 and completed == total and current_state == "executing":
                # All executions complete but session stuck in executing
                logger.warning(
                    f"Execution mismatch for session {session_id}: "
                    f"All {total} executions complete but session in {current_state}"
                )

                try:
                    # Log transition attempt
                    logger.info(
                        f"Attempting reconciliation transition: {current_state} → processing_results "
                        f"for session {session_id}"
                    )

                    state_machine.transition(
                        session.id,
                        "processing_results",
                        metadata={
                            "reason": "state_reconciliation",
                            "completed_executions": completed,
                            "reconciliation_type": "executions_complete",
                        },
                        triggered_by="reconciliation",
                    )
                    result["reconciled"] = True
                    result["changes"].append(
                        f"Transitioned from {current_state} to processing_results"
                    )

                    logger.info(
                        f"Reconciliation transition successful: {current_state} → processing_results"
                    )

                    # Trigger processing task
                    from apps.results_manager.tasks import process_session_results_task

                    process_session_results_task.apply_async(
                        args=(str(session_id),), countdown=2
                    )
                    result["changes"].append("Triggered result processing task")

                except Exception as e:
                    logger.error(
                        f"Failed to reconcile executions for session {session_id}: {e}"
                    )
                    result["errors"].append(str(e))

            # Check for stuck in ready_for_review without results
            if current_state == "ready_for_review":
                # Ensure ProcessedResult records exist
                from apps.results_manager.models import ProcessedResult

                # Count total processed results
                total_processed_count = ProcessedResult.objects.filter(
                    session=session
                ).count()

                # Count SUCCESS status results (excludes FILTERED and ERROR)
                from apps.results_manager.services.processors.error_handler import (
                    ProcessingStatus,
                )

                success_count = ProcessedResult.objects.filter(
                    session=session, processing_status=ProcessingStatus.SUCCESS
                ).count()

                filtered_count = ProcessedResult.objects.filter(
                    session=session, processing_status=ProcessingStatus.FILTERED
                ).count()

                error_count = ProcessedResult.objects.filter(
                    session=session, processing_status=ProcessingStatus.ERROR
                ).count()

                logger.info(
                    f"Session {session_id} in ready_for_review state:\n"
                    f"   📊 Total ProcessedResults: {total_processed_count}\n"
                    f"   ✅ SUCCESS: {success_count}\n"
                    f"   🔄 FILTERED (duplicates): {filtered_count}\n"
                    f"   ❌ ERRORS: {error_count}"
                )

                if total_processed_count > 0:
                    if success_count == 0 and filtered_count > 0:
                        logger.error(
                            f"⚠️  ZERO RESULTS BUG DETECTED: Session {session_id} has {filtered_count} filtered results "
                            f"but 0 SUCCESS results. All results were marked as duplicates!"
                        )
                        result["errors"].append(
                            f"All {filtered_count} results marked as duplicates - zero unique results available for review"
                        )
                    elif success_count > 0:
                        logger.info(
                            f"Session {session_id} has {success_count} results available for review"
                        )
                        result["changes"].append(
                            f"Confirmed {success_count} unique results ready for review"
                        )
                    else:
                        logger.warning(
                            f"Session {session_id} in ready_for_review with {error_count} error results only"
                        )
                        result["errors"].append(
                            f"Only error results ({error_count}) available - no successful results"
                        )
                else:
                    logger.warning(
                        f"Session {session_id} in ready_for_review but no ProcessedResults found at all"
                    )
                    result["errors"].append("No processed results found")

    except SearchSession.DoesNotExist:
        result["errors"].append(f"Session {session_id} not found")
    except Exception as e:
        logger.error(f"Reconciliation error for session {session_id}: {e}")
        result["errors"].append(str(e))

    return result


def trigger_next_phase_task(session_id: str, phase: str, countdown: int = 2) -> None:
    """
    Trigger the appropriate next phase task based on session state.

    Args:
        session_id: Session ID
        phase: Next phase to trigger
        countdown: Delay in seconds before execution
    """
    if phase == "processing_results":
        from apps.results_manager.tasks import process_session_results_task

        process_session_results_task.apply_async(
            args=(str(session_id),), countdown=countdown
        )
        logger.info(
            f"Triggered result processing for session {session_id} with {countdown}s delay"
        )
    else:
        logger.warning(f"Unknown phase '{phase}' for session {session_id}")
