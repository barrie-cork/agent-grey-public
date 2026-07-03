"""Session access-control helpers for review_manager.

Centralises the "owner or accepted-invitation reviewer" rule so it can be
shared by review_results and reporting without duplicating the logic. The
helper operates purely on review_manager models (SearchSession and
ReviewInvitation), so it belongs with those models rather than in core.
"""


def check_session_access(user, session) -> tuple[bool, str | None]:
    """Check whether a user can access a session (owner or accepted invitation).

    Returns (True, None) if access is granted, or (False, reason) if denied.
    """
    if session.owner == user:
        return True, None

    from apps.review_manager.models import ReviewInvitation

    has_accepted_invitation = ReviewInvitation.objects.filter(
        session=session,
        invitee_email=user.email,
        status=ReviewInvitation.STATUS_ACCEPTED,
    ).exists()

    if has_accepted_invitation:
        return True, None

    return False, (
        "You don't have permission to access this session. "
        "If you were invited, please accept the invitation first."
    )
