"""
Dependency injection and adapter implementations.
Provides concrete implementations of interfaces and manages dependency registry.
"""

import logging
import threading
from typing import Any, cast

from apps.core.interfaces import SessionProvider

from .interfaces import NotificationService

logger = logging.getLogger(__name__)


class DefaultSessionProvider:
    """Default implementation using review_manager models.

    This adapter isolates all imports from review_manager app.
    """

    def get_session(self, session_id: str) -> Any:
        """Get session by ID. Returns None if the session no longer exists."""
        from apps.review_manager.models import SearchSession

        try:
            return SearchSession.objects.get(id=session_id)
        except SearchSession.DoesNotExist:
            logger.warning("get_session: SearchSession %s not found", session_id)
            return None

    def get_session_data(self, session_id: str):
        """Get session data for display. Returns None if the session no longer exists."""
        from apps.review_manager.models import SearchSession

        try:
            session = SearchSession.objects.get(id=session_id)
        except SearchSession.DoesNotExist:
            logger.warning("get_session_data: SearchSession %s not found", session_id)
            return None
        return {
            "id": str(session.id),
            "title": session.title,
            "status": session.status,
            "owner_id": str(session.owner.id),
            "created_at": session.created_at.isoformat(),
            "total_queries": session.total_queries,
            "total_results": session.total_results,
            "reviewed_results": session.reviewed_results,
            "included_results": session.included_results,
        }

    def get_session_queries(self, session_id: str):
        """Get queries for a session."""
        from apps.search_strategy.models import SearchQuery

        return list(SearchQuery.objects.filter(session__id=session_id))

    def get_session_state(self, session_id: str) -> str:
        """Get current state of a session. Returns 'not_found' if the session no longer exists."""
        from apps.review_manager.models import SearchSession

        try:
            session = SearchSession.objects.get(id=session_id)
        except SearchSession.DoesNotExist:
            logger.warning("get_session_state: SearchSession %s not found", session_id)
            return "not_found"
        return session.status

    def session_exists(self, session_id: str) -> bool:
        """Check if session exists."""
        from apps.review_manager.models import SearchSession

        return SearchSession.objects.filter(id=session_id).exists()

    def verify_session_ownership(self, session_id: str, user: Any) -> bool:
        """Verify that the user owns the session."""
        from apps.review_manager.models import SearchSession

        try:
            session = SearchSession.objects.get(id=session_id)
            return session.owner == user
        except SearchSession.DoesNotExist:
            return False

    def get_session_for_diagnostic(self, session_id: str) -> dict:
        """Get session data for diagnostic purposes. Returns empty dict if session not found."""
        from apps.review_manager.models import SearchSession

        try:
            session = SearchSession.objects.get(id=session_id)
        except SearchSession.DoesNotExist:
            logger.warning(
                "get_session_for_diagnostic: SearchSession %s not found", session_id
            )
            return {}
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


class DefaultNotificationService:
    """Default implementation for notifications using WebSocket integration.

    Sends real-time state updates and progress notifications via WebSocket.
    """

    def __init__(self):
        """Initialize notification service."""
        pass

    def notify_execution_complete(self, session_id: str, status: str) -> None:
        """Send notification when execution completes via WebSocket."""
        logger.info(
            f"Execution completed for session {session_id} with status: {status}"
        )

        # Get session to determine owner for WebSocket broadcast
        try:
            from uuid import UUID

            from apps.review_manager.models import SearchSession

            session_uuid = (
                UUID(session_id) if isinstance(session_id, str) else session_id
            )
            session = SearchSession.objects.select_related("owner").get(id=session_uuid)

            # Map status to state names
            state_mapping = {
                "auto_transition": "processing_results",
                "ready_for_review": "ready_for_review",
                "completed": "completed",
                "failed": "failed",
            }

            new_state = state_mapping.get(status, status)

            # Update session status directly
            if new_state == "processing_results":
                session.update_status_detail(f"Search execution {status}")
            else:
                session.set_status(new_state, f"Search execution {status}")

        except Exception as e:
            logger.error(f"Failed to send WebSocket notification for {session_id}: {e}")

    def notify_error(self, session_id: str, error_message: str) -> None:
        """Send error notification via WebSocket."""
        logger.error(f"Error in session {session_id}: {error_message}")

        try:
            from uuid import UUID

            from apps.review_manager.models import SearchSession

            session_uuid = (
                UUID(session_id) if isinstance(session_id, str) else session_id
            )
            session = SearchSession.objects.select_related("owner").get(id=session_uuid)

            # Update session status directly with error
            session.update_status_detail(f"Error: {error_message}")

        except Exception as e:
            logger.error(f"Failed to send error notification for {session_id}: {e}")

    def notify_progress(self, session_id: str, progress: int, step: str = "") -> None:
        """Send progress update notification via WebSocket."""
        try:
            from uuid import UUID

            from apps.review_manager.models import SearchSession

            session_uuid = (
                UUID(session_id) if isinstance(session_id, str) else session_id
            )
            session = SearchSession.objects.select_related("owner").get(id=session_uuid)

            # Update session status directly with progress
            session.update_status_detail(step or "Executing search queries")

        except Exception as e:
            logger.warning(
                f"Failed to send progress notification for {session_id}: {e}"
            )


# Dependency injection registry
_providers: dict[str, Any] = {
    "session": None,
    "notification": None,
}
_providers_lock = threading.Lock()


def get_session_provider() -> SessionProvider:
    """Get the session provider implementation."""
    if not _providers["session"]:
        with _providers_lock:
            if not _providers["session"]:
                _providers["session"] = DefaultSessionProvider()
    return cast(SessionProvider, _providers["session"])


def get_notification_service() -> NotificationService:
    """Get the notification service implementation."""
    if not _providers["notification"]:
        with _providers_lock:
            if not _providers["notification"]:
                _providers["notification"] = DefaultNotificationService()
    return _providers["notification"]


def reset_providers() -> None:
    """Reset all providers to None (useful for testing)."""
    global _providers
    with _providers_lock:
        _providers = {
            "session": None,
            "notification": None,
        }
