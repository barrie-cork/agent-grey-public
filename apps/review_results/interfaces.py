"""
Interfaces for review_results app to avoid cross-app dependencies.

This module defines abstract interfaces that other apps can implement
to provide data to the review_results app without creating direct
dependencies between apps.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    pass


class IResultsProvider(ABC):
    """
    Interface for providing processed results to the review process.

    This interface abstracts the results_manager dependency.
    """

    @abstractmethod
    def get_results_queryset_for_session(self, session_id: UUID):
        """Get results as queryset for annotation."""

    @abstractmethod
    def get_results_for_session(self, session_id: UUID):
        """
        Get all processed results for a given session.

        Args:
            session_id: UUID of the search session

        Returns:
            List of ProcessedResult objects
        """

    @abstractmethod
    def get_result_by_id(self, result_id: UUID, session_id: UUID):
        """
        Get a specific processed result by ID, ensuring it belongs to the session.

        Args:
            result_id: UUID of the processed result
            session_id: UUID of the search session (for validation)

        Returns:
            ProcessedResult object or None if not found
        """

    @abstractmethod
    def mark_result_as_reviewed(self, result_id: UUID) -> bool:
        """
        Mark a result as reviewed.

        Args:
            result_id: UUID of the processed result

        Returns:
            True if successful, False otherwise
        """

    @abstractmethod
    def get_results_count(self, session_id: UUID) -> int:
        """
        Get count of results for a session.

        Args:
            session_id: UUID of the search session

        Returns:
            Number of results
        """


class ISessionProvider(ABC):
    """
    Interface for providing search session data.

    This interface abstracts the review_manager dependency.
    """

    @abstractmethod
    def get_session(self, session_id: UUID):
        """
        Get a search session by ID.

        Args:
            session_id: UUID of the search session

        Returns:
            SearchSession object or None if not found
        """

    @abstractmethod
    def get_session_owner_id(self, session_id: UUID):
        """
        Get the owner ID of a session without loading the full session.

        Args:
            session_id: UUID of the search session

        Returns:
            UUID of the owner or None if session not found
        """

    @abstractmethod
    def update_session_status(self, session_id: UUID, new_status: str) -> bool:
        """
        Update the status of a search session.

        Args:
            session_id: UUID of the search session
            new_status: New status value

        Returns:
            True if successful, False otherwise
        """
