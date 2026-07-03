"""
Provider implementations for review_manager slice.
Implements protocols for dependency injection.
"""

from django.shortcuts import get_object_or_404

from .models import SearchSession
from .signals import get_session_data


class SessionProviderImpl:
    """Implementation of SessionProvider protocol."""

    def get_session(self, session_id: str) -> SearchSession:
        """Get session by ID."""
        return get_object_or_404(SearchSession, id=session_id)

    def get_session_data(self, session_id: str):
        """Get session data for display."""
        return get_session_data(session_id)

    def verify_session_ownership(self, session_id: str, user) -> bool:
        """Verify user owns the session."""
        try:
            session = SearchSession.objects.get(id=session_id)
            return session.owner == user
        except SearchSession.DoesNotExist:
            return False

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists."""
        return SearchSession.objects.filter(id=session_id).exists()

    def get_session_state(self, session_id: str) -> str:
        """Get current state of a session."""
        session = self.get_session(session_id)
        return session.status

    def get_session_queries(self, session_id: str):
        """Get queries for a session."""
        from apps.search_strategy.models import SearchQuery

        return list(SearchQuery.objects.filter(session__id=session_id))

    def get_session_for_diagnostic(self, session_id: str) -> dict:
        """Get session data for diagnostic purposes."""
        session = self.get_session(session_id)
        return {
            "id": str(session.id),
            "status": session.status,
            "status_display": session.get_status_display(),
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "transitions": {
                "allowed_from_current": session.get_allowed_transitions(),
                "can_execute": session.can_transition_to("executing"),
                "can_process": session.can_transition_to("processing_results"),
                "can_review": session.can_transition_to("ready_for_review"),
            },
            "queries": {
                "total": session.search_queries_denorm.count(),
                "active": session.search_queries_denorm.filter(is_active=True).count(),
            },
        }
