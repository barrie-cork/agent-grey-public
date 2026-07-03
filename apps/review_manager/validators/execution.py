"""
Execution state validator.

Validates transitions to the 'executing' state.
"""

import logging

from .base import BaseStateValidator

logger = logging.getLogger(__name__)


class ExecutionStateValidator(BaseStateValidator):
    """Validates transitions to executing state."""

    def __init__(self):
        """Initialize validator with service dependencies."""
        super().__init__()
        # Services will be injected at runtime
        self.query_service = None
        self.execution_service = None

    def validate(self, session):
        """
        Validate if session can move to 'executing' status.

        Checks:
        - Session has active queries defined
        - No existing executions are in progress
        - Session is properly configured

        Args:
            session: SearchSession instance

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Import services only when needed to avoid circular imports
        if self.query_service is None:
            from apps.search_strategy.services import QueryService

            self.query_service = QueryService

        if self.execution_service is None:
            from apps.serp_execution.services import ExecutionService

            self.execution_service = ExecutionService

        # Check for active queries using service
        active_queries = self.query_service.get_active_query_count(session.id)

        if active_queries == 0:
            return (
                False,
                "No active queries defined. Please define search queries before executing.",
            )

        # Check if already has pending/running executions using service
        existing_executions = self.execution_service.get_pending_execution_count(
            session.id
        )

        if existing_executions > 0:
            return (
                False,
                f"Session has {existing_executions} executions already in progress.",
            )

        # Check if session has a search strategy using service
        if not self.query_service.has_search_strategy(session.id):
            return False, "No search strategy defined for this session."

        logger.debug(
            f"Session {session.id} validated for execution: {active_queries} active queries"
        )
        return True, None
