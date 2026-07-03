"""
Workflow recovery manager for handling stuck sessions.

This service provides automatic detection and recovery of sessions
that become stuck in various states due to failures or timeouts.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Tuple

from django.db.models import Count, Q
from django.utils import timezone

from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_manager.services.state_manager import (
    SessionStateManager,
    StateTransitionError,
)

logger = logging.getLogger(__name__)


class WorkflowRecoveryManager:
    """
    Handles automatic recovery of stuck workflows.

    This class implements detection and recovery strategies for sessions
    that become stuck in various states. It uses configurable timeouts
    and health checks to determine when intervention is needed.
    """

    # Recovery rules define timeout and recovery strategy for each state
    RECOVERY_RULES = {
        "executing": {
            "timeout": timedelta(hours=1),
            "recovery_state": "ready_to_execute",
            "check_method": "check_executing_health",
            "description": "Execution timeout - no progress in 1 hour",
        },
        "processing_results": {
            "timeout": timedelta(minutes=30),
            "recovery_state": "ready_for_review",
            "check_method": "check_processing_health",
            "description": "Processing timeout - no progress in 30 minutes",
        },
        "ready_to_execute": {
            "timeout": timedelta(days=7),
            "recovery_state": "defining_search",
            "check_method": "check_ready_health",
            "description": "Session idle in ready state for 7 days",
        },
    }

    def __init__(self):
        """Initialize the recovery manager."""
        self.stats = {
            "sessions_checked": 0,
            "issues_detected": 0,
            "recoveries_attempted": 0,
            "recoveries_succeeded": 0,
            "recoveries_failed": 0,
        }

    def recover_stuck_sessions(self) -> Dict[str, Any]:
        """
        Main recovery method to find and fix stuck sessions.

        This method iterates through all potentially stuck states,
        identifies problematic sessions, and attempts recovery.

        Returns:
            Dictionary with recovery statistics and details
        """
        self.stats = {
            "sessions_checked": 0,
            "issues_detected": 0,
            "recoveries_attempted": 0,
            "recoveries_succeeded": 0,
            "recoveries_failed": 0,
            "details": [],
        }

        start_time = timezone.now()

        # Check each state that can get stuck
        for status, rules in self.RECOVERY_RULES.items():
            stuck_sessions = self._find_stuck_sessions(status, rules["timeout"])

            for session in stuck_sessions:
                self.stats["sessions_checked"] += 1

                # Attempt recovery
                success, details = self._attempt_recovery(session, rules)

                if success:
                    self.stats["recoveries_succeeded"] += 1
                else:
                    self.stats["recoveries_failed"] += 1

                self.stats["details"].append(
                    {
                        "session_id": str(session.id),
                        "session_title": session.title,
                        "original_status": status,
                        "recovery_success": success,
                        "details": details,
                    }
                )

        # Also check for orphaned states
        self._check_orphaned_states()

        # Calculate execution time
        execution_time = (timezone.now() - start_time).total_seconds()
        self.stats["execution_time_seconds"] = execution_time
        self.stats["timestamp"] = timezone.now().isoformat()

        # Log summary
        if self.stats["issues_detected"] > 0:
            logger.info(
                f"Recovery completed: {self.stats['issues_detected']} issues found, "
                f"{self.stats['recoveries_succeeded']} recovered, "
                f"{self.stats['recoveries_failed']} failed"
            )

        return self.stats

    def _find_stuck_sessions(
        self, status: str, timeout: timedelta
    ) -> List[SearchSession]:
        """
        Find sessions stuck in a specific status.

        Args:
            status: The status to check
            timeout: How long before considering it stuck

        Returns:
            List of stuck SearchSession instances
        """
        threshold = timezone.now() - timeout

        stuck_sessions = (
            SearchSession.objects.filter(status=status, updated_at__lt=threshold)
            .select_related("owner")
            .order_by("updated_at")
        )

        count = stuck_sessions.count()
        if count > 0:
            logger.info(f"Found {count} sessions stuck in '{status}' state")
            self.stats["issues_detected"] += count

        return stuck_sessions

    def _attempt_recovery(
        self, session: SearchSession, rules: Dict
    ) -> Tuple[bool, str]:
        """
        Attempt to recover a stuck session.

        Args:
            session: The stuck session
            rules: Recovery rules for this state

        Returns:
            Tuple of (success, details_message)
        """
        self.stats["recoveries_attempted"] += 1

        try:
            # Run health check
            check_method = getattr(self, rules["check_method"])
            is_healthy, reason = check_method(session)

            if is_healthy:
                # Session is actually healthy, just hasn't updated recently
                logger.debug(f"Session {session.id} is healthy, no recovery needed")
                return True, "Session is healthy, no intervention needed"

            # Log the issue
            logger.warning(
                f"Session {session.id} stuck in '{session.status}': {reason}"
            )

            # Attempt state recovery
            state_manager = SessionStateManager(session)

            # Try normal transition first
            try:
                success, error = state_manager.transition_to(
                    rules["recovery_state"],
                    metadata={
                        "recovery_reason": reason,
                        "auto_recovery": True,
                        "timeout_threshold": rules["timeout"].total_seconds(),
                        "stuck_duration": (
                            timezone.now() - session.updated_at
                        ).total_seconds(),
                    },
                )

                if success:
                    logger.info(
                        f"Successfully recovered session {session.id} from "
                        f"'{session.status}' to '{rules['recovery_state']}'"
                    )
                    return True, f"Recovered to {rules['recovery_state']}: {reason}"
                else:
                    # Normal transition returned False - log and try force transition
                    logger.warning(
                        f"Normal transition failed for session {session.id}: {error}"
                    )
                    raise StateTransitionError(error)

            except StateTransitionError:
                # Normal transition failed, try force transition
                logger.info(
                    f"Normal transition failed for session {session.id}, "
                    f"attempting force recovery"
                )

                success = state_manager.force_transition(
                    rules["recovery_state"], reason=f"Auto-recovery: {reason}"
                )

                if success:
                    return (
                        True,
                        f"Force-recovered to {rules['recovery_state']}: {reason}",
                    )
                else:
                    return False, "Force recovery failed"

        except Exception as e:
            logger.error(
                f"Recovery failed for session {session.id}: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            return False, f"Recovery error: {str(e)}"

    def check_executing_health(self, session: SearchSession) -> Tuple[bool, str]:
        """
        Check health of a session in 'executing' status.

        Args:
            session: Session to check

        Returns:
            Tuple of (is_healthy, reason)
        """
        from apps.search_strategy.models import SearchQuery
        from apps.serp_execution.models import SearchExecution

        # Check for any executions
        executions = SearchExecution.objects.filter(query__session=session)

        if not executions.exists():
            # No executions created
            active_queries = SearchQuery.objects.filter(
                session=session, is_active=True
            ).count()

            if active_queries == 0:
                return False, "No active queries to execute"
            else:
                return False, "Execution failed to create SearchExecution records"

        # Check execution statuses
        execution_stats = executions.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status="pending")),
            running=Count("id", filter=Q(status="running")),
            completed=Count("id", filter=Q(status="completed")),
            failed=Count("id", filter=Q(status="failed")),
        )

        # All executions are done (completed or failed)
        if execution_stats["pending"] == 0 and execution_stats["running"] == 0:
            if execution_stats["completed"] > 0:
                return False, f"All {execution_stats['total']} executions completed"
            else:
                return False, f"All {execution_stats['total']} executions failed"

        # Check if running executions are actually progressing
        running_executions = executions.filter(status="running")
        for execution in running_executions:
            if execution.started_at:
                runtime = timezone.now() - execution.started_at
                if runtime > timedelta(minutes=30):
                    return False, f"Execution {execution.id} running for {runtime}"

        # Session appears healthy
        return True, f"{execution_stats['running']} executions still running"

    def check_processing_health(self, session: SearchSession) -> Tuple[bool, str]:
        """
        Check health of a session in 'processing_results' status.

        Args:
            session: Session to check

        Returns:
            Tuple of (is_healthy, reason)
        """
        from apps.results_manager.models import ProcessingSession

        # Check for ProcessingSession
        processing_sessions = ProcessingSession.objects.filter(
            search_session=session
        ).order_by("-created_at")

        if not processing_sessions.exists():
            # No processing session created
            if session.total_results == 0:
                return False, "No results to process - should complete"
            else:
                return False, "ProcessingSession not created"

        # Check latest processing session
        latest_processing = processing_sessions.first()

        if latest_processing.status == "completed":
            return False, "Processing completed but session status not updated"
        elif latest_processing.status == "failed":
            return (
                False,
                f"Processing failed: {latest_processing.error_message or 'Unknown error'}",
            )
        elif latest_processing.status == "in_progress":
            # Check heartbeat
            if latest_processing.last_heartbeat:
                time_since_heartbeat = timezone.now() - latest_processing.last_heartbeat
                if time_since_heartbeat > timedelta(minutes=10):
                    return False, f"Processing heartbeat stale ({time_since_heartbeat})"
            else:
                return False, "Processing has no heartbeat"

        # Session appears healthy
        return (
            True,
            f"Processing in progress: {latest_processing.get_progress_display()}",
        )

    def check_ready_health(self, session: SearchSession) -> Tuple[bool, str]:
        """
        Check health of a session in 'ready_to_execute' status.

        This mainly checks for sessions that have been idle too long.

        Args:
            session: Session to check

        Returns:
            Tuple of (is_healthy, reason)
        """
        from apps.search_strategy.models import SearchQuery

        # Check if has queries
        active_queries = SearchQuery.objects.filter(
            session=session, is_active=True
        ).count()

        if active_queries == 0:
            return False, "No active queries defined after extended idle period"

        # Check last activity
        last_activity = (
            SessionActivity.objects.filter(session=session)
            .order_by("-created_at")
            .first()
        )

        if last_activity:
            time_since_activity = timezone.now() - last_activity.created_at
            if time_since_activity > timedelta(days=30):
                return False, f"No activity for {time_since_activity.days} days"

        # Session is just idle but healthy
        return True, "Session is idle but ready"

    def _check_orphaned_states(self) -> None:
        """
        Check for orphaned or inconsistent states.

        This method looks for data inconsistencies that might not be
        caught by the timeout-based checks.
        """
        # Check for sessions with 0 results but not in completed state
        zero_result_sessions = SearchSession.objects.filter(
            total_results=0,
            status__in=["processing_results", "ready_for_review", "under_review"],
        )

        for session in zero_result_sessions:
            self.stats["issues_detected"] += 1

            # Determine the correct target state based on current status
            state_manager = SessionStateManager(session)

            # Different handling based on current state
            if session.status == "processing_results":
                # Can go directly to completed from processing_results
                target_state = "completed"
            elif session.status == "ready_for_review":
                # Must go to archived from ready_for_review (completed not allowed)
                target_state = "archived"
            elif session.status == "under_review":
                # Can go to completed from under_review
                target_state = "completed"
            else:
                # Default to archived as safe option
                target_state = "archived"

            try:
                success, error = state_manager.transition_to(
                    target_state,
                    metadata={
                        "recovery_reason": "No results to process/review",
                        "auto_recovery": True,
                        "original_status": session.status,
                    },
                )
                if not success:
                    logger.warning(
                        f"Failed to transition session {session.id} to {target_state}: {error}"
                    )
                self.stats["recoveries_succeeded"] += 1

                self.stats["details"].append(  # type: ignore[union-attr]
                    {
                        "session_id": str(session.id),
                        "session_title": session.title,
                        "original_status": session.status,
                        "recovery_success": True,
                        "details": f"Moved to {target_state} (0 results)",
                    }
                )

            except Exception as e:
                self.stats["recoveries_failed"] += 1
                logger.error(
                    f"Failed to transition zero-result session {session.id} from "
                    f"{session.status} to {target_state}: {str(e)}"
                )

    def get_session_diagnostics(self, session_id: str) -> Dict[str, Any]:
        """
        Get detailed diagnostics for a specific session.

        This method provides comprehensive information about a session's
        state and any potential issues.

        Args:
            session_id: UUID of the session to diagnose

        Returns:
            Dictionary with diagnostic information
        """
        from apps.results_manager.models import ProcessedResult, ProcessingSession
        from apps.review_manager.validators import WorkflowValidator
        from apps.search_strategy.models import SearchQuery
        from apps.serp_execution.models import SearchExecution

        try:
            session = SearchSession.objects.get(id=session_id)
        except SearchSession.DoesNotExist:
            return {"error": f"Session {session_id} not found"}

        # Basic session info
        diagnostics = {
            "session_id": str(session.id),
            "title": session.title,
            "status": session.status,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "time_in_current_status": (
                timezone.now() - session.updated_at
            ).total_seconds(),
            "owner": session.owner.email if session.owner else "Unknown",
        }

        # Query information
        queries = SearchQuery.objects.filter(session=session)
        diagnostics["queries"] = {
            "total": queries.count(),
            "active": queries.filter(is_active=True).count(),
            "inactive": queries.filter(is_active=False).count(),
        }

        # Execution information
        executions = SearchExecution.objects.filter(query__session=session)
        execution_stats = executions.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status="pending")),
            running=Count("id", filter=Q(status="running")),
            completed=Count("id", filter=Q(status="completed")),
            failed=Count("id", filter=Q(status="failed")),
        )
        diagnostics["executions"] = execution_stats

        # Processing information
        processing = ProcessingSession.objects.filter(search_session=session).first()
        if processing:
            diagnostics["processing"] = {
                "status": processing.status,
                "created_at": processing.created_at.isoformat(),
                "last_heartbeat": (
                    processing.last_heartbeat.isoformat()
                    if processing.last_heartbeat
                    else None
                ),
                "progress": processing.get_progress_display(),
            }
        else:
            diagnostics["processing"] = None

        # Results information
        diagnostics["results"] = {
            "total_results": session.total_results,
            "reviewed_results": session.reviewed_results,
            "included_results": session.included_results,
            "processed_count": ProcessedResult.objects.filter(
                raw_result__execution__query__session=session
            ).count(),
        }

        # Validation checks
        validator = WorkflowValidator()
        diagnostics["validations"] = {}

        # Check various transitions
        for transition, method in [
            ("executing", validator.can_execute),
            ("processing_results", validator.can_process_results),
            ("ready_for_review", validator.can_review),
            ("completed", validator.can_complete),
        ]:
            can_transition, reason = method(session)
            diagnostics["validations"][f"can_move_to_{transition}"] = {
                "allowed": can_transition,
                "reason": reason,
            }

        # Data integrity check
        is_valid, integrity_report = validator.validate_session_data_integrity(session)
        diagnostics["data_integrity"] = {"valid": is_valid, "report": integrity_report}

        # Recent activities
        recent_activities = SessionActivity.objects.filter(session=session).order_by(
            "-created_at"
        )[:5]

        diagnostics["recent_activities"] = [
            {
                "type": activity.activity_type,
                "description": activity.description,
                "created_at": activity.created_at.isoformat(),
                "metadata": activity.metadata,
            }
            for activity in recent_activities
        ]

        # Diagnosis
        if session.status in self.RECOVERY_RULES:
            rules = self.RECOVERY_RULES[session.status]
            check_method = getattr(self, rules["check_method"])
            is_healthy, issue = check_method(session)

            diagnostics["health_check"] = {
                "healthy": is_healthy,
                "issue": issue if not is_healthy else None,
                "timeout_seconds": rules["timeout"].total_seconds(),
                "would_recover_to": rules["recovery_state"] if not is_healthy else None,
            }
        else:
            diagnostics["health_check"] = {
                "healthy": True,
                "issue": None,
                "note": f"No automatic recovery rules for status '{session.status}'",
            }

        return diagnostics

    def recover_session(self, session: Any) -> Dict[str, Any]:
        """
        Attempt to recover a specific stuck session.

        Args:
            session: SearchSession instance to recover

        Returns:
            Dictionary with recovery result including success, original_status,
            new_status, duration_ms, and optional error
        """
        start_time = timezone.now()
        original_status = session.status

        recovery_rule = self.RECOVERY_RULES.get(original_status)
        if not recovery_rule:
            duration_ms = (timezone.now() - start_time).total_seconds() * 1000
            return {
                "success": False,
                "original_status": original_status,
                "new_status": original_status,
                "duration_ms": duration_ms,
                "error": f"No recovery rule for status: {original_status}",
            }

        success, details = self._attempt_recovery(session, recovery_rule)
        duration_ms = (timezone.now() - start_time).total_seconds() * 1000

        return {
            "success": success,
            "original_status": original_status,
            "new_status": recovery_rule["recovery_state"]
            if success
            else original_status,
            "duration_ms": duration_ms,
            "error": None if success else details,
        }
