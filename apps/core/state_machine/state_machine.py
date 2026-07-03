"""Core state machine implementation."""

import logging
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from apps.core.utils.distributed_lock import DistributedLock, LockConfig

from .event_bus import event_bus
from .event_store import event_store
from .events import ErrorEvent, ProgressEvent, RecoveryEvent, StateTransitionEvent
from .exceptions import InvalidTransition, LockAcquisitionFailed, StateNotFound
from .registry import state_registry

logger = logging.getLogger(__name__)


class SessionStateMachine:
    """
    Single source of truth for all state transitions.
    Replaces scattered logic across multiple services with a unified event-driven approach.
    """

    def __init__(self):
        # Initialize distributed lock with configuration
        self.lock_config = LockConfig(
            timeout=30, retry_count=3, use_exponential_backoff=True
        )
        self.lock = DistributedLock(self.lock_config)
        self.registry = state_registry
        self.event_bus = event_bus
        self.event_store = event_store

        # Register default event listeners
        self._register_default_listeners()

    def _register_default_listeners(self):
        """Register default event listeners."""

        # Persist all events
        def persist_event(event):
            self.event_store.save_event(event)
            logger.debug(f"Persisted {event.__class__.__name__}: {event.event_id}")

        # Subscribe to all events for persistence
        self.event_bus.subscribe_all(persist_event)

        # Auto-trigger tasks for automated transitions
        def handle_state_transition(event):
            if isinstance(event, StateTransitionEvent):
                self._trigger_automated_tasks(event)

        self.event_bus.subscribe("state_transition", handle_state_transition)

    def can_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a transition is allowed."""
        return self.registry.can_transition(from_state, to_state)

    def is_backwards_transition(self, from_state: str, to_state: str) -> bool:
        """
        Check if a transition is going backwards in the workflow.

        This helps prevent invalid backwards transitions that can cause state
        desynchronization issues. Some backwards transitions are allowed (e.g.,
        to 'defining_search' for re-configuration, or to 'archived').

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            True if the transition is backwards and should be blocked
        """
        # Define the forward progression order
        forward_progression = [
            "draft",
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
            "completed",
            "archived",
        ]

        # Special cases - these are always allowed
        allowed_backwards = [
            "defining_search",  # Can always go back to reconfigure
            "archived",  # Can archive from any state
            "draft",  # Can reset to draft (for recovery)
            "failed",  # Can fail from executing states
        ]

        if to_state in allowed_backwards:
            return False

        # Check if it's a backwards transition
        try:
            from_index = forward_progression.index(from_state)
            to_index = forward_progression.index(to_state)

            # It's backwards if to_index < from_index
            is_backwards = to_index < from_index

            if is_backwards:
                logger.warning(
                    f"Backwards transition detected: {from_state} -> {to_state}. "
                    f"Forward index: {from_index} -> {to_index}"
                )

            return is_backwards

        except ValueError:
            # State not in progression list (e.g., 'failed')
            return False

    def is_automated_state(self, state: str | None) -> bool:
        """Check if a state should be automatically transitioned."""
        if state is None:
            return False
        state_def = self.registry.get_state(state)
        return state_def.is_automated if state_def else False

    def get_current_state(self, session_id: str) -> str:
        """Get the current state of a session."""
        from apps.review_manager.models import SearchSession

        try:
            session = SearchSession.objects.get(id=session_id)
            return session.status
        except SearchSession.DoesNotExist:
            raise StateNotFound(f"Session {session_id} not found")

    @transaction.atomic
    def transition(
        self,
        session_id: str,
        target_state: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        triggered_by: str = "system",
    ) -> StateTransitionEvent:
        """
        Perform a state transition with full validation and event emission.

        Args:
            session_id: UUID of the session
            target_state: Target state to transition to
            metadata: Optional metadata for the transition
            user_id: Optional user ID who triggered the transition
            triggered_by: Source of transition ('system', 'user', 'task')

        Returns:
            StateTransitionEvent object

        Raises:
            InvalidTransition: If transition is not allowed
            LockAcquisitionFailed: If unable to acquire lock
        """
        lock_key = f"session:state:{session_id}"

        try:
            # Acquire distributed lock
            with self.lock.acquire(lock_key, timeout=30):
                return self._perform_transition(
                    session_id, target_state, metadata, user_id, triggered_by
                )
        except InvalidTransition:
            # Re-raise InvalidTransition exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Failed to acquire lock for session {session_id}: {e}")
            raise LockAcquisitionFailed(
                f"Could not acquire lock for session {session_id}"
            )

    def _perform_transition(
        self,
        session_id: str,
        target_state: str,
        metadata: Optional[Dict[str, Any]],
        user_id: Optional[str],
        triggered_by: str,
    ) -> StateTransitionEvent:
        """Internal method to perform the actual transition."""
        from apps.review_manager.models import SearchSession, SessionActivity

        # Get session with row lock
        session = SearchSession.objects.select_for_update().get(id=session_id)
        old_state = session.status

        # Validate transition
        if not self.can_transition(old_state, target_state):
            raise InvalidTransition(old_state, target_state)

        # Check for backwards transition (unless it's a reconciliation or recovery)
        if triggered_by not in [
            "reconciliation",
            "recovery",
        ] and self.is_backwards_transition(old_state, target_state):
            # Log the blocked transition
            SessionActivity.objects.create(
                session=session,
                activity_type="backwards_transition_blocked",
                description=f"Blocked backwards transition from {old_state} to {target_state}",
                metadata={
                    "from_state": old_state,
                    "to_state": target_state,
                    "triggered_by": triggered_by,
                    "reason": "backwards_transition_prevention",
                },
            )

            error_msg = (
                f"Backwards transition from '{old_state}' to '{target_state}' is not allowed. "
                f"This typically indicates a state synchronization issue. "
                f"Use reconciliation or recovery mode if this transition is necessary."
            )
            logger.error(error_msg)
            raise InvalidTransition(old_state, target_state, error_msg)

        # Execute pre-transition hooks
        self._execute_pre_transition_hooks(session, old_state, target_state)

        # Perform the transition
        session.status = target_state
        self._update_timestamps(session, target_state)

        # Determine which fields need to be saved
        update_fields = ["status", "updated_at"]
        if target_state == "executing":
            update_fields.append("started_at")
        elif target_state == "completed":
            update_fields.append("completed_at")
        elif target_state == "draft":
            # When going back to draft, we clear timestamps
            update_fields.extend(["started_at", "completed_at"])
        elif target_state == "ready_to_execute":
            # When going back to ready_to_execute, we clear started_at
            update_fields.append("started_at")

        session.save(update_fields=update_fields)

        # Create transition event
        event = StateTransitionEvent(
            session_id=str(session_id),
            old_state=old_state,
            new_state=target_state,
            metadata=metadata or {},
            triggered_by=triggered_by,
            user_id=user_id,
        )

        # Execute post-transition hooks
        self._execute_post_transition_hooks(session, event)

        # Emit event to all listeners
        self.event_bus.emit(event)

        # Log the activity
        self._log_session_activity(session, event)

        logger.info(
            f"Transition completed: {old_state} -> {target_state} "
            f"for session {session_id}"
        )

        return event

    def _update_timestamps(self, session, new_state: str):
        """Update session timestamps based on state change."""
        if new_state == "executing" and not session.started_at:
            session.started_at = timezone.now()
        elif new_state == "completed" and not session.completed_at:
            session.completed_at = timezone.now()
        elif new_state == "ready_to_execute":
            # Clear started_at if reverting to ready_to_execute
            session.started_at = None
        elif new_state == "draft":
            # Clear all execution timestamps if reverting to draft
            session.started_at = None
            session.completed_at = None

    def _execute_pre_transition_hooks(self, session, old_state: str, new_state: str):
        """Execute hooks before transition."""
        # Validate session has required data for certain transitions
        if old_state == "defining_search" and new_state == "ready_to_execute":
            from apps.search_strategy.models import SearchQuery

            if not SearchQuery.objects.filter(
                strategy__session=session, is_active=True
            ).exists():
                raise InvalidTransition(
                    old_state, new_state, "Cannot execute without search queries"
                )

        logger.debug(f"Pre-transition hooks executed for {old_state} -> {new_state}")

    def _execute_post_transition_hooks(self, session, event: StateTransitionEvent):
        """Execute hooks after transition."""
        # Automated states trigger background tasks
        if self.is_automated_state(event.new_state):
            logger.info(
                f"State {event.new_state} is automated, tasks will be triggered"
            )

        logger.debug(f"Post-transition hooks executed for {event.new_state}")

    def _trigger_automated_tasks(self, event: StateTransitionEvent):
        """Trigger background tasks for automated states."""
        if event.session_id is None:
            return
        if event.new_state == "executing":
            self._trigger_execution_task(event.session_id)
        elif event.new_state == "processing_results":
            self._trigger_processing_task(event.session_id)
        elif event.new_state == "ready_for_review":
            self._trigger_review_preparation(event.session_id)

    def _trigger_execution_task(self, session_id: str):
        """Trigger search execution task."""
        try:
            from apps.serp_execution.tasks import initiate_search_session_execution_task

            initiate_search_session_execution_task.delay(session_id)
            logger.info(f"Triggered execution task for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to trigger execution task: {e}")
            self._emit_error(session_id, e, "Failed to trigger execution")

    def _trigger_processing_task(self, session_id: str):
        """Trigger results processing task."""
        try:
            from apps.results_manager.tasks.orchestration import (
                process_session_results_task,
            )

            process_session_results_task.delay(session_id)
            logger.info(f"Triggered processing task for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to trigger processing task: {e}")
            self._emit_error(session_id, e, "Failed to trigger processing")

    def _trigger_review_preparation(self, session_id: str):
        """Prepare session for review."""
        from apps.review_manager.models import SearchSession

        try:
            SearchSession.objects.get(id=session_id)
            # Note: SearchSession doesn't have review_started_at field
            # The under_review status transition itself marks when review starts
            logger.info(f"Prepared session {session_id} for review at {timezone.now()}")
        except Exception as e:
            logger.error(f"Failed to prepare review: {e}")

    def _log_session_activity(self, session, event: StateTransitionEvent):
        """Log the transition as a session activity."""
        from apps.review_manager.models import SessionActivity

        SessionActivity.objects.create(
            session=session,
            activity_type="state_transition",
            description=f"State changed from {event.old_state} to {event.new_state}",
            metadata={
                "old_state": event.old_state,
                "new_state": event.new_state,
                "triggered_by": event.triggered_by,
                "event_id": event.event_id,
            },
        )

    def _emit_error(self, session_id: str, exception: Exception, context: str):
        """Emit an error event."""
        error_event = ErrorEvent(
            session_id=session_id,
            error_type=type(exception).__name__,
            error_message=str(exception),
            metadata={"context": context},
        )
        self.event_bus.emit(error_event)

    def emit_progress(
        self, session_id: str, component: str, progress: int = 0, **kwargs
    ):
        """Emit a progress update event."""
        progress_event = ProgressEvent(
            session_id=session_id,
            component=component,
            processed_count=kwargs.get("processed_count", progress),
            total_count=kwargs.get("total_count", 0),
            current_step=kwargs.get("current_step", ""),
        )
        self.event_bus.emit(progress_event)

    def force_transition(
        self, session_id: str, target_state: str, reason: str
    ) -> StateTransitionEvent:
        """
        Force a state transition for recovery purposes.
        Bypasses normal validation rules.
        """
        from apps.review_manager.models import SearchSession

        try:
            with transaction.atomic():
                session = SearchSession.objects.select_for_update().get(id=session_id)
                old_state = session.status

                # Force the transition
                session.status = target_state
                self._update_timestamps(session, target_state)
                session.save()

                # Create recovery event
                recovery_event = RecoveryEvent(
                    session_id=str(session_id),
                    recovery_action="force_transition",
                    original_state=old_state,
                    recovered_state=target_state,
                    reason=reason,
                )
                self.event_bus.emit(recovery_event)

                # Create transition event
                event = StateTransitionEvent(
                    session_id=str(session_id),
                    old_state=old_state,
                    new_state=target_state,
                    metadata={"forced": True, "reason": reason},
                    triggered_by="recovery",
                )
                self.event_bus.emit(event)

                logger.warning(
                    f"Forced transition for session {session_id}: "
                    f"{old_state} -> {target_state}. Reason: {reason}"
                )

                return event

        except Exception as e:
            logger.error(f"Force transition failed: {e}")
            raise

    def get_session_history(self, session_id: str) -> List[Dict]:
        """Get the state transition history for a session."""
        return self.event_store.get_session_events(
            session_id, event_type="state_transition"
        )


# Create global singleton instance
state_machine = SessionStateMachine()
