"""
Monitoring tasks for detecting and fixing stuck sessions.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.utils import timezone

from apps.results_manager.models import ProcessingSession
from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_manager.services.recovery_manager import WorkflowRecoveryManager
from apps.review_manager.services.state_manager import StateTransitionError

logger = logging.getLogger(__name__)

# Import Sentry monitor decorator for Crons integration
try:
    from sentry_sdk.crons import monitor

    SENTRY_AVAILABLE = True
except ImportError:
    # Fallback if Sentry SDK is not available
    def monitor(monitor_slug=None):
        def decorator(func):
            return func

        return decorator

    SENTRY_AVAILABLE = False


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
# @monitor(monitor_slug='check-stuck-sessions')  # Disabled - replaced by unified-session-monitor
def check_stuck_sessions(self):
    """
    Periodic task to detect and fix sessions stuck in processing states.

    This task now delegates to the WorkflowRecoveryManager for comprehensive
    session recovery. It provides backward compatibility for existing
    scheduled tasks while using the centralized recovery logic.

    The task is integrated with Sentry Crons monitoring via the @monitor
    decorator to provide check-in tracking and failure detection.

    Returns:
        Dictionary with counts of detected and fixed sessions
    """
    logger.info(
        f"Starting stuck session check via recovery manager "
        f"(Sentry monitoring: {'enabled' if SENTRY_AVAILABLE else 'disabled'})"
    )

    # Initialize Sentry monitoring
    capture_exception = _init_sentry_monitoring(self.request.retries)

    # Check for clock drift (optional, non-blocking)
    clock_drift_warning, clock_status = _check_clock_health()

    try:
        # Use the centralized recovery manager
        recovery_manager = WorkflowRecoveryManager()
        logger.debug("WorkflowRecoveryManager instance created, attempting recovery")

        results = recovery_manager.recover_stuck_sessions()

        logger.info(
            f"Stuck session check completed: detected={results.get('issues_detected', 0)}, "
            f"fixed={results.get('recoveries_succeeded', 0)}"
        )

        return _build_success_result(results, clock_drift_warning, clock_status)

    except (DatabaseError, ValidationError, StateTransitionError) as e:
        return _handle_known_error(self, e, capture_exception)

    except Exception as e:
        return _handle_unexpected_error(self, e, capture_exception, clock_drift_warning)


def _init_sentry_monitoring(retry_count):
    """Initialize Sentry monitoring breadcrumb."""
    try:
        from sentry_sdk import add_breadcrumb, capture_exception

        add_breadcrumb(
            category="monitoring",
            message="check_stuck_sessions task started",
            level="info",
            data={"retry": retry_count},
        )
        return capture_exception
    except ImportError:
        return None


def _check_clock_health():
    """Check for clock drift (optional, non-blocking)."""
    try:
        from apps.core.monitoring.clock_utils import check_clock_health

        clock_status = check_clock_health()

        if clock_status.get("drift_seconds", 0) > 30:
            logger.warning(
                f"Significant clock drift detected: {clock_status['drift_seconds']}s. "
                "Task may not execute properly."
            )
            return True, clock_status

        return False, clock_status

    except ImportError:
        logger.debug("Clock health check module not available")
    except Exception as e:
        logger.debug(f"Clock health check failed (non-critical): {e}")

    return False, {}


def _build_success_result(results, clock_drift_warning, clock_status):
    """Build success result with optional clock drift warning."""
    result = {
        "detected": results.get("issues_detected", 0),
        "fixed": results.get("recoveries_succeeded", 0),
        "timestamp": results.get("timestamp", timezone.now().isoformat()),
        "recovery_details": results.get("details", []),
    }

    if clock_drift_warning:
        result["clock_drift_warning"] = True
        result["clock_status"] = clock_status

    return result


def _handle_known_error(task, error, capture_exception):
    """Handle known error types (Database, Validation, StateTransition)."""
    logger.error(
        f"Recovery failed with known error type {type(error).__name__}: {str(error)}",
        exc_info=True,
        extra={
            "error_type": type(error).__name__,
            "error_message": str(error),
            "task": "check_stuck_sessions",
            "retry": task.request.retries,
        },
    )

    # Retry for database errors with exponential backoff
    if isinstance(error, DatabaseError) and task.request.retries < task.max_retries:
        logger.warning(
            f"Retrying check_stuck_sessions after database error "
            f"(attempt {task.request.retries + 1}/{task.max_retries})"
        )
        raise task.retry(exc=error, countdown=300 * (task.request.retries + 1))

    # For validation errors, return error info without retry
    return {
        "detected": 0,
        "fixed": 0,
        "error": str(error),
        "error_type": type(error).__name__,
        "timestamp": timezone.now().isoformat(),
    }


def _handle_unexpected_error(task, error, capture_exception, clock_drift_warning):
    """Handle unexpected error types."""
    logger.exception(
        f"Unexpected error during stuck session check: {type(error).__name__}",
        extra={
            "error_type": type(error).__name__,
            "error_message": str(error),
            "task": "check_stuck_sessions",
            "retry": task.request.retries,
        },
    )

    # Capture to Sentry
    if capture_exception:
        capture_exception(error)

    # Retry for connection errors with exponential backoff
    if task.request.retries < task.max_retries and isinstance(
        error, (ConnectionError, TimeoutError)
    ):
        logger.warning(
            f"Retrying check_stuck_sessions after connection error "
            f"(attempt {task.request.retries + 1}/{task.max_retries})"
        )
        raise task.retry(exc=error, countdown=300 * (task.request.retries + 1))

    # For all other errors or after max retries, return error info
    return {
        "detected": 0,
        "fixed": 0,
        "error": str(error),
        "error_type": type(error).__name__,
        "timestamp": timezone.now().isoformat(),
        "final_attempt": task.request.retries >= task.max_retries,
        "clock_drift_warning": clock_drift_warning,
    }


@shared_task(
    name="apps.results_manager.tasks.monitoring.cleanup_orphaned_processing_sessions"
)
def cleanup_orphaned_processing_sessions():
    """
    Clean up ProcessingSession records that have no corresponding SearchSession.

    Returns:
        Count of orphaned records cleaned up
    """
    try:
        orphaned = ProcessingSession.objects.filter(search_session__isnull=True)

        count = orphaned.count()
        if count > 0:
            logger.warning(f"Cleaning up {count} orphaned ProcessingSession records")
            orphaned.delete()

        return count
    except Exception as e:
        logger.error(
            f"Failed to clean up orphaned processing sessions: {e}", exc_info=True
        )
        return 0


def _check_sessions_without_executions():
    """
    Check for sessions marked as executing but with no executions.

    Returns:
        Tuple of (detected_count, fixed_count)
    """
    from django.db.models import Count

    detected = 0
    fixed = 0

    executing_sessions = SearchSession.objects.filter(status="executing").annotate(
        execution_count=Count("search_strategy__search_queries__executions")
    )

    for session in executing_sessions:
        if session.execution_count == 0:
            detected += 1

            # Session marked as executing but no executions created
            time_since_update = timezone.now() - session.updated_at

            if time_since_update > timedelta(minutes=5):
                if _fix_stuck_executing_session(session, time_since_update):
                    fixed += 1

    return detected, fixed


def _fix_stuck_executing_session(session, time_since_update):
    """
    Fix a single stuck executing session.

    Args:
        session: The stuck SearchSession
        time_since_update: Time since last update

    Returns:
        bool: True if fixed, False otherwise
    """
    logger.warning(
        f"Session {session.id} stuck in executing with no executions "
        f"for {time_since_update}"
    )

    # Determine target status based on query availability
    has_queries = _check_has_active_queries(session)
    new_status = "ready_to_execute" if has_queries else "strategy_defined"

    # Update session status
    _update_session_status(session, "executing", new_status)

    # Log the fix
    _log_session_fix(session, "executing", new_status, has_queries)

    logger.info(f"Fixed session {session.id} stuck in executing")
    return True


def _check_has_active_queries(session):
    """Check if session has active queries."""
    from apps.search_strategy.models import SearchQuery

    return SearchQuery.objects.filter(session=session, is_active=True).exists()


def _update_session_status(session, old_status, new_status):
    """Update session status and clear started_at."""
    session.status = new_status
    session.started_at = None
    session.save(update_fields=["status", "started_at"])


def _log_session_fix(session, old_status, new_status, has_queries):
    """Log the session fix activity."""
    if has_queries:
        description = "Auto-fixed: Execution failed to start"
        reason = "No executions created"
    else:
        description = "Auto-fixed: No queries to execute"
        reason = "No active queries found"

    SessionActivity.objects.create(
        session=session,
        user=session.owner,
        activity_type="status_change",
        description=description,
        metadata={"old_status": old_status, "new_status": new_status, "reason": reason},
    )


def _check_sessions_with_completed_executions():
    """
    Check for sessions where all executions are done but status not updated.

    Returns:
        Tuple of (detected_count, fixed_count)
    """
    from django.db.models import Count, Q

    detected = 0
    fixed = 0

    sessions_with_completed = SearchSession.objects.filter(status="executing").annotate(
        total_executions=Count("search_strategy__search_queries__executions"),
        completed_executions=Count(
            "search_strategy__search_queries__executions",
            filter=Q(
                search_strategy__search_queries__executions__status__in=[
                    "completed",
                    "failed",
                    "cancelled",
                ]
            ),
        ),
    )

    for session in sessions_with_completed:
        if (
            session.total_executions > 0
            and session.total_executions == session.completed_executions
        ):
            detected += 1

            # All executions done but status not updated
            time_since_update = timezone.now() - session.updated_at

            if time_since_update > timedelta(minutes=10):
                if _trigger_completion_monitoring(session):
                    fixed += 1

    return detected, fixed


def _trigger_completion_monitoring(session):
    """
    Trigger completion monitoring for a session.

    Args:
        session: The SearchSession to monitor

    Returns:
        bool: True if triggered successfully
    """
    logger.warning(
        f"Session {session.id} has all executions completed but "
        f"still in executing status"
    )

    # Trigger the completion monitor
    from apps.serp_execution.tasks import monitor_session_completion_task

    monitor_session_completion_task.delay(str(session.id))

    logger.info(f"Triggered completion monitoring for session {session.id}")
    return True


def _check_orphaned_executions():
    """
    Check for executions without associated sessions.

    Returns:
        int: Number of orphaned executions found
    """
    from apps.serp_execution.models import SearchExecution

    orphaned_executions = SearchExecution.objects.filter(query__session__isnull=True)

    orphan_count = orphaned_executions.count()
    if orphan_count > 0:
        logger.warning(f"Found {orphan_count} orphaned executions")
        # Don't delete automatically - just log for manual review

    return orphan_count


@shared_task
def check_stuck_executions():
    """
    Monitor for sessions stuck in execution states.

    This task complements check_stuck_sessions by focusing on
    execution-phase issues.
    """
    try:
        detected_no_exec, fixed_no_exec = _check_sessions_without_executions()
        detected_complete, fixed_complete = _check_sessions_with_completed_executions()
        orphan_count = _check_orphaned_executions()

        result = {
            "detected": detected_no_exec + detected_complete + orphan_count,
            "fixed": fixed_no_exec + fixed_complete,
            "orphaned_executions": orphan_count,
            "timestamp": timezone.now().isoformat(),
        }

        if result["detected"] > 0:
            logger.info(f"Execution monitoring complete: {result}")

        return result
    except Exception as e:
        logger.error(f"Stuck execution check failed: {e}", exc_info=True)
        return {
            "detected": 0,
            "fixed": 0,
            "error": str(e),
            "timestamp": timezone.now().isoformat(),
        }
