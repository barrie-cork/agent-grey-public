"""
Maintenance tasks for session cleanup and statistics.

This module contains tasks that clean up old sessions
and update session statistics.
"""

import logging

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from apps.review_manager.models import SearchSession

logger = logging.getLogger(__name__)


@shared_task
def cleanup_old_sessions(days_old: int = 365):
    """
    Clean up old archived sessions.

    This task removes sessions that have been archived for more than
    the specified number of days. It helps maintain database performance
    by removing old data that is no longer needed.

    Args:
        days_old: Number of days after which to delete archived sessions

    Returns:
        Dictionary with cleanup statistics
    """
    logger.info(f"Starting cleanup of sessions archived more than {days_old} days ago")

    try:
        cutoff_date = timezone.now() - timezone.timedelta(days=days_old)

        # Find old archived sessions
        old_sessions = SearchSession.objects.filter(
            status="archived", updated_at__lt=cutoff_date
        )

        # Get count before deletion
        count = old_sessions.count()

        if count > 0:
            # Log sessions being deleted
            for session in old_sessions[:10]:  # Log first 10
                logger.info(
                    f"Deleting archived session {session.id} ({session.title}) "
                    f"last updated {session.updated_at}"
                )

            if count > 10:
                logger.info(f"... and {count - 10} more sessions")

            # Delete the sessions (cascade will handle related records)
            old_sessions.delete()

            logger.info(f"Successfully deleted {count} old archived sessions")
        else:
            logger.info("No old archived sessions found to delete")

        return {
            "sessions_deleted": count,
            "cutoff_date": cutoff_date.isoformat(),
            "timestamp": timezone.now().isoformat(),
        }

    except Exception as e:
        logger.error(
            f"Session cleanup failed: {type(e).__name__}: {str(e)}", exc_info=True
        )
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": timezone.now().isoformat(),
        }


@shared_task
def auto_fix_stuck_sessions():
    """
    Automatically detect and fix stuck sessions.

    This task runs every 5 minutes via Celery beat to identify
    and recover sessions that are stuck in executing or processing states.

    Returns:
        Dictionary with recovery statistics
    """
    from io import StringIO

    from django.core.management import call_command

    logger.info("Starting automatic stuck session recovery")

    try:
        # Run the fix_stuck_sessions command
        out = StringIO()
        err = StringIO()

        call_command("fix_stuck_sessions", timeout_minutes=30, stdout=out, stderr=err)

        result = out.getvalue()
        error_output = err.getvalue()

        # Parse results
        sessions_found = 0
        sessions_fixed = 0

        if "Found" in result:
            import re

            found_match = re.search(r"Found (\d+) stuck sessions", result)
            if found_match:
                sessions_found = int(found_match.group(1))

        if "Fixed:" in result:
            sessions_fixed = result.count("Fixed:")

        # Log if sessions were recovered
        if sessions_found > 0:
            logger.warning(
                f"Auto-recovery: Found {sessions_found} stuck sessions, "
                f"successfully recovered {sessions_fixed}"
            )

        return {
            "sessions_found": sessions_found,
            "sessions_recovered": sessions_fixed,
            "output": result,
            "errors": error_output,
            "timestamp": timezone.now().isoformat(),
        }

    except Exception as e:
        logger.error(
            f"Auto-recovery failed: {type(e).__name__}: {str(e)}", exc_info=True
        )
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": timezone.now().isoformat(),
        }


@shared_task
def check_workflow_health():
    """
    Comprehensive workflow health check with alerting.

    This task monitors overall workflow health and triggers
    alerts when issues are detected. Runs every 10 minutes.

    Returns:
        Dictionary with health check results
    """
    from apps.core.monitoring.alerts import WorkflowAlertManager
    from apps.core.monitoring.metrics import TransitionMetrics

    logger.info("Starting workflow health check")

    try:
        # Check for alerts
        alert_manager = WorkflowAlertManager()
        alert_results = alert_manager.check_and_alert()

        # Get transition metrics
        metrics = TransitionMetrics()
        transition_stats = metrics.get_transition_stats(time_window_hours=1)

        # Get stuck session count
        stuck_threshold = timezone.now() - timezone.timedelta(minutes=30)
        stuck_sessions = SearchSession.objects.filter(
            Q(status="executing", updated_at__lt=stuck_threshold)
            | Q(status="processing_results", updated_at__lt=stuck_threshold)
        ).count()

        health_status = {
            "healthy": stuck_sessions == 0 and alert_results.get("alerts_sent", 0) == 0,
            "stuck_sessions": stuck_sessions,
            "alerts_triggered": alert_results.get("alerts_triggered", []),
            "transition_stats": transition_stats,
            "timestamp": timezone.now().isoformat(),
        }

        if not health_status["healthy"]:
            logger.warning(
                f"Workflow health check: {stuck_sessions} stuck sessions, "
                f"{len(health_status['alerts_triggered'])} alerts triggered"
            )

        return health_status

    except Exception as e:
        logger.error(
            f"Health check failed: {type(e).__name__}: {str(e)}", exc_info=True
        )
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": timezone.now().isoformat(),
        }


