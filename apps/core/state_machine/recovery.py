"""Recovery mechanisms for state machine failures."""

import logging
from datetime import timedelta
from typing import Any, Dict, List

from django.db import transaction
from django.utils import timezone

from .events import ErrorEvent, RecoveryEvent
from .state_machine import state_machine

logger = logging.getLogger(__name__)


class StateRecoveryService:
    """Service for recovering from state machine failures."""

    def __init__(self):
        self.state_machine = state_machine

    def recover_stuck_sessions(self, timeout_minutes: int = 30) -> List[str]:
        """
        Find and recover sessions stuck in automated states.

        Args:
            timeout_minutes: Minutes after which a session is considered stuck

        Returns:
            List of recovered session IDs
        """
        from apps.review_manager.models import SearchSession

        recovered = []
        timeout_threshold = timezone.now() - timedelta(minutes=timeout_minutes)

        # Find stuck sessions in automated states
        automated_states = self.state_machine.registry.get_automated_states()
        stuck_sessions = SearchSession.objects.filter(
            status__in=automated_states, updated_at__lt=timeout_threshold
        )

        logger.info(f"Found {stuck_sessions.count()} potentially stuck sessions")

        for session in stuck_sessions:
            try:
                if self._recover_session(session):
                    recovered.append(str(session.id))
            except Exception as e:
                logger.error(f"Failed to recover session {session.id}: {e}")
                self._emit_error_event(session.id, e)

        logger.info(f"Recovered {len(recovered)} stuck sessions")
        return recovered

    @transaction.atomic
    def _recover_session(self, session) -> bool:
        """
        Recover a single stuck session.

        Returns:
            True if recovery was successful
        """
        current_state = session.status
        recovery_action = None
        target_state = None

        # Determine recovery action based on current state
        if current_state == "executing":
            recovery_action, target_state = self._recover_from_executing(session)
        elif current_state == "processing_results":
            recovery_action, target_state = self._recover_from_processing(session)
        elif current_state == "ready_for_review":
            # This shouldn't be stuck, but move to under_review
            recovery_action = "auto_transition"
            target_state = "under_review"
        else:
            logger.warning(f"Unknown recovery for state {current_state}")
            return False

        if target_state:
            # Perform the recovery transition
            self.state_machine.force_transition(
                session.id,
                target_state,
                reason=f"Recovery from stuck state: {current_state}",
            )

            # Emit recovery event
            recovery_event = RecoveryEvent(
                session_id=str(session.id),
                recovery_action=recovery_action,
                original_state=current_state,
                recovered_state=target_state,
                reason="Session stuck timeout",
            )
            self.state_machine.event_bus.emit(recovery_event)

            logger.info(
                f"Recovered session {session.id}: "
                f"{current_state} -> {target_state} ({recovery_action})"
            )
            return True

        return False

    def _recover_from_executing(self, session) -> tuple[str, str]:
        """Determine recovery action for stuck executing state."""
        from apps.serp_execution.models import SearchExecution

        # Check if execution actually completed (any completed executions with results)
        if SearchExecution.objects.filter(
            query__session=session, status="completed"
        ).exists():
            # Has results, move to processing
            return "has_results", "processing_results"
        else:
            # No results, move back to ready_to_execute for retry
            return "retry_execution", "ready_to_execute"

    def _recover_from_processing(self, session) -> tuple[str, str]:
        """Determine recovery action for stuck processing state."""
        from apps.results_manager.models import ProcessedResult

        # Check if processing completed
        if ProcessedResult.objects.filter(session=session).exists():
            # Has processed results, move to review
            return "has_processed", "ready_for_review"
        else:
            # Check if there are raw results to process (completed executions)
            from apps.serp_execution.models import SearchExecution

            if SearchExecution.objects.filter(
                query__session=session, status="completed"
            ).exists():
                # Retry processing by triggering task again
                try:
                    from apps.serp_execution.tasks.simple_tasks import (
                        process_session_results_simple,
                    )

                    process_session_results_simple.delay(str(session.id))
                    logger.info(f"Re-triggered processing for session {session.id}")
                    return "retry_processing", "processing_results"
                except Exception as e:
                    logger.error(f"Failed to re-trigger processing: {e}")
                    return "failed_processing", "failed"
            else:
                # No completed executions, go back to ready_to_execute
                return "no_raw_results", "ready_to_execute"

    def _emit_error_event(self, session_id: str, error: Exception):
        """Emit an error event for failed recovery."""
        error_event = ErrorEvent(
            session_id=str(session_id),
            error_type=type(error).__name__,
            error_message=str(error),
            recoverable=False,
            metadata={"context": "recovery_failed"},
        )
        self.state_machine.event_bus.emit(error_event)

    def check_session_health(self, session_id: str) -> Dict[str, Any]:
        """
        Check the health of a specific session.

        Returns:
            Dictionary with health status and recommendations
        """
        from apps.review_manager.models import SearchSession

        try:
            session = SearchSession.objects.get(id=session_id)
            current_state = session.status

            health = {
                "session_id": str(session_id),
                "current_state": current_state,
                "is_healthy": True,
                "issues": [],
                "recommendations": [],
            }

            # Check if stuck in automated state
            if self.state_machine.is_automated_state(current_state):
                time_in_state = timezone.now() - session.updated_at
                if time_in_state > timedelta(minutes=30):
                    health["is_healthy"] = False
                    health["issues"].append(
                        f"Stuck in {current_state} for {time_in_state}"
                    )
                    health["recommendations"].append("Run recovery service")

            # Check for recent errors
            recent_errors = self.state_machine.event_store.get_error_events(
                session_id=str(session_id), limit=5
            )
            if recent_errors:
                health["recent_errors"] = len(recent_errors)
                health["last_error"] = recent_errors[0].get("error_message", "Unknown")

            # Check transition history
            history = self.state_machine.get_session_history(str(session_id))
            if history:
                health["transition_count"] = len(history)
                health["last_transition"] = history[-1] if history else None

            return health

        except SearchSession.DoesNotExist:
            return {
                "session_id": str(session_id),
                "is_healthy": False,
                "error": "Session not found",
            }
        except Exception as e:
            logger.error(f"Health check failed for {session_id}: {e}")
            return {"session_id": str(session_id), "is_healthy": False, "error": str(e)}


# Global recovery service instance
recovery_service = StateRecoveryService()
