"""
Mixins for the review_results app views.

This module contains common mixins used across review views to provide
shared functionality like session ownership validation and access control.
"""

from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.review_manager.access import check_session_access

from ..providers import get_session_provider

# Re-exported for backwards compatibility: existing callers import
# check_session_access from this module (e.g. review_results.api.utils).
__all__ = ["check_session_access", "SessionOwnershipMixin"]


class SessionOwnershipMixin:
    """
    Mixin to ensure authenticated user owns the search session or is an invited reviewer.

    This mixin provides session access validation for all review views.
    It allows access for:
    - Session owners (users who created the session)
    - Invited reviewers who have accepted their invitations

    This enables dual-screening workflows where multiple reviewers can
    access and review the same session's results.
    """

    def get_session(self):
        """
        Get and validate session access (ownership or accepted invitation).

        Retrieves the search session from the URL parameter and validates that
        the current authenticated user either owns the session or has accepted
        an invitation to review it.

        Returns:
            SearchSession: The validated session object accessible by current user

        Raises:
            Http404: When session is not found
            PermissionDenied: When user doesn't have access to the session
        """
        session_id = self.kwargs.get("session_id")  # type: ignore[attr-defined]
        session_provider = get_session_provider()
        session = session_provider.get_session(session_id)

        if not session:
            raise Http404("Session not found")

        user = self.request.user  # type: ignore[attr-defined]
        has_access, reason = check_session_access(user, session)
        if not has_access:
            raise PermissionDenied(reason)

        return session
