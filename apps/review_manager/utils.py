"""
Utility functions for the review_manager app.

This module contains helper functions for session management, workflow state transitions,
progress calculations, reviewer classification, and other common operations related to
SearchSession management.
"""

from typing import Dict, List

from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from apps.organisation.models import OrganisationMembership
from .models import SearchSession, SessionActivity

User = get_user_model()


def get_session_statistics(user):
    """
    Get comprehensive statistics for a user's search sessions.

    Args:
        user (User): The user to get statistics for

    Returns:
        dict: Dictionary containing session statistics with keys:
            - total_sessions (int): Total number of sessions
            - status_distribution (dict): Count of sessions by status
            - total_results_found (int): Sum of all results found
            - total_results_reviewed (int): Sum of all results reviewed
            - total_results_included (int): Sum of all included results
            - overall_inclusion_rate (float): Percentage of reviewed results included
            - active_sessions (int): Count of non-completed/archived sessions
            - completed_sessions (int): Count of completed sessions
    """
    sessions = SearchSession.objects.filter(owner=user)

    total_sessions = sessions.count()
    status_counts = sessions.values("status").annotate(count=Count("status"))

    # Calculate progress metrics
    total_results = sum(session.total_results for session in sessions)
    total_reviewed = sum(session.reviewed_results for session in sessions)
    total_included = sum(session.included_results for session in sessions)

    return {
        "total_sessions": total_sessions,
        "status_distribution": {
            item["status"]: item["count"] for item in status_counts
        },
        "total_results_found": total_results,
        "total_results_reviewed": total_reviewed,
        "total_results_included": total_included,
        "overall_inclusion_rate": (
            round((total_included / total_reviewed * 100), 1)
            if total_reviewed > 0
            else 0
        ),
        "active_sessions": sessions.exclude(
            status__in=["completed", "archived"]
        ).count(),
        "completed_sessions": sessions.filter(status="completed").count(),
    }


def validate_status_transition(session, new_status):
    """
    Validate if a status transition is allowed and return validation result.

    Args:
        session (SearchSession): The SearchSession instance to validate transition for.
        new_status (str): The desired new status string to transition to.

    Returns:
        tuple[bool, str | None]: A tuple of (is_valid, error_message) where is_valid
            indicates if the transition is valid and error_message contains the error
            description or None if validation passes.
    """
    if session.status == new_status:
        return True, None

    if session.can_transition_to(new_status):
        return True, None

    allowed_transitions = session.get_allowed_transitions()
    allowed_names = [
        dict(SearchSession.STATUS_CHOICES)[status] for status in allowed_transitions
    ]
    error_msg = (
        f"Cannot transition from '{session.get_status_display()}' "
        f"to '{dict(SearchSession.STATUS_CHOICES)[new_status]}'. "
        f"Allowed transitions: {', '.join(allowed_names)}"
    )

    return False, error_msg


def transition_session_status(
    session,
    new_status,
    user=None,
    description=None,
):
    """
    Safely transition a session to a new status with activity logging.

    Args:
        session: The SearchSession instance to transition.
        new_status: The desired new status string to transition to.
        user: User performing the transition (defaults to session owner if None).
        description: Custom description string for the activity log (optional).

    Returns:
        tuple: A tuple of (success, error_message) where success is bool
            and error_message is str or None if operation succeeds.
    """
    # Short-circuit if already in the target state (avoids duplicate activity logs
    # when signals fire multiple times for the same transition)
    if session.status == new_status:
        return True, None

    is_valid, error_msg = validate_status_transition(session, new_status)
    if not is_valid:
        return False, error_msg

    old_status = session.status
    session.status = new_status

    try:
        session.save()

        # Log the activity
        if not description:
            old_name = dict(SearchSession.STATUS_CHOICES)[old_status]
            new_name = dict(SearchSession.STATUS_CHOICES)[new_status]
            description = f"Status changed from {old_name} to {new_name}"

        SessionActivity.log_activity(
            session=session,
            activity_type="status_changed",
            description=description,
            user=user,
            metadata={"old_status": old_status, "new_status": new_status},
        )

        return True, None

    except Exception as e:
        return False, str(e)


def get_sessions_by_status(user, status=None):
    """
    Get user's sessions filtered by status with optimized queries.

    Args:
        user: The User instance to get sessions for.
        status:  status string to filter by (if None, returns all sessions).

    Returns:
        QuerySet: Django QuerySet of SearchSession instances ordered by updated_at descending.
    """
    sessions = SearchSession.objects.filter(owner=user).select_related("owner")

    if status:
        sessions = sessions.filter(status=status)

    return sessions.order_by("-updated_at")


def get_recent_activities(session, limit=10):
    """
    Get recent activities for a session with user information.

    Args:
        session: The SearchSession instance to get activities for.
        limit: Maximum number of activities to return (defaults to 10).

    Returns:
        QuerySet: Django QuerySet of SessionActivity instances ordered by created_at descending,
            with user information prefetched, limited to the specified number of records.
    """
    return (
        SessionActivity.objects.filter(session=session)
        .select_related("user")
        .order_by("-created_at")[:limit]
    )


