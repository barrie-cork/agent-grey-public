"""
Concrete implementations of interfaces for review_results app.

This module provides concrete implementations of the interfaces
defined in interfaces.py, maintaining separation between apps.
"""

from uuid import UUID

from django.apps import apps

from .interfaces import IResultsProvider, ISessionProvider


class DjangoResultsProvider(IResultsProvider):
    """
    Django ORM-based implementation of IResultsProvider.

    This implementation uses Django's app registry to avoid
    direct imports at module level.
    """

    def __init__(self):
        # Lazy import to avoid circular dependencies
        self._processed_result_model = None

    @property
    def ProcessedResult(self):
        """Lazy load ProcessedResult model."""
        if self._processed_result_model is None:
            self._processed_result_model = apps.get_model(
                "results_manager", "ProcessedResult"
            )
        return self._processed_result_model

    def get_results_queryset_for_session(self, session_id: UUID):
        """Return queryset (not list) to allow further annotation."""
        return (
            self.ProcessedResult.objects.filter(
                session_id=session_id,
                processing_status="success",
                is_hidden=False,
            )
            .prefetch_related("simplereviewdecision")
            .order_by("-processed_at")
        )

    def get_results_for_session(self, session_id: UUID) -> list:
        """Backward compatible - returns list."""
        return list(self.get_results_queryset_for_session(session_id))

    def get_result_by_id(self, result_id: UUID, session_id: UUID):
        """Get a specific processed result by ID."""
        try:
            return self.ProcessedResult.objects.get(id=result_id, session_id=session_id)
        except self.ProcessedResult.DoesNotExist:
            return None

    def mark_result_as_reviewed(self, result_id: UUID) -> bool:
        """Mark a result as reviewed."""
        try:
            result = self.ProcessedResult.objects.get(id=result_id)
            result.is_reviewed = True
            result.save(update_fields=["is_reviewed"])
            return True
        except self.ProcessedResult.DoesNotExist:
            return False

    def get_results_count(self, session_id: UUID) -> int:
        """Get count of results for a session."""
        return self.ProcessedResult.objects.filter(session_id=session_id).count()


class DjangoSessionProvider(ISessionProvider):
    """
    Django ORM-based implementation of ISessionProvider.

    This implementation uses Django's app registry to avoid
    direct imports at module level.
    """

    def __init__(self):
        # Lazy import to avoid circular dependencies
        self._search_session_model = None

    @property
    def SearchSession(self):
        """Lazy load SearchSession model."""
        if self._search_session_model is None:
            self._search_session_model = apps.get_model(
                "review_manager", "SearchSession"
            )
        return self._search_session_model

    def get_session(self, session_id: UUID):
        """Get a search session by ID."""
        try:
            return self.SearchSession.objects.get(id=session_id)
        except self.SearchSession.DoesNotExist:
            return None

    def get_session_owner_id(self, session_id: UUID):
        """Get the owner ID of a session without loading the full session."""
        try:
            session = self.SearchSession.objects.only("owner_id").get(id=session_id)
            return session.owner_id
        except self.SearchSession.DoesNotExist:
            return None

    def update_session_status(self, session_id: UUID, new_status: str) -> bool:
        """Update the status of a search session."""
        try:
            self.SearchSession.objects.filter(id=session_id).update(status=new_status)
            return True
        except Exception:
            return False


# Factory functions to get provider instances
def get_results_provider() -> IResultsProvider:
    """Get the default results provider instance."""
    return DjangoResultsProvider()


def get_session_provider() -> ISessionProvider:
    """Get the default session provider instance."""
    return DjangoSessionProvider()
