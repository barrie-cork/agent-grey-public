"""
Database State Manager Service

Atomic database state transition management.
Replaces complex event-driven state changes with simple database transactions.
"""

import logging
from typing import TypedDict

from django.db import transaction
from django.utils import timezone

from .base import BaseService

logger = logging.getLogger(__name__)


class StateManagerConfig(TypedDict):
    cache_timeout: int
    max_retries: int
    transition_timeout: int


class DatabaseStateManager(BaseService[StateManagerConfig]):
    """
    Atomic database state transition management.
    Replaces complex event-driven state changes with simple database transactions.
    """

    SERVICE_NAME = "DatabaseStateManager"
    SERVICE_VERSION = "2.0.0"

    def get_default_config(self) -> StateManagerConfig:
        """Get default state manager configuration."""
        return {"cache_timeout": 300, "max_retries": 3, "transition_timeout": 30}

    def _initialize(self) -> None:
        """Initialize state manager resources."""
        pass  # No special initialization needed

    def health_check(self) -> bool:
        """Check if state manager is healthy."""
        try:
            # Test database transaction capability
            with transaction.atomic():
                # Simple test transaction
                pass
            return True
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    @transaction.atomic
    def set_session_status(self, session, status: str, detail: str = "") -> bool:
        """
        Atomically update session status and detail.

        Args:
            session: SearchSession instance
            status: New status value
            detail: Optional status detail message

        Returns:
            True if update successful
        """
        with self._measure_performance("set_session_status"):
            try:
                # Get default status message if detail not provided
                if not detail and hasattr(session, "STATUS_MESSAGES"):
                    detail = session.STATUS_MESSAGES.get(status, "")

                # Atomic update of status fields
                session.status = status
                session.status_detail = detail
                session.updated_at = timezone.now()

                session.save(update_fields=["status", "status_detail", "updated_at"])

                self.logger.info(f"Session {session.id} status: {status} - {detail}")
                return True

            except Exception as e:
                self._handle_error(
                    e,
                    {"session_id": session.id, "status": status},
                    "set_session_status",
                )
                return False

    @transaction.atomic
    def update_session_detail(self, session, detail: str) -> bool:
        """
        Update just the status detail message.

        Args:
            session: SearchSession instance
            detail: Status detail message

        Returns:
            True if update successful
        """
        with self._measure_performance("update_session_detail"):
            try:
                session.status_detail = detail
                session.updated_at = timezone.now()
                session.save(update_fields=["status_detail", "updated_at"])

                self.logger.debug(f"Session {session.id} detail: {detail}")
                return True

            except Exception as e:
                self._handle_error(
                    e, {"session_id": session.id}, "update_session_detail"
                )
                return False