def calculate_workflow_progress(session):
    """
    Calculate detailed workflow progress information.

    Args:
        session: The SearchSession instance

    Returns:
        Dictionary containing progress information
    """
    status_order = [
        status[0] for status in SearchSession.STATUS_CHOICES if status[0] != "archived"
    ]
    current_index = (
        status_order.index(session.status) if session.status in status_order else 0
    )
    total_steps = len(status_order)

    return {
        "current_step": current_index + 1,
        "total_steps": total_steps,
        "percentage": (
            round((current_index / (total_steps - 1)) * 100, 1)
            if total_steps > 1
            else 0
        ),
        "status_display": session.get_status_display(),
        "next_statuses": [
            dict(SearchSession.STATUS_CHOICES)[status]
            for status in session.get_allowed_transitions()
        ],
        "is_complete": session.status == "completed",
        "is_archived": session.status == "archived",
    }


def get_dashboard_summary(user):
    """
    Get summary data for the user's dashboard.

    Args:
        user: The user to get dashboard data for

    Returns:
        Dictionary containing dashboard summary
    """
    sessions = SearchSession.objects.filter(owner=user)

    # Get sessions by status
    draft_sessions = sessions.filter(status="draft").count()
    active_sessions = sessions.exclude(
        status__in=["completed", "archived", "draft"]
    ).count()
    completed_sessions = sessions.filter(status="completed").count()

    # Get recent sessions
    recent_sessions = sessions.order_by("-updated_at")[:5]

    return {
        "total_sessions": sessions.count(),
        "draft_sessions": draft_sessions,
        "active_sessions": active_sessions,
        "completed_sessions": completed_sessions,
        "recent_sessions": recent_sessions,
        "total_results_across_sessions": sum(s.total_results for s in sessions),
        "requires_attention": sessions.filter(
            Q(status="ready_to_execute") | Q(status="ready_for_review")
        ).count(),
    }


def get_sessions_needing_attention(user):
    """
    Get sessions that need user attention (ready for next action).

    Args:
        user: The User instance to get sessions for.

    Returns:
        QuerySet: Django QuerySet of SearchSession instances with status
            'ready_to_execute' or 'ready_for_review', ordered by updated_at ascending.
    """
    attention_statuses = ["ready_to_execute", "ready_for_review"]
    return SearchSession.objects.filter(
        owner=user, status__in=attention_statuses
    ).order_by("updated_at")


# External Reviewer Classification Functions (Phase B)


def is_user_in_organisation(email: str, organisation) -> bool:
    """
    Check if user email belongs to organisation members.

    Args:
        email: User email address
        organisation: Organisation instance

    Returns:
        bool: True if user is active member, False otherwise
    """
    return OrganisationMembership.objects.filter(
        user__email=email, organisation=organisation, is_active=True
    ).exists()


def classify_invited_reviewers(invited_reviewers: List[Dict], organisation) -> Dict:
    """
    Classify reviewers as internal (org members) or external.

    Args:
        invited_reviewers: List of dicts with 'email', 'first_name', 'last_name'
        organisation: Organisation instance

    Returns:
        dict: {
            'internal': [reviewer_dicts for org members],
            'external': [reviewer_dicts for non-members],
            'counts': {
                'total': int,
                'internal': int,
                'external': int
            }
        }

    Example:
        >>> classification = classify_invited_reviewers(
        ...     [
        ...         {'email': 'alice@ourorg.com', 'first_name': 'Alice', 'last_name': 'Smith'},
        ...         {'email': 'bob@external.com', 'first_name': 'Bob', 'last_name': 'Jones'}
        ...     ],
        ...     organisation
        ... )
        >>> classification
        {
            'internal': [{'email': 'alice@ourorg.com', ...}],
            'external': [{'email': 'bob@external.com', ...}],
            'counts': {'total': 2, 'internal': 1, 'external': 1}
        }
    """
    internal = []
    external = []

    for reviewer in invited_reviewers:
        email = reviewer.get("email", "").strip()

        if not email:
            continue  # Skip empty emails

        if is_user_in_organisation(email, organisation):
            internal.append(reviewer)
        else:
            external.append(reviewer)

    return {
        "internal": internal,
        "external": external,
        "counts": {
            "total": len(invited_reviewers),
            "internal": len(internal),
            "external": len(external),
        },
    }


def requires_is_approval_for_external() -> bool:
    """
    Check if IS approval is required for external reviewer invitations.

    Returns:
        bool: True if approval required, False if invitations sent immediately

    Usage:
        if requires_is_approval_for_external():
            # Store for approval
            store_for_approval(external_reviewers)
        else:
            # Send immediately
            send_invitations(external_reviewers)
    """
    try:
        from constance import config

        return config.REQUIRE_IS_APPROVAL_FOR_EXTERNAL_INVITES
    except ImportError:
        # Constance not available, use default
        return False
    except AttributeError:
        # Config key not found, use default
        return False


def get_invitation_rate_limit() -> int:
    """
    Get current invitation rate limit per hour.

    Returns:
        int: Maximum invitations allowed per hour
    """
    try:
        from constance import config

        return config.INVITATION_RATE_LIMIT_PER_HOUR
    except ImportError:
        # Constance not available, use default
        return 10
    except AttributeError:
        # Config key not found, use default
        return 10


def get_invitation_expiry_days() -> int:
    """
    Get invitation expiry period in days.

    Returns:
        int: Number of days before invitation expires
    """
    try:
        from constance import config

        return config.INVITATION_EXPIRY_DAYS
    except ImportError:
        # Constance not available, use default
        return 7
    except AttributeError:
        # Config key not found, use default
        return 7
