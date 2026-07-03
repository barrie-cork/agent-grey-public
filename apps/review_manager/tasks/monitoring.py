"""
Monitoring tasks for workflow health and diagnostics.

This module contains tasks that monitor session health,
detect stuck workflows, and generate diagnostics.
"""

import logging

from celery import shared_task
from django.utils import timezone

from apps.review_manager.services.recovery_manager import WorkflowRecoveryManager

logger = logging.getLogger(__name__)


@shared_task
def monitor_workflow_health():
    """
    Periodic task to detect and recover stuck workflows.

    This task runs periodically to check for sessions that are stuck
    in various states and attempts automatic recovery. It should be
    scheduled to run every 10-15 minutes for optimal recovery time.

    Returns:
        Dictionary with recovery statistics
    """
    logger.info("Starting workflow health monitoring")

    try:
        recovery_manager = WorkflowRecoveryManager()
        results = recovery_manager.recover_stuck_sessions()

        # Log results if any issues were found
        if results["issues_detected"] > 0:
            logger.warning(
                f"Workflow monitoring detected {results['issues_detected']} issues. "
                f"Successfully recovered {results['recoveries_succeeded']} sessions, "
                f"{results['recoveries_failed']} recovery attempts failed."
            )

            # Log details for failed recoveries
            for detail in results["details"]:
                if not detail["recovery_success"]:
                    logger.error(
                        f"Failed to recover session {detail['session_id']} "
                        f"({detail['session_title']}) from status "
                        f"'{detail['original_status']}': {detail['details']}"
                    )
        else:
            logger.debug("Workflow monitoring completed - no issues detected")

        return results

    except Exception as e:
        logger.error(
            f"Workflow health monitoring failed: {type(e).__name__}: {str(e)}",
            exc_info=True,
        )
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "timestamp": timezone.now().isoformat(),
        }


@shared_task
def diagnose_session_health(session_id: str):
    """
    Generate detailed diagnostics for a specific session.

    This task can be triggered manually to get comprehensive information
    about a session's state and any potential issues.

    Args:
        session_id: UUID of the session to diagnose

    Returns:
        Dictionary with diagnostic information
    """
    logger.info(f"Running diagnostics for session {session_id}")

    try:
        recovery_manager = WorkflowRecoveryManager()
        diagnostics = recovery_manager.get_session_diagnostics(session_id)

        # Log any issues found
        if (
            diagnostics.get("health_check")
            and not diagnostics["health_check"]["healthy"]
        ):
            logger.warning(
                f"Session {session_id} health check failed: "
                f"{diagnostics['health_check']['issue']}"
            )

        return diagnostics

    except Exception as e:
        logger.error(
            f"Session diagnostics failed for {session_id}: {str(e)}", exc_info=True
        )
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "session_id": session_id,
            "timestamp": timezone.now().isoformat(),
        }
