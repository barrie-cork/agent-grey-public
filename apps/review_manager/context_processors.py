"""
Context processors for review_manager app.

Provides template context variables available to all templates.
"""

from typing import Any, Dict

from django.http import HttpRequest

from apps.review_manager.models import ReviewInvitation


def pending_invitations(request: HttpRequest) -> Dict[str, Any]:
    """
    Add pending invitations count to all templates.

    Provides the number of pending review invitations for the current user,
    enabling the notification badge in the navbar.

    Args:
        request: HttpRequest object

    Returns:
        dict: Context dictionary with 'pending_invitations_count' key
    """
    if not request.user.is_authenticated:
        return {"pending_invitations_count": 0}

    try:
        count = ReviewInvitation.objects.filter(
            invitee_email=request.user.email, status=ReviewInvitation.STATUS_PENDING
        ).count()

        return {"pending_invitations_count": count}

    except Exception:
        # If there's any error (e.g., database unavailable), return 0
        # to prevent template rendering from failing
        return {"pending_invitations_count": 0}
