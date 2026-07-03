"""
Processing state validator.

Validates transitions to the 'processing_results' state.
"""

import logging

from .base import BaseStateValidator

logger = logging.getLogger(__name__)


class ProcessingStateValidator(BaseStateValidator):
    """Validates transitions to processing_results state."""

    def __init__(self):
        """Initialize validator with service dependencies."""
        super().__init__()
        # Services will be injected at runtime
        self.execution_service = None
        self.processing_service = None

    def validate(self, session):
        """
        Validate if session can move to 'processing_results' status.

        Checks:
        - Has completed executions with results
        - No existing processing in progress

        Args:
            session: SearchSession instance

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Import services only when needed to avoid circular imports
        if self.execution_service is None:
            from apps.serp_execution.services import ExecutionService

            self.execution_service = ExecutionService

        if self.processing_service is None:
            from apps.results_manager.services import ProcessingService

            self.processing_service = ProcessingService

        # Check for completed executions using service
        completed_executions = self.execution_service.get_completed_execution_count(
            session.id
        )

        if completed_executions == 0:
            return (
                False,
                "No completed executions found. Cannot process results without completed searches.",
            )

        # Check if any execution has results using service
        executions_with_results = (
            self.execution_service.get_executions_with_results_count(session.id)
        )

        if executions_with_results == 0:
            logger.warning(
                f"Session {session.id} has completed executions but no results"
            )
            # Allow processing even with no results to properly complete the workflow

        # Check for existing processing session in progress using service
        active_processing = self.processing_service.has_active_processing(session.id)

        if active_processing:
            return False, "Results processing is already in progress for this session."

        return True, None
