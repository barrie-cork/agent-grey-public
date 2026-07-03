"""
Concrete implementations of interfaces for results_manager app.

This module provides concrete implementations that other apps can use
to access results_manager functionality without direct imports.
"""

from uuid import UUID

from apps.review_results.interfaces import IResultsProvider

from .models import ProcessedResult


class ResultsProvider(IResultsProvider):
    """Concrete implementation of IResultsProvider for results_manager."""

    def get_results_queryset_for_session(self, session_id: UUID):
        """Return queryset (not list) to allow further annotation."""
        return ProcessedResult.objects.filter(session__id=session_id)

    def get_results_for_session(self, session_id: UUID):
        """Get all processed results for a given session."""
        return list(self.get_results_queryset_for_session(session_id))

    def get_result_by_id(self, result_id: UUID, session_id: UUID):
        """Get a specific processed result by ID, ensuring it belongs to the session."""
        try:
            return ProcessedResult.objects.get(id=result_id, session__id=session_id)
        except ProcessedResult.DoesNotExist:
            return None

    def mark_result_as_reviewed(self, result_id: UUID) -> bool:
        """Mark a result as reviewed."""
        try:
            result = ProcessedResult.objects.get(id=result_id)
            result.is_reviewed = True
            result.save(update_fields=["is_reviewed"])
            return True
        except ProcessedResult.DoesNotExist:
            return False

    def get_results_count(self, session_id: UUID) -> int:
        """Get count of processed results for a session."""
        return ProcessedResult.objects.filter(session__id=session_id).count()


# Factory function to get provider instance
def get_results_provider() -> IResultsProvider:
    """Get the default results provider instance."""
    return ResultsProvider()
