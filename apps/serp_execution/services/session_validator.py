"""
Session validation service for serp_execution.
Handles all session validation logic for execution tasks.
"""

import logging
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist

from apps.serp_execution.api_types import SessionValidationResult

if TYPE_CHECKING:
    from apps.review_manager.models import SearchSession

logger = logging.getLogger(__name__)


class SessionValidator:
    """Validates search sessions for execution readiness."""

    EXECUTABLE_STATES = [
        "ready_to_execute",
        "executing",
        "processing_results",
        "ready_for_review",
    ]

    def __init__(self):
        """Initialize the session validator."""
        self.logger = logger.getChild(self.__class__.__name__)

    def validate_session(self, session_id: UUID) -> SessionValidationResult:
        """
        Validate that a session exists and is ready for execution.

        Args:
            session_id: The UUID of the session to validate

        Returns:
            SessionValidationResult with validation details
        """
        from apps.review_manager.models import SearchSession
        from apps.search_strategy.models import SearchQuery

        session_id_str = str(session_id)

        try:
            # Get session with related data
            session = SearchSession.objects.select_related(
                "owner", "search_strategy"
            ).get(id=session_id)

            self.logger.info(
                f"Validating session {session_id}, status: {session.status}"
            )

            # Check if session is in executable state
            can_execute = session.status in self.EXECUTABLE_STATES

            if not can_execute:
                error_message = (
                    f"Session not in executable state. "
                    f"Current status: {session.status}, "
                    f"Required: {', '.join(self.EXECUTABLE_STATES)}"
                )
                self.logger.warning(error_message)

                return SessionValidationResult(
                    is_valid=True,  # Session exists
                    session_id=session_id_str,
                    current_status=session.status,
                    error_message=error_message,
                    can_execute=False,
                    query_count=0,
                )

            # Check for active queries
            query_count = SearchQuery.objects.filter(
                strategy__session=session, is_active=True
            ).count()

            if query_count == 0:
                error_message = "No active queries found for session"
                self.logger.warning(f"Session {session_id} has no active queries")

                return SessionValidationResult(
                    is_valid=True,
                    session_id=session_id_str,
                    current_status=session.status,
                    error_message=error_message,
                    can_execute=False,
                    query_count=0,
                )

            # All validations passed
            self.logger.info(
                f"Session {session_id} validated successfully with "
                f"{query_count} queries"
            )

            return SessionValidationResult(
                is_valid=True,
                session_id=session_id_str,
                current_status=session.status,
                error_message=None,
                can_execute=True,
                query_count=query_count,
            )

        except ObjectDoesNotExist:
            error_message = f"Session {session_id} not found"
            self.logger.error(error_message)

            return SessionValidationResult(
                is_valid=False,
                session_id=session_id_str,
                current_status="not_found",
                error_message=error_message,
                can_execute=False,
                query_count=0,
            )

        except Exception as e:
            error_message = f"Validation error: {str(e)}"
            self.logger.error(
                f"Unexpected error validating session {session_id}: {e}", exc_info=True
            )

            return SessionValidationResult(
                is_valid=False,
                session_id=session_id_str,
                current_status="error",
                error_message=error_message,
                can_execute=False,
                query_count=0,
            )

    def get_session_with_validation(
        self, session_id: UUID
    ) -> Optional["SearchSession"]:
        """
        Get a session object if it passes validation.

        Args:
            session_id: The UUID of the session

        Returns:
            SearchSession object if valid and executable, None otherwise
        """
        from apps.review_manager.models import SearchSession

        validation = self.validate_session(session_id)

        if not validation["is_valid"] or not validation["can_execute"]:
            return None

        try:
            return SearchSession.objects.select_related("owner", "search_strategy").get(
                id=session_id
            )
        except ObjectDoesNotExist:
            return None
