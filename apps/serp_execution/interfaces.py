"""
Interface definitions for cross-app dependencies.
Provides protocols for dependency injection to eliminate direct cross-app imports.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class NotificationService(Protocol):
    """Interface for notification service.

    Abstracts notification sending functionality.
    """

    def notify_execution_complete(self, session_id: str, status: str) -> None:
        """Send notification when execution completes.

        Args:
            session_id: UUID string of the session
            status: Final execution status
        """
        ...

    def notify_error(self, session_id: str, error_message: str) -> None:
        """Send error notification.

        Args:
            session_id: UUID string of the session
            error_message: Error details
        """
        ...

    def notify_progress(self, session_id: str, progress: int, step: str = "") -> None:
        """Send progress update notification.

        Args:
            session_id: UUID string of the session
            progress: Progress percentage (0-100)
            step: Optional description of current step
        """
        ...
