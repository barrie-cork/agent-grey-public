"""
Centralized error handling for task orchestration.

This service provides consistent error handling and logging for
the results processing pipeline.
"""

import logging

from apps.review_manager.models import SearchSession

from ..api_types import ProcessingError
from ..constants import TaskConstants
from ..models import ProcessingSession

logger = logging.getLogger(__name__)


class TaskErrorHandler:
    """Centralized error handling for processing tasks."""

    def __init__(self, session_id: str):
        """
        Initialize the error handler.

        Args:
            session_id: The session ID being processed
        """
        self.session_id = str(session_id)

    def handle_exception(self, exception, retries=0):
        """
        Handle and log exceptions consistently.

        Args:
            exception: The exception that occurred
            retries: Number of retries attempted

        Returns:
            ProcessingError object with error details
        """
        error_type = type(exception).__name__

        # Handle specific exception types
        if isinstance(exception, SearchSession.DoesNotExist):
            logger.error(f"SearchSession {self.session_id} not found")
            return ProcessingError(
                session_id=self.session_id,
                error=f"Session {self.session_id} not found",
                error_type=error_type,
            )

        # Handle lock acquisition errors
        if "Could not acquire lock" in str(exception):
            logger.info(f"Session {self.session_id} already being processed")
            return ProcessingError(
                session_id=self.session_id,
                error="Session is already being processed",
                error_type="LockAcquisitionError",
                can_retry=False,
            )

        # Generic error handling
        logger.error(f"Error processing {self.session_id}: {exception}")
        return ProcessingError(
            session_id=self.session_id,
            error=str(exception),
            error_type=error_type,
            retries_attempted=retries,
            can_retry=retries < TaskConstants.MAX_RETRIES,
        )

    def mark_processing_failed(self, exception):
        """
        Mark the processing session as failed.

        Args:
            exception: The exception that caused the failure
        """
        try:
            processing_session = ProcessingSession.objects.get(
                search_session_id=self.session_id
            )
            processing_session.fail_processing(
                error_message=f"Failed to start processing: {str(exception)}",
                error_details={"exception_type": type(exception).__name__},
            )
        except ProcessingSession.DoesNotExist:
            logger.warning(
                f"Could not mark ProcessingSession as failed - "
                f"session {self.session_id} not found"
            )

    def should_retry(self, exception, retries):
        """
        Determine if the task should be retried.

        Args:
            exception: The exception that occurred
            retries: Current retry count

        Returns:
            bool: True if should retry, False otherwise
        """
        # Don't retry lock acquisition errors
        if "Could not acquire lock" in str(exception):
            return False

        # Don't retry if max retries reached
        if retries >= TaskConstants.MAX_RETRIES:
            return False

        # Don't retry DoesNotExist errors
        if isinstance(
            exception, (SearchSession.DoesNotExist, ProcessingSession.DoesNotExist)
        ):
            return False

        return True

    def get_retry_delay(self, retries):
        """
        Calculate retry delay with exponential backoff.

        Args:
            retries: Current retry count

        Returns:
            int: Delay in seconds
        """
        return TaskConstants.RETRY_DELAY * (2**retries)
