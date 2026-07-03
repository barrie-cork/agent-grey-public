"""
Review state validator.

Validates transitions to the 'ready_for_review' state.
"""

import logging

from .base import BaseStateValidator

logger = logging.getLogger(__name__)


class ReviewStateValidator(BaseStateValidator):
    """Validates transitions to ready_for_review state."""

    def __init__(self):
        """Initialize validator with service dependencies."""
        super().__init__()
        # Services will be injected at runtime
        self.processing_service = None

    def validate(self, session):
        """
        Validate if session can move to 'ready_for_review' status.

        Checks:
        - Results have been processed
        - ProcessedResult records exist

        Args:
            session: SearchSession instance

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Import services only when needed to avoid circular imports
        if self.processing_service is None:
            from apps.results_manager.services import ProcessingService

            self.processing_service = ProcessingService

        # Check if processing was completed using service
        completed_processing = self.processing_service.has_completed_processing(
            session.id
        )

        if not completed_processing:
            # Check if there are any processed results (legacy support) using service
            processed_count = self.processing_service.get_processed_result_count(
                session.id
            )

            if processed_count == 0:
                return (
                    False,
                    "No processed results found. Results must be processed before review.",
                )

            logger.info(
                f"Session {session.id} has {processed_count} processed results (legacy path)"
            )

        # Verify session has results to review
        if session.total_results == 0:
            # This is allowed - session can complete with no results
            logger.info(f"Session {session.id} moving to review with 0 results")

        return True, None
