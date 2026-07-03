"""
Execution orchestration service for serp_execution.
Coordinates the execution of search sessions by delegating to specialized services.
"""

import logging
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from celery import group
from django.db import transaction

from apps.core.services.simple_services import DatabaseStateManager

if TYPE_CHECKING:
    from apps.review_manager.models import SearchSession
from apps.serp_execution.api_types import (
    SessionExecutionResult,
    SessionValidationResult,
)
from apps.serp_execution.services.query_manager import QueryManager
from apps.serp_execution.services.session_validator import SessionValidator

logger = logging.getLogger(__name__)


class ExecutionOrchestrator:
    """
    Orchestrates the execution of search sessions.

    This class coordinates between different services to execute
    a search session, maintaining separation of concerns and
    single responsibility principle.
    """

    def __init__(self, celery_task_id: Optional[str] = None):
        """
        Initialize the execution orchestrator.

        Args:
            celery_task_id: Optional Celery task ID for tracking
        """
        self.validator = SessionValidator()
        self.query_manager = QueryManager()
        self.celery_task_id = celery_task_id
        self.logger = logger.getChild(self.__class__.__name__)

    def execute_session(self, session_id: UUID) -> SessionExecutionResult:
        """
        Execute a search session with all its queries.

        This is the main entry point that coordinates the entire
        execution process.

        Args:
            session_id: The UUID of the session to execute

        Returns:
            SessionExecutionResult with execution details
        """
        self.logger.info(f"Starting execution for session {session_id}")

        # Step 1: Validate session
        validation = self._validate_session(session_id)
        if not validation["can_execute"]:
            return self._create_validation_failure_result(validation)

        # Step 2: Get session and queries
        session = self._get_session(session_id)
        if not session:
            return SessionExecutionResult(
                success=False,
                session_id=str(session_id),
                error="Failed to retrieve session after validation",
            )

        queries = self.query_manager.get_active_queries(session)
        if not queries:
            return self._handle_no_queries(session)

        # Step 3: Transition to executing state
        transition_result = self._transition_to_executing(session, len(queries))
        if not transition_result:
            return SessionExecutionResult(
                success=False,
                session_id=str(session_id),
                error="Failed to transition session to executing state",
            )

        # Step 4: Create execution records and tasks
        try:
            result = self._create_and_launch_executions(session, queries)

            # Step 5: Log successful start
            self._log_execution_start(session, len(queries))

            return result

        except Exception as e:
            self.logger.error(
                f"Execution failed for session {session_id}: {str(e)}", exc_info=True
            )

            # Rollback session state
            self._rollback_session_state(session, str(e))

            return SessionExecutionResult(
                success=False,
                session_id=str(session_id),
                error=str(e),
                error_type=type(e).__name__,
            )

    def _validate_session(self, session_id: UUID) -> SessionValidationResult:
        """Validate the session for execution."""
        return self.validator.validate_session(session_id)

    def _get_session(self, session_id: UUID) -> Optional["SearchSession"]:
        """Get the session object."""
        # Lazy import to avoid Django initialization timing issues in Celery
        from apps.review_manager.models import SearchSession

        try:
            return SearchSession.objects.select_related("owner", "search_strategy").get(
                id=session_id
            )
        except SearchSession.DoesNotExist:
            self.logger.error(f"Session {session_id} not found")
            return None

    def _create_validation_failure_result(
        self, validation: SessionValidationResult
    ) -> SessionExecutionResult:
        """Create a result for validation failure."""
        self.logger.warning(
            f"Session {validation['session_id']} validation failed: "
            f"{validation['error_message']}"
        )

        return SessionExecutionResult(
            success=False,
            session_id=validation["session_id"],
            error=validation["error_message"] or "Validation failed",
            status=validation["current_status"],
            queries_count=0,
        )

    def _handle_no_queries(self, session: "SearchSession") -> SessionExecutionResult:
        """Handle case when no queries are found."""
        from apps.review_manager.models import SessionActivity

        self.logger.error(f"No active queries for session {session.id}")

        # Log as activity
        SessionActivity.log_activity(
            session=session,
            activity_type="execution_failed",
            description="Search execution failed - no active queries found",
            user=session.owner,
            metadata={"reason": "no_active_queries", "task_id": self.celery_task_id},
        )

        return SessionExecutionResult(
            success=False,
            session_id=str(session.id),
            error="No active queries found",
            queries_count=0,
            status=session.status,
        )

    def _transition_to_executing(
        self, session: "SearchSession", query_count: int
    ) -> bool:
        """
        Transition session to executing state.

        Returns:
            True if transition successful, False otherwise
        """
        try:
            success = DatabaseStateManager().set_session_status(
                session,
                "executing",
                detail=f"Starting execution of {query_count} queries",
            )

            if success:
                self.logger.info(
                    f"Transitioned session {session.id} to executing state"
                )
            else:
                self.logger.error(f"State transition failed for session {session.id}")

            return success

        except Exception as e:
            self.logger.error(
                f"State transition failed for session {session.id}: {str(e)}"
            )
            return False

    @transaction.atomic
    def _create_and_launch_executions(
        self, session: "SearchSession", queries: list
    ) -> SessionExecutionResult:
        """
        Create execution records and launch Celery tasks.

        Args:
            session: The SearchSession object
            queries: List of SearchQuery objects

        Returns:
            SessionExecutionResult with execution details
        """
        from apps.serp_execution.providers import (
            get_default_provider,
            get_provider_display_name,
        )
        from apps.serp_execution.tasks import monitor_session_completion_task

        # Resolve the SERP provider for this execution
        provider = get_default_provider()
        provider_key = provider.provider_key
        provider_display = get_provider_display_name(provider_key)

        # Create execution records
        execution_records = self.query_manager.create_execution_records(
            queries=queries,
            initiated_by=session.owner,
            celery_task_id=self.celery_task_id,
            provider_key=provider_key,
            provider_display=provider_display,
        )

        # Prepare Celery tasks
        celery_tasks = self.query_manager.prepare_celery_tasks(execution_records)

        # Create task group with completion monitor
        job = group(celery_tasks) | monitor_session_completion_task.si(str(session.id))

        # Launch async execution after transaction commits
        # This ensures SearchExecution records are visible to Celery workers
        transaction.on_commit(lambda: job.apply_async())

        self.logger.info(
            f"Scheduled {len(celery_tasks)} tasks for session {session.id} (will launch after commit)"
        )

        return SessionExecutionResult(
            success=True,
            session_id=str(session.id),
            queries_count=len(celery_tasks),
            status="executing",
            execution_ids=[str(e.id) for e in execution_records],
            task_id=self.celery_task_id,
        )

    def _log_execution_start(self, session: "SearchSession", query_count: int) -> None:
        """Log the successful start of execution."""
        from apps.review_manager.models import SessionActivity

        SessionActivity.objects.create(
            session=session,
            user=session.owner,
            activity_type="execution_started",
            description=f"Search execution started with {query_count} queries",
            metadata={"query_count": query_count, "task_id": self.celery_task_id},
        )

        self.logger.info(f"Logged execution start for session {session.id}")

    def _rollback_session_state(self, session: "SearchSession", error: str) -> None:
        """
        Rollback session state after failure.

        Args:
            session: The SearchSession object
            error: Error message for logging
        """
        if session.status != "executing":
            return

        try:
            success = DatabaseStateManager().set_session_status(
                session, "ready_to_execute", detail=f"Execution failed: {error}"
            )

            if success:
                self.logger.info(
                    f"Rolled back session {session.id} to ready_to_execute"
                )
            else:
                self.logger.error(f"Failed to rollback session {session.id}")

        except Exception as e:
            self.logger.error(f"Failed to rollback session state: {str(e)}")
