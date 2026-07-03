"""
Monitoring tasks for search session execution.
Decomposed from the original tasks.py for better maintainability.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from celery import shared_task
from django.db import transaction

if TYPE_CHECKING:
    from apps.review_manager.models import SearchSession
    from apps.review_manager.services.state_manager import SessionStateManager

logger = logging.getLogger(__name__)


def _validate_session(session_id: str) -> "SearchSession":
    """
    Validate and retrieve session with lock.

    Args:
        session_id: ID of the SearchSession

    Returns:
        SearchSession instance with update lock

    Raises:
        SearchSession.DoesNotExist: If session not found
    """
    from apps.review_manager.models import SearchSession

    session = SearchSession.objects.select_for_update().get(id=session_id)
    logger.info(f"Retrieved and locked session {session_id} for monitoring")
    return session


def _get_execution_stats(session: "SearchSession"):
    """
    Get execution statistics for a session.

    Args:
        session: SearchSession instance

    Returns:
        tuple: (total_executions, completed_executions, executions_queryset)
               where executions_queryset is a Django QuerySet of SearchExecution objects
    """
    from apps.serp_execution.models import SearchExecution

    executions = SearchExecution.objects.filter(query__session=session).select_related(
        "query"
    )

    total_executions = executions.count()
    completed_executions = executions.filter(
        status__in=["completed", "failed", "cancelled"]
    ).count()

    logger.info(
        f"Session {session.id}: {completed_executions}/{total_executions} executions completed"
    )

    return total_executions, completed_executions, executions


def _should_continue_monitoring(
    completed: int, total: int, session=None, monitor_count: int = 0
) -> bool:
    """
    Check if monitoring should continue.

    Args:
        completed: Number of completed executions
        total: Total number of executions
        session: Session object for timeout checks
        monitor_count: Number of monitoring attempts

    Returns:
        True if monitoring should continue, False if all done
    """
    from .monitoring_helpers import validate_monitoring_conditions

    return validate_monitoring_conditions(completed, total, session, monitor_count)


def _schedule_retry_monitoring(
    session_id: str,
    monitor_count: int = 0,
    countdown: int = 30,
    progress: str | None = None,
):
    """
    Schedule another monitoring check.

    Args:
        session_id: Session ID to monitor
        monitor_count: Current monitoring attempt count
        countdown: Seconds to wait before retry
        progress: Optional progress string (e.g., "1/5")

    Returns:
        dict: Status dictionary with keys (session_id, status, message, progress)
    """
    monitor_session_completion_task.apply_async(
        args=(session_id, monitor_count + 1), countdown=countdown
    )

    result = {
        "session_id": str(session_id),
        "status": "executing",
        "message": f"Scheduled retry in {countdown} seconds",
    }

    if progress:
        result["progress"] = progress

    return result


def _calculate_execution_summary(executions):
    """
    Calculate summary statistics for executions.

    Args:
        executions: Django QuerySet of SearchExecution objects

    Returns:
        dict: Dictionary with summary statistics including keys (total_results,
              successful_count, failed_count, successful_executions, failed_executions)
    """
    from .monitoring_helpers import calculate_session_statistics

    return calculate_session_statistics(executions)


def _handle_all_failed(
    session: "SearchSession",
    state_manager: "SessionStateManager | None",  # Kept for compatibility
    failed_count: int,
):
    """
    Handle case where all executions failed.

    Args:
        session: SearchSession instance
        state_manager: Deprecated - kept for backwards compatibility
        failed_count: Number of failed executions

    Returns:
        dict: Result dictionary with keys (session_id, status, successful, failed)
    """
    from apps.core.services.simple_services import DatabaseStateManager

    from .helpers import _send_session_notification

    try:
        success = DatabaseStateManager().set_session_status(
            session,
            "ready_to_execute",
            detail=f"All {failed_count} executions failed - ready to retry",
        )

        if not success:
            logger.error(
                f"Failed to transition session {session.id} after all failures"
            )
    except Exception as e:
        logger.error(
            f"Failed to transition session {session.id} after all failures: {str(e)}"
        )

    _send_session_notification(
        session,
        f"All search executions failed for session '{session.title}'. "
        f"Please review error logs and retry.",
    )

    return {
        "session_id": str(session.id),
        "status": "all_failed",
        "successful": 0,
        "failed": failed_count,
    }


def _transition_to_processing(
    session: "SearchSession",
    state_manager: "SessionStateManager | None",  # Kept for compatibility
    summary: dict,
) -> bool:
    """
    Transition session to processing_results state.

    Args:
        session: SearchSession instance
        state_manager: Deprecated - kept for backwards compatibility
        summary: Execution summary dictionary

    Returns:
        bool: True if transition successful, False otherwise
    """
    from apps.core.services.simple_services import DatabaseStateManager

    # Update total results first
    session.total_results = summary["total_results"]
    session.save(update_fields=["total_results"])

    # Simple status transition
    success = DatabaseStateManager().set_session_status(
        session,
        "processing_results",
        detail=f"Processing {summary['total_results']} results from {summary['successful_count']} queries",
    )

    if not success:
        logger.error(f"Failed to transition session {session.id} to processing_results")

    return success


# Removed - functionality moved to monitoring_helpers.handle_session_state_transition


def _trigger_result_processing(session_id: str, countdown: int = 2) -> None:
    """
    Trigger result processing task.

    Args:
        session_id: Session ID to process
        countdown: Delay in seconds before processing
    """
    from .monitoring_helpers import trigger_next_phase_task

    trigger_next_phase_task(session_id, "processing_results", countdown)


@shared_task
def monitor_session_completion_task(session_id: str, monitor_count: int = 0):
    """
    Monitor search session completion and trigger next steps.

    This is the main monitoring task that checks if all executions are complete
    and transitions the session to the next state.

    Args:
        session_id: ID of the SearchSession
        monitor_count: Number of monitoring attempts (for timeout detection)

    Returns:
        dict: Dictionary with session summary including keys (session_id, status,
              successful, failed, total_results) or error information
    """
    from apps.core.env_config import get_env_bool
    from apps.review_manager.models import SearchSession

    from .monitoring_helpers import prepare_monitoring_result, process_monitoring_check

    # Check if unified monitoring is enabled - but still process completion!
    # The unified monitor handles stuck sessions, but we need this for immediate transitions
    if get_env_bool("USE_UNIFIED_MONITORING", default=False):
        logger.info(
            f"Unified monitor active, but still processing completion for {session_id}"
        )
        # Continue processing instead of returning early

    logger.info(f"Starting completion monitoring for session {session_id}")

    try:
        with transaction.atomic():
            # Process monitoring check - returns (should_continue, result)
            should_continue, result = process_monitoring_check(
                session_id, monitor_count
            )
            return result

    except SearchSession.DoesNotExist:
        logger.error(f"SearchSession {session_id} not found")
        return prepare_monitoring_result(session_id, "error", error="Session not found")

    except Exception as e:
        logger.error(f"Error monitoring session completion: {str(e)}")
        monitor_session_completion_task.apply_async(
            args=(session_id, monitor_count + 1), countdown=60
        )
        return prepare_monitoring_result(session_id, "error", error=str(e))
