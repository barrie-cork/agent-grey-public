"""
Core interfaces for dependency injection and vertical slice abstraction.
Defines protocols for cross-slice communication without direct imports.
"""

from typing import Any, Protocol


class SessionProvider(Protocol):
    """Protocol for accessing session data across slices."""

    def get_session(self, session_id: str) -> Any:
        """Get session by ID.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            SearchSession object matching the provided ID.
        """
        ...

    def get_session_data(self, session_id: str) -> Any:
        """Get session data for display.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            dict: Session data formatted for template display.
        """
        ...

    def get_session_queries(self, session_id: str) -> Any:
        """Get queries for a session.

        Args:
            session_id: UUID string of the session.

        Returns:
            List of query objects.
        """
        ...

    def verify_session_ownership(self, session_id: str, user) -> bool:
        """Verify user owns the session."""
        ...

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists."""
        ...

    def get_session_state(self, session_id: str) -> str:
        """Get current state of a session."""
        ...

    def get_session_for_diagnostic(self, session_id: str) -> dict:
        """Get session data for diagnostic purposes."""
        ...
