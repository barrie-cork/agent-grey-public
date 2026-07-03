"""
State management service for SearchSession workflow.

This service provides atomic state transitions with automatic rollback
on failure, comprehensive validation, and audit logging.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.core.utils.distributed_lock import (
    DistributedLock,
    LockAcquisitionError,
    LockConfig,
)
from apps.review_manager.models import SearchSession, SessionActivity
from apps.serp_execution.constants import ExecutionStatusMessages

logger = logging.getLogger(__name__)


# State transition validation matrix
# Defines which transitions are allowed from each state
VALID_TRANSITIONS = {
    "draft": ["defining_search", "archived"],
    "defining_search": ["ready_to_execute", "draft", "archived"],
    "ready_to_execute": ["executing", "defining_search", "archived"],
    "executing": [
        "processing_results",
        "ready_to_execute",
        "defining_search",
        "archived",
    ],
    "processing_results": [
        "ready_for_review",
        "executing",
        "defining_search",
        "completed",
        "archived",
    ],
    "ready_for_review": [
        "under_review",
        "processing_results",
        "defining_search",
        "archived",
    ],
    "under_review": ["completed", "ready_for_review", "defining_search", "archived"],
    "completed": ["archived", "under_review"],
    "archived": ["draft"],  # Can only unarchive to draft
}

# Automated transitions that happen without user interaction
AUTOMATED_TRANSITIONS = [
    ("ready_to_execute", "executing"),
    ("executing", "processing_results"),
    ("processing_results", "ready_for_review"),
    ("ready_for_review", "under_review"),  # Auto-redirect
]


class StateTransitionError(Exception):
    """Raised when state transition fails."""

    pass


class SessionStateManager:
    """
    Manages atomic state transitions for SearchSession.

    This class ensures that all state transitions are atomic,
    validated, and properly logged. It provides automatic rollback
    on any failure during the transition process.
    """

    def __init__(self, session: SearchSession):
        """
        Initialize state manager for a session.

        Args:
            session: The SearchSession instance to manage
        """
        self.session = session
        self.original_status = session.status
        self._use_new_system = self._check_feature_flag()

    def _check_feature_flag(self):
        """Check if new state machine should be used."""
        from apps.core.models import Configuration

        # Use JSON-based configuration approach
        return Configuration.get_config("use_event_driven_state_machine", False)

    def validate_transition_matrix(self, from_state: str, to_state: str) -> bool:
        """
        Validate transition against the allowed transition matrix.

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            True if transition is allowed

        Raises:
            StateTransitionError: If transition is not allowed
        """
        valid_targets = VALID_TRANSITIONS.get(from_state, [])

        if to_state not in valid_targets:
            error_msg = (
                f"Transition from '{from_state}' to '{to_state}' is not allowed. "
                f"Valid transitions from '{from_state}': {', '.join(valid_targets)}"
            )
            logger.error(error_msg)
            raise StateTransitionError(error_msg)

        return True

    def is_automated_transition(self, from_state: str, to_state: str) -> bool:
        """
        Check if a transition is automated (happens without user interaction).

        Args:
            from_state: Current state
            to_state: Target state

        Returns:
            True if this is an automated transition
        """
        return (from_state, to_state) in AUTOMATED_TRANSITIONS

    def get_matrix_allowed_transitions(self, current_state: str) -> list:
        """
        Get list of allowed transitions from current state based on matrix.

        Args:
            current_state: The current state

        Returns:
            List of states that can be transitioned to
        """
        return VALID_TRANSITIONS.get(current_state, [])

    def validate_transition_prerequisites(
        self, session: SearchSession, to_state: str
    ) -> Tuple[bool, str]:
        """
        Validate business rule prerequisites for transition.

        Args:
            session: The SearchSession instance
            to_state: Target state

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Add specific validation for each transition type
        current_state = session.status

        # Validate using the matrix first
        try:
            self.validate_transition_matrix(current_state, to_state)
        except StateTransitionError as e:
            return False, str(e)

        # Additional business rule validations
        if to_state == "executing" and current_state == "ready_to_execute":
            # Check if there are queries to execute
            from apps.search_strategy.models import SearchQuery

            active_queries = SearchQuery.objects.filter(
                strategy__session=session, is_active=True
            ).count()

            if active_queries == 0:
                return False, "Cannot execute: No active queries defined"

        elif to_state == "completed" and current_state == "under_review":
            # Check if review is actually complete
            from apps.results_manager.models import ProcessedResult

            unreviewed = ProcessedResult.objects.filter(
                session=session, simplereviewdecision__isnull=True
            ).count()

            if unreviewed > 0:
                logger.warning(
                    f"Completing session with {unreviewed} unreviewed results"
                )

        return True, ""

    def _validate_transition_request(self, new_status: str) -> None:
        """Validate the transition request."""
        if not new_status:
            raise StateTransitionError("New status cannot be empty")

        valid_statuses = [status[0] for status in SearchSession.STATUS_CHOICES]
        if new_status not in valid_statuses:
            raise StateTransitionError(f"Invalid status: {new_status}")

    def _update_timestamps(self, session: SearchSession, new_status: str) -> None:
        """Update session timestamps based on status change."""
        if new_status == "executing" and not session.started_at:
            session.started_at = timezone.now()
        elif new_status == "completed" and not session.completed_at:
            session.completed_at = timezone.now()
        elif new_status == "ready_to_execute":
            # Clear started_at if reverting to ready_to_execute
            session.started_at = None
        elif new_status == "draft":
            # Clear all execution timestamps if reverting to draft
            session.started_at = None
            session.completed_at = None

    def _log_status_change(
        self,
        session: SearchSession,
        old_status: str,
        new_status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log status change activity."""
        activity_metadata = {
            "old_status": old_status,
            "new_status": new_status,
            "transition_timestamp": timezone.now().isoformat(),
        }

        # Add any additional metadata provided
        if metadata:
            activity_metadata["transition_metadata"] = metadata

        SessionActivity.log_activity(
            session=session,
            activity_type="status_changed",
            description=f"Status changed from '{old_status}' to '{new_status}'",
            user=session.owner,
            metadata=activity_metadata,
        )

    def _legacy_transition_to(
        self, new_status: str, metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Legacy transition implementation."""
        return self._perform_transition(new_status, metadata)

    @transaction.atomic
    def transition_to(
        self, new_status: str, metadata: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Tuple[bool, Optional[str]]:
        """
        Transition to a new state.
        Routes to appropriate system based on feature flag.

        Args:
            new_status: Target status to transition to
            metadata: Additional transition metadata for logging
            **kwargs: Additional parameters including 'user' for the user initiating the transition

        Returns:
            Tuple of (success, error_message) where error_message is None on success
        """
        try:
            if self._use_new_system:
                # Use new state machine
                from apps.core.state_machine import state_machine

                result = state_machine.transition(
                    session_id=self.session.id,
                    target_state=new_status,
                    metadata=metadata or kwargs,
                    user_id=str(self.session.owner.id) if self.session.owner else None,
                    triggered_by=kwargs.get("triggered_by", "system"),
                )
                return (
                    (True, None)
                    if result
                    else (False, "State machine transition failed")
                )
            else:
                # Use existing implementation
                result = self._legacy_transition_to(new_status, metadata)
                return (result, None) if result else (False, "Legacy transition failed")
        except StateTransitionError as e:
            return (False, str(e))
        except (DatabaseError, ImportError, AttributeError) as e:
            logger.error(f"Unexpected error in transition_to: {e}", exc_info=True)
            return (False, f"Unexpected error: {str(e)}")

    @transaction.atomic
    def _perform_transition(  # noqa: C901 - Complex state transition with validation and rollback
        self, new_status: str, metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Atomic state transition with matrix validation and rollback on failure.

        This method ensures that state transitions follow the defined matrix,
        validates business rules, and maintains atomicity.

        Args:
            new_status: Target status to transition to
            metadata: Additional transition metadata for logging

        Returns:
            True if transition was successful

        Raises:
            StateTransitionError: If transition fails or is invalid
        """
        try:
            # Validate request
            self._validate_transition_request(new_status)

            # Refresh from DB with lock to prevent concurrent modifications
            session = SearchSession.objects.select_for_update().get(pk=self.session.pk)
            old_status = session.status

            # NEW: Validate against transition matrix
            self.validate_transition_matrix(old_status, new_status)

            # NEW: Check if this is an automated transition
            if self.is_automated_transition(old_status, new_status):
                logger.info(
                    f"Processing automated transition: {old_status} -> {new_status}"
                )
                if metadata is None:
                    metadata = {}
                metadata["automated"] = True

            # NEW: Validate prerequisites
            is_valid, validation_error = self.validate_transition_prerequisites(
                session, new_status
            )
            if not is_valid:
                raise StateTransitionError(
                    f"Prerequisite validation failed: {validation_error}"
                )

            # Use existing model validation as additional check
            if not session.can_transition_to(new_status):
                # This shouldn't happen if our matrix is correct, but keep as safety net
                logger.warning(
                    f"Model validation rejected transition {old_status} -> {new_status} "
                    f"even though matrix allowed it"
                )
                raise StateTransitionError(
                    f"Model validation failed for transition from '{old_status}' to '{new_status}'"
                )

            # Perform business rule validation (existing)
            is_valid, validation_error = self.validate_transition(session, new_status)
            if not is_valid:
                raise StateTransitionError(
                    f"Business rule validation failed: {validation_error}"
                )

            # Update status and timestamps
            session.status = new_status
            self._update_timestamps(session, new_status)
            session.save()

            # Log the change
            self._log_status_change(session, old_status, new_status, metadata)

            # State changes are now automatically broadcast via event_bus
            # No explicit broadcast needed - handled by SessionStateManager
            try:
                # Log state change for debugging
                logger.info(
                    f"State transition for session {session.id}: "
                    f"{old_status} -> {new_status}"
                )

            except (DatabaseError, OSError) as e:
                # Don't fail the state transition if logging fails
                logger.warning(
                    f"Failed to log state change for session {session.id}: {e}"
                )

            # Update cached instance
            self.session = session

            logger.info(
                f"Session {session.id} successfully transitioned from "
                f"'{old_status}' to '{new_status}'"
            )

            # NEW: Trigger automatic execution when reaching ready_to_execute
            if new_status == "ready_to_execute":
                self._trigger_automatic_execution(session)

            return True

        except SearchSession.DoesNotExist:
            raise StateTransitionError(f"Session {self.session.pk} no longer exists")
        except StateTransitionError:
            raise
        except (
            Exception
        ) as e:  # Intentional broad catch: re-wraps as StateTransitionError
            logger.error(
                f"Unexpected error during transition: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            raise StateTransitionError(f"Transition failed: {str(e)}")

    def _trigger_automatic_execution(  # noqa: C901 - Auto execution logic
        self, session: SearchSession
    ) -> None:
        """
        Automatically trigger search execution when reaching ready_to_execute state.

        This method emits progress events and starts the execution task,
        eliminating the need for user interaction at the ready_to_execute state.
        """
        try:
            from apps.core.progress.tracker import ProgressTracker
            from apps.serp_execution.tasks import initiate_search_session_execution_task

            session_id_str = str(session.id)

            def trigger_execution_after_commit() -> None:
                """Launch execution once the ready_to_execute transition is committed."""
                try:
                    tracker = ProgressTracker()

                    # Emit progress events showing preparation (5-10% range)
                    owner_info = f"(owner: {session.owner.username if session.owner else 'anonymous'})"
                    logger.info(
                        f"Starting automatic execution trigger for session {session_id_str} {owner_info}"
                    )

                    # First progress: Validation complete
                    tracker.update_progress(
                        session_id=session_id_str,
                        component="ready_to_execute",
                        processed_count=1,
                        total_count=4,
                        current_step=ExecutionStatusMessages.VALIDATION_COMPLETE,
                        metadata={"automatic": True, "trigger": "state_transition"},
                    )

                    # Removed time.sleep(0.3) for faster execution

                    tracker.update_progress(
                        session_id=session_id_str,
                        component="ready_to_execute",
                        processed_count=2,
                        total_count=4,
                        current_step=ExecutionStatusMessages.PREPARING_ENVIRONMENT,
                        metadata={"automatic": True, "trigger": "state_transition"},
                    )

                    # Removed time.sleep(0.3) for faster execution

                    tracker.update_progress(
                        session_id=session_id_str,
                        component="ready_to_execute",
                        processed_count=3,
                        total_count=4,
                        current_step=ExecutionStatusMessages.INITIALIZING_QUERIES,
                        metadata={"automatic": True, "trigger": "state_transition"},
                    )

                    # Removed time.sleep(0.3) for faster execution

                    tracker.update_progress(
                        session_id=session_id_str,
                        component="ready_to_execute",
                        processed_count=4,
                        total_count=4,
                        current_step=ExecutionStatusMessages.STARTING_EXECUTION,
                        metadata={"automatic": True, "trigger": "state_transition"},
                    )

                    task = initiate_search_session_execution_task.delay(session_id_str)

                    logger.info(
                        f"Automatic execution triggered for session {session_id_str} {owner_info}. "
                        f"Task ID: {task.id if hasattr(task, 'id') else 'unknown'}"
                    )

                    SessionActivity.log_activity(
                        session=session,
                        activity_type="auto_execution",
                        description="Search execution automatically triggered after validation",
                        user=session.owner,
                        metadata={
                            "task_id": task.id if hasattr(task, "id") else None,
                            "automatic": True,
                            "triggered_from": "ready_to_execute_transition",
                        },
                    )
                except Exception as exc:  # Intentional broad catch: a failed
                    # fire-and-forget execution trigger must never break the
                    # committed state transition (e.g. broker unavailable).
                    logger.error(
                        f"Failed to trigger automatic execution for session {session.id}: {exc}",
                        exc_info=True,
                    )

            # Defer execution until the surrounding transaction successfully commits
            transaction.on_commit(trigger_execution_after_commit)

        except (
            Exception
        ) as e:  # Intentional broad catch: don't fail the state transition
            # Log error but don't fail the transition
            logger.error(
                f"Failed to register automatic execution trigger for session {session.id}: {e}",
                exc_info=True,
            )
            # ENHANCED: Try fallback execution without progress tracking or distributed locking
            try:
                logger.warning(
                    f"Attempting fallback execution trigger for session {session.id}"
                )
                from apps.serp_execution.tasks import (
                    initiate_search_session_execution_task,
                )

                # Try direct task execution without progress tracking
                task = initiate_search_session_execution_task.delay(str(session.id))

                logger.info(
                    f"Fallback execution triggered for session {session.id}. "
                    f"Task ID: {task.id if hasattr(task, 'id') else 'unknown'}"
                )

                # Log fallback execution attempt
                try:
                    SessionActivity.log_activity(
                        session=session,
                        activity_type="fallback_execution",
                        description="Search execution triggered via fallback method after primary trigger failed",
                        user=session.owner,
                        metadata={
                            "task_id": task.id if hasattr(task, "id") else None,
                            "fallback_reason": str(e)[:200],  # Truncate error message
                            "automatic": True,
                            "triggered_from": "fallback_ready_to_execute_transition",
                        },
                    )
                except (DatabaseError, OSError) as activity_error:
                    # Don't fail execution trigger due to activity logging error
                    logger.warning(
                        f"Failed to log fallback activity for session {session.id}: {activity_error}"
                    )

            except (
                Exception
            ) as fallback_error:  # Intentional broad catch: last-resort fallback
                logger.error(
                    f"Fallback execution trigger also failed for session {session.id}: {fallback_error}",
                    exc_info=True,
                )
                # CRITICAL: If automatic trigger AND fallback fail, the session stays in ready_to_execute
                # The session will need manual recovery or the next automatic retry
                # Mark this session for recovery attention
                try:
                    SessionActivity.log_activity(
                        session=session,
                        activity_type="execution_failure",
                        description=(
                            "Both automatic and fallback execution triggers failed - "
                            "session needs manual recovery"
                        ),
                        user=session.owner,
                        metadata={
                            "primary_error": str(e)[:200],
                            "fallback_error": str(fallback_error)[:200],
                            "needs_recovery": True,
                            "automatic": True,
                        },
                    )
                except Exception:  # Intentional: activity logging must not mask primary state transition error
                    # If even logging fails, log to system logger
                    logger.critical(
                        f"Session {session.id} execution trigger failed and activity logging also failed"
                    )

    def validate_transition(
        self, session: SearchSession, new_status: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate business rules for state transitions.

        This method checks business-specific rules beyond the basic
        state machine transitions defined in the model.

        Args:
            session: The session to validate
            new_status: The target status

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Import here to avoid circular imports
        from apps.review_manager.validators import WorkflowValidator

        validator = WorkflowValidator()

        # Validate based on target status
        if new_status == "executing":
            return validator.can_execute(session)
        elif new_status == "processing_results":
            return validator.can_process_results(session)
        elif new_status == "completed":
            return validator.can_complete(session)
        elif new_status == "ready_for_review":
            return validator.can_review(session)

        # No special validation for other transitions
        return True, None

    def get_allowed_transitions(self) -> list:
        """
        Get list of allowed transitions from current state.

        Returns:
            List of allowed target status values
        """
        return self.session.get_allowed_transitions()

    def can_transition_to(self, new_status: str) -> bool:
        """
        Check if transition to new status is allowed.

        Args:
            new_status: Target status to check

        Returns:
            True if transition is allowed
        """
        return self.session.can_transition_to(new_status)

    @transaction.atomic
    def force_transition(self, new_status: str, reason: str) -> bool:
        """
        Force a state transition for recovery purposes.

        This method bypasses normal transition rules and should only
        be used by the recovery system or administrators.

        Args:
            new_status: Target status
            reason: Reason for forcing the transition

        Returns:
            True if successful
        """
        try:
            # Refresh with lock
            session = SearchSession.objects.select_for_update().get(pk=self.session.pk)
            original_status = session.status

            # Force the status change
            session.status = new_status

            # Handle timestamps
            if new_status == "executing" and not session.started_at:
                session.started_at = timezone.now()
            elif new_status == "completed" and not session.completed_at:
                session.completed_at = timezone.now()
            elif new_status in ["ready_to_execute", "draft"]:
                session.started_at = None
                if new_status == "draft":
                    session.completed_at = None

            session.save()

            # Log the forced transition
            SessionActivity.log_activity(
                session=session,
                activity_type="status_changed",
                description=f"Status force-changed from '{original_status}' to '{new_status}'",
                user=session.owner,
                metadata={
                    "old_status": original_status,
                    "new_status": new_status,
                    "forced": True,
                    "reason": reason,
                    "timestamp": timezone.now().isoformat(),
                },
            )

            logger.warning(
                f"Forced transition for session {session.id} from "
                f"'{original_status}' to '{new_status}'. Reason: {reason}"
            )

            self.session = session
            return True

        except (DatabaseError, SearchSession.DoesNotExist) as e:
            logger.error(
                f"Force transition failed for session {self.session.pk}: {str(e)}",
                exc_info=True,
            )
            return False

    def get_current_status(self) -> str:
        """
        Get the current status of the session.

        Returns:
            Current status value
        """
        # Refresh from database to get latest status
        self.session.refresh_from_db()
        return self.session.status

    def log_transition_attempt(
        self, target_status: str, success: bool, error: Optional[str] = None
    ) -> None:
        """
        Log a transition attempt for debugging purposes.

        Args:
            target_status: The status that was attempted
            success: Whether the transition succeeded
            error: Error message if failed
        """
        log_data = {
            "session_id": str(self.session.pk),
            "current_status": self.session.status,
            "target_status": target_status,
            "success": success,
            "timestamp": timezone.now().isoformat(),
        }

        if error:
            log_data["error"] = error

        if success:
            logger.info(f"Transition attempt succeeded: {log_data}")
        else:
            logger.warning(f"Transition attempt failed: {log_data}")

    def _get_session_lock_key(self, session_id: str | None = None) -> str:
        """
        Generate a unique lock key for this session's transitions.

        Args:
            session_id: Optional session ID, uses self.session.pk if not provided

        Returns:
            String key for the distributed lock
        """
        sid = session_id or str(self.session.pk)
        return f"session_transition_{sid}"

    def _create_lock_config(self, timeout: int = 30) -> LockConfig:
        """
        Create configuration for distributed lock.

        Args:
            timeout: Maximum time to hold the lock in seconds

        Returns:
            LockConfig instance with appropriate settings
        """
        return LockConfig(
            timeout=timeout,
            retry_count=5,  # Try 5 times
            retry_delay=0.5,  # Wait 0.5 seconds between retries
            use_exponential_backoff=True,  # Increase wait time on each retry
            timeout_buffer=2,  # Release lock 2 seconds before timeout
        )

    def transition_with_lock(
        self,
        new_status: str,
        metadata: Optional[Dict[str, Any]] = None,
        lock_timeout: int = 30,
    ) -> bool:
        """
        Perform state transition with distributed locking.

        This method ensures that only one process can transition a session
        at a time by using Redis-based distributed locking.

        Args:
            new_status: Target status to transition to
            metadata: Additional transition metadata for logging
            lock_timeout: Maximum time to hold the lock

        Returns:
            True if transition was successful

        Raises:
            StateTransitionError: If transition fails or lock cannot be acquired
        """
        lock_key = self._get_session_lock_key()
        lock_config = self._create_lock_config(lock_timeout)

        logger.info(
            f"Attempting to acquire transition lock for session {self.session.pk}"
        )

        try:
            # Create distributed lock instance
            lock = DistributedLock(config=lock_config)

            # Acquire lock and perform transition
            with lock.acquire(lock_key, timeout=lock_timeout):
                logger.info(f"Acquired lock for session {self.session.pk}")

                # Reload session within lock to get latest state
                # This is critical - we must check the current state after acquiring lock
                self.session.refresh_from_db()

                # Log if state changed while waiting for lock
                if self.session.status != self.original_status:
                    logger.warning(
                        f"Session {self.session.pk} state changed while waiting for lock: "
                        f"{self.original_status} -> {self.session.status}"
                    )
                    # Update our original status tracker
                    self.original_status = self.session.status

                # Perform the transition with the lock held
                success, _error = self.transition_to(new_status, metadata)

                logger.info(f"Released lock for session {self.session.pk}")
                return success

        except LockAcquisitionError as e:
            error_msg = (
                f"Could not acquire lock for session {self.session.pk}: {str(e)}"
            )
            logger.error(error_msg)
            raise StateTransitionError(error_msg)

        except (
            Exception
        ) as e:  # Intentional broad catch: re-wraps as StateTransitionError
            error_msg = f"Unexpected error during locked transition: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise StateTransitionError(error_msg)

    def safely_complete_review(self, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Safely transition from under_review to completed with locking.

        Args:
            metadata: Additional metadata for the transition

        Returns:
            True if successful
        """
        if self.session.status != "under_review":
            raise StateTransitionError(
                f"Cannot complete review from state '{self.session.status}'"
            )

        return self.transition_with_lock("completed", metadata)

    def safely_start_review(self, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Safely transition from ready_for_review to under_review with locking.

        Args:
            metadata: Additional metadata for the transition

        Returns:
            True if successful
        """
        if self.session.status != "ready_for_review":
            raise StateTransitionError(
                f"Cannot start review from state '{self.session.status}'"
            )

        return self.transition_with_lock("under_review", metadata)

    def safely_execute_search(self, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Safely transition from ready_to_execute to executing with locking.

        Args:
            metadata: Additional metadata for the transition

        Returns:
            True if successful
        """
        if self.session.status != "ready_to_execute":
            raise StateTransitionError(
                f"Cannot execute search from state '{self.session.status}'"
            )

        # Add default metadata for execution
        if metadata is None:
            metadata = {}
        metadata["trigger"] = "user_initiated"
        metadata["timestamp"] = timezone.now().isoformat()

        return self.transition_with_lock("executing", metadata)