@shared_task
def recover_stuck_sessions(  # noqa: C901 - Session recovery
    alert_threshold=5, max_resume_tasks=3
):
    """
    Automatically recover sessions stuck in executing state and alert if too many.
    Runs every 5 minutes via Celery beat.

    This implements the approach from Issue #83 for automatic recovery.
    Combines recovery with alerting functionality.

    Args:
        alert_threshold: Number of stuck sessions that triggers an alert (default: 5)
        max_resume_tasks: Maximum number of resume tasks to queue per run (default: 3)
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.results_manager.models import ProcessedResult

    logger.info(
        f"Starting automatic stuck session recovery and monitoring (max resume: {max_resume_tasks})"
    )

    try:
        # Find sessions stuck in executing state for more than 10 minutes
        stuck_sessions = SearchSession.objects.filter(
            status="executing", updated_at__lt=timezone.now() - timedelta(minutes=10)
        )

        recovery_stats = {
            "sessions_found": stuck_sessions.count(),
            "sessions_recovered": 0,
            "sessions_archived": 0,
            "sessions_resumed": 0,
            "timestamp": timezone.now().isoformat(),
        }

        from django.db import transaction

        resume_count = 0  # Track number of resume tasks queued

        for session in stuck_sessions:
            should_resume = False
            try:
                with transaction.atomic():
                    # Lock the session row to prevent concurrent modifications
                    session = SearchSession.objects.select_for_update().get(
                        id=session.id
                    )

                    # Re-check status in case it changed
                    if session.status != "executing":
                        logger.info(
                            f"Session {session.id} status changed, skipping recovery"
                        )
                        continue

                    # Check if session has results
                    result_count = ProcessedResult.objects.filter(
                        session=session
                    ).count()

                    age = timezone.now() - session.updated_at

                    if result_count > 0:
                        # Has results, move to review
                        session.status = "ready_for_review"
                        session.save()
                        recovery_stats["sessions_recovered"] += 1
                        logger.info(
                            f"Recovered session {session.id} with {result_count} results"
                        )

                    elif age > timedelta(hours=1):
                        # No results after 1 hour, archive
                        session.status = "archived"
                        session.save()
                        recovery_stats["sessions_archived"] += 1
                        logger.warning(
                            f"Archived stuck session {session.id} after {age}"
                        )

                    else:
                        # Try to resume search (outside transaction to avoid holding lock)
                        # Check rate limit before marking for resume
                        if resume_count < max_resume_tasks:
                            should_resume = True
                        else:
                            logger.warning(
                                f"Rate limit reached, skipping resume for session {session.id}"
                            )

                if should_resume:
                    try:
                        from apps.serp_execution.tasks import (
                            execute_search_session_simple,
                        )

                        execute_search_session_simple.delay(str(session.id))
                        recovery_stats["sessions_resumed"] += 1
                        resume_count += 1
                        logger.info(
                            f"Attempting to resume session {session.id} ({resume_count}/{max_resume_tasks})"
                        )
                    except Exception as e:
                        logger.error(f"Failed to resume session {session.id}: {e}")

            except Exception as e:
                logger.error(f"Failed to process session {session.id}: {e}")

        if recovery_stats["sessions_found"] > 0:
            logger.warning(
                f"Stuck session recovery: Found {recovery_stats['sessions_found']} stuck sessions, "
                f"recovered {recovery_stats['sessions_recovered']}, "
                f"archived {recovery_stats['sessions_archived']}, "
                f"resumed {recovery_stats['sessions_resumed']}"
            )

            # Send alert if too many stuck sessions
            if recovery_stats["sessions_found"] > alert_threshold:
                logger.error(
                    f"HIGH STUCK SESSION COUNT: "
                    f"{recovery_stats['sessions_found']} sessions stuck "
                    f"(threshold: {alert_threshold})"
                )
                try:
                    import sentry_sdk

                    if sentry_sdk.is_initialized():
                        with sentry_sdk.new_scope() as scope:
                            scope.set_tag("component", "session_recovery")
                            scope.set_tag("alert_type", "high_stuck_count")
                            scope.set_context("recovery_stats", recovery_stats)
                            sentry_sdk.capture_message(
                                (
                                    f"High stuck session count: "
                                    f"{recovery_stats['sessions_found']} sessions "
                                    f"stuck (threshold: {alert_threshold})"
                                ),
                                level="error",
                            )
                except ImportError:
                    pass  # Sentry not configured

        return recovery_stats

    except Exception as e:
        logger.error(
            f"Stuck session recovery failed: {type(e).__name__}: {str(e)}",
            exc_info=True,
        )
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": timezone.now().isoformat(),
        }


# Note: check_stuck_sessions functionality has been merged into recover_stuck_sessions
# to avoid duplication and provide both monitoring and recovery in one task
# The recover_stuck_sessions task now includes alerting when threshold is exceeded


@shared_task
def comprehensive_recovery():
    """
    Comprehensive system recovery task.

    This task performs a full system recovery including:
    - Stuck session recovery
    - Orphaned result cleanup
    - Statistics recalculation
    - Cache refresh

    Runs hourly for thorough system maintenance.

    Returns:
        Dictionary with comprehensive recovery results
    """
    from apps.review_manager.services.recovery_manager import WorkflowRecoveryManager

    logger.info("Starting comprehensive system recovery")

    results = {
        "timestamp": timezone.now().isoformat(),
        "stuck_sessions": {},
        "statistics_update": {},
        "cleanup": {},
    }

    try:
        # 1. Recover stuck sessions
        recovery_manager = WorkflowRecoveryManager()
        results["stuck_sessions"] = recovery_manager.recover_stuck_sessions()

        # 2. Update session statistics
        stats_result = update_session_statistics.apply()
        results["statistics_update"] = stats_result.result

        # 3. Clean up old sessions
        cleanup_result = cleanup_old_sessions.apply(args=(90,))  # 90 days
        results["cleanup"] = cleanup_result.result

        # Log summary
        logger.info(
            f"Comprehensive recovery completed: "
            f"{results['stuck_sessions'].get('recoveries_succeeded', 0)} sessions recovered, "
            f"{results['statistics_update'].get('sessions_updated', 0)} statistics updated, "
            f"{results['cleanup'].get('sessions_deleted', 0)} old sessions cleaned"
        )

        return results

    except Exception as e:
        logger.error(
            f"Comprehensive recovery failed: {type(e).__name__}: {str(e)}",
            exc_info=True,
        )
        results["error"] = str(e)
        results["error_type"] = type(e).__name__
        return results


@shared_task
def update_session_statistics():
    """
    Update statistics for all active sessions.

    Delegates to the signal-level update_session_statistics function which
    correctly handles both Workflow #1 (SimpleReviewDecision) and Workflow #2
    (ReviewerDecision) sessions, counting ProcessedResults for total_results
    and using the appropriate decision model for reviewed/included counts.

    Returns:
        Dictionary with update statistics.
    """
    from apps.review_manager.signals_denormalized import (
        update_session_statistics as sync_session_stats,
    )

    logger.info("Starting session statistics update")

    try:
        active_session_ids = list(
            SearchSession.objects.filter(
                status__in=[
                    "executing",
                    "processing_results",
                    "ready_for_review",
                    "under_review",
                ]
            ).values_list("id", flat=True)
        )

        updated_count = 0

        for session_id in active_session_ids:
            try:
                # Capture before-values for change detection logging
                session_before = (
                    SearchSession.objects.filter(id=session_id)
                    .values("total_results", "reviewed_results", "included_results")
                    .first()
                )

                sync_session_stats(session_id)

                # Check if values changed
                session_after = (
                    SearchSession.objects.filter(id=session_id)
                    .values("total_results", "reviewed_results", "included_results")
                    .first()
                )

                if session_before and session_after and session_before != session_after:
                    updated_count += 1

            except Exception as e:
                logger.warning(
                    f"Failed to update statistics for session {session_id}: {e}"
                )

        logger.info(
            f"Updated statistics for {updated_count} of "
            f"{len(active_session_ids)} sessions"
        )

        return {
            "sessions_checked": len(active_session_ids),
            "sessions_updated": updated_count,
            "timestamp": timezone.now().isoformat(),
        }

    except Exception as e:
        logger.error(
            f"Session statistics update failed: {type(e).__name__}: {str(e)}",
            exc_info=True,
        )
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": timezone.now().isoformat(),
        }
