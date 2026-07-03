"""Service layer for search strategy operations.

This service handles the business logic for search strategy management,
including validation, query generation, and status transitions.
"""

import logging
import time
from typing import Any, Dict, Optional, Tuple

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpRequest

from apps.review_manager.models import SearchSession, SessionActivity

from ..forms import SearchStrategyForm
from ..models import SearchQuery, SearchStrategy

logger = logging.getLogger(__name__)
User = get_user_model()


class SearchStrategyService:
    """Service for managing search strategy operations."""

    def __init__(self):
        """Initialize the service."""
        self.logger = logger

    def get_or_create_strategy(
        self, session: SearchSession, user: User
    ) -> Tuple[SearchStrategy, bool]:
        """Get or create a search strategy for a session.

        Args:
            session: The search session.
            user: The user creating the strategy.

        Returns:
            Tuple of (strategy, created) where created is True if newly created.
        """
        return SearchStrategy.objects.get_or_create(
            session=session, defaults={"user": user}
        )

    def validate_and_save_strategy(
        self, form: SearchStrategyForm
    ) -> Tuple[SearchStrategy, bool]:
        """Validate and save a search strategy.

        Args:
            form: The validated form containing strategy data.

        Returns:
            Tuple of (strategy, is_complete) where is_complete indicates
            if the strategy passes all validation.
        """
        strategy = form.save()

        # Log saved strategy data
        self.logger.info(f"Saved strategy - Population: {strategy.population_terms}")
        self.logger.info(f"Saved strategy - Interest: {strategy.interest_terms}")
        self.logger.info(f"Saved strategy - Context: {strategy.context_terms}")
        self.logger.info(f"Saved strategy - Config: {strategy.search_config}")

        # Validate completeness
        is_complete = strategy.validate_completeness()
        strategy.save(update_fields=["is_complete", "validation_errors"])

        return strategy, is_complete

    def update_search_queries(self, strategy: SearchStrategy) -> int:
        """Update SearchQuery objects based on strategy.

        Regenerates all search queries based on the current strategy configuration.
        Deletes existing queries and creates new ones to ensure consistency.
        Handles query splitting if enabled in the configuration.

        Args:
            strategy: The search strategy to generate queries from.

        Returns:
            Number of queries created.
        """
        # If session already has processed results (re-execution), deactivate
        # old queries instead of deleting to preserve the audit trail
        from apps.results_manager.models import ProcessedResult

        existing_queries = SearchQuery.objects.filter(session=strategy.session)
        has_existing_results = ProcessedResult.objects.filter(
            session=strategy.session
        ).exists()

        if has_existing_results and existing_queries.exists():
            existing_queries.filter(is_active=True).update(is_active=False)
            logger.info(
                f"Deactivated existing queries for session {strategy.session.id} "
                f"(preserving for audit trail)"
            )
        else:
            existing_queries.delete()

        # Check if query splitting is enabled
        splitting_enabled = strategy.search_config.get("query_splitting", {}).get(
            "enabled", False
        )

        # Generate queries (with or without splitting)
        if splitting_enabled:
            logger.info(
                f"[Query Splitting] Generating split queries for session {strategy.session.id}"
            )
            queries = strategy.generate_split_queries()
        else:
            queries = strategy.generate_queries()

        # Create SearchQuery objects
        for idx, query_data in enumerate(queries):
            query_text = query_data["query"]

            # Log differently for split queries
            if "split_info" in query_data:
                split_info = query_data["split_info"]
                logger.info(
                    f"[Query Splitting] Creating split query #{idx} "
                    f"(original: {split_info.get('original_index')}, "
                    f"strategy: {split_info.get('split_strategy')}): {query_text[:100]}..."
                )
            # Standard query logging removed for performance

            SearchQuery.objects.create(
                strategy=strategy,
                session=strategy.session,
                query_text=query_text,
                query_type=query_data["type"],
                target_domain=query_data.get("domain"),
                execution_order=idx,
                is_active=True,
            )

        logger.info(f"Created {len(queries)} queries for session {strategy.session.id}")
        return len(queries)

    def log_strategy_update(
        self, session: SearchSession, user: User, is_complete: bool, query_count: int
    ) -> None:
        """Log strategy update activity.

        Args:
            session: The search session.
            user: The user performing the update.
            is_complete: Whether the strategy is complete.
            query_count: Number of queries generated.
        """
        strategy = session.search_strategy
        SessionActivity.log_activity(
            session=session,
            activity_type="search_defined",
            description="Search strategy updated",
            user=user,
            metadata={
                "is_complete": is_complete,
                "query_count": query_count,
                "stats": strategy.get_stats(),
            },
        )

    def handle_status_transition(
        self, session: SearchSession, user: User, request: Optional[HttpRequest]
    ) -> bool:
        """Handle session status transition when strategy is complete.

        Args:
            session: The search session.
            user: The user performing the action.
            request: The HTTP request for messages (optional, can be None).

        Returns:
            True if transition was successful, False otherwise.
        """
        if session.status in ["draft", "defining_search"]:
            if session.can_transition_to("ready_to_execute"):
                old_status = session.status
                session.status = "ready_to_execute"
                session.save(update_fields=["status"])

                SessionActivity.log_activity(
                    session=session,
                    activity_type="status_changed",
                    description="Session ready for execution",
                    user=user,
                    metadata={
                        "old_status": old_status,
                        "new_status": "ready_to_execute",
                    },
                )

                # Only add message if request is provided and valid
                if request and hasattr(request, "META"):
                    messages.success(
                        request,
                        "Search strategy completed! Session is now ready for execution.",
                    )
                    self.logger.debug(
                        f"Request provided for session {session.id} - success message added"
                    )
                else:
                    self.logger.warning(
                        f"No valid request provided for session {session.id} - messages skipped"
                    )
                return True
            else:
                # Session cannot transition (likely already in a later state)
                # Log at debug level instead of showing user-facing warning
                self.logger.debug(
                    f"Session {session.id} cannot transition to ready_to_execute from {session.status}. "
                    f"This is expected if session is already executing or beyond."
                )
                return False
        return True

    def prepare_for_execution(
        self, session: SearchSession, user: User, request: Optional[HttpRequest]
    ) -> Dict[str, Any]:
        """Prepare session for search execution.

        Handles the status transitions and validations needed before
        initiating search execution using the SessionStateManager.

        Args:
            session: The search session.
            user: The user initiating execution.
            request: The HTTP request for messages (optional, can be None).

        Returns:
            Dict with 'success' bool and optional 'error' message.
        """
        from apps.review_manager.services.state_manager import SessionStateManager

        state_manager = SessionStateManager(session)

        # Debug current status
        self.logger.debug(f"Current session status: {session.status}")
        self.logger.debug(
            f"Can transition to ready_to_execute: {session.can_transition_to('ready_to_execute')}"
        )
        self.logger.debug(f"Allowed transitions: {session.get_allowed_transitions()}")

        # Handle draft to defining_search transition
        if session.status == "draft":
            success, error = state_manager.transition_to("defining_search", user=user)
            if not success:
                self.logger.error(
                    f"Failed to transition from draft to defining_search: {error}"
                )
                return {"success": False, "error": error}

        # Ensure we have latest session state
        session.refresh_from_db()

        # Handle defining_search to ready_to_execute transition
        # This will automatically trigger the execution after 1-2 seconds
        if session.status == "defining_search":
            success, error = state_manager.transition_to("ready_to_execute", user=user)
            if not success:
                self.logger.error(f"Failed to transition to ready_to_execute: {error}")
                return {"success": False, "error": error}

        # Refresh from database to ensure latest status
        session.refresh_from_db()

        # Check if we can execute or if execution is already in progress
        valid_execution_states = [
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
        ]
        if session.status in valid_execution_states:
            return {"success": True}
        else:
            self.logger.error(
                f"Session {session.id} is in unexpected state after transition: {session.status}"
            )
            return {
                "success": False,
                "error": f"Cannot execute search from status '{session.get_status_display()}'",
            }

    def initiate_search_execution(
        self, session: SearchSession, user: User, request: Optional[HttpRequest]
    ) -> Dict[str, Any]:
        """Initiate the search execution task.

        Args:
            session: The search session to execute.
            user: The user initiating execution.
            request: The HTTP request for messages.

        Returns:
            Dict with 'success' bool, optional 'task_id', and 'error' message.
        """
        # Track execution time
        start_time = time.time()

        try:
            from apps.serp_execution.tasks import initiate_search_session_execution_task

            # Start the execution task
            task = initiate_search_session_execution_task.delay(str(session.id))

            # Log the execution start
            SessionActivity.log_activity(
                session=session,
                activity_type="search_started",
                description="Search execution initiated",
                user=user,
                metadata={"task_id": task.id},
            )

            # Only add message if request is provided and valid
            if request and hasattr(request, "META"):
                messages.success(
                    request,
                    "Search execution has been initiated. You'll be notified when it's complete.",
                )
                self.logger.debug(
                    f"Request provided for session {session.id} - execution message added"
                )
            else:
                self.logger.warning(
                    f"No valid request provided for session {session.id} - execution message skipped"
                )

            # Log timing information
            elapsed = time.time() - start_time
            self.logger.info(
                f"Search execution initiated in {elapsed:.2f}s for session {session.id}"
            )

            return {"success": True, "task_id": task.id}

        except Exception as e:
            self.logger.error(f"Failed to initiate search execution: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to start search execution: {str(e)}",
            }
