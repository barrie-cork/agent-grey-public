"""Shared access-control utilities for session-scoped API endpoints.

All session-scoped endpoints should resolve the session first, validate access
via ``_has_session_access``, then use ``session.organisation`` for downstream
operations.  This avoids reliance on ``request.organisation`` which may not
match the session's org for cross-org reviewers.
"""

from __future__ import annotations

from collections.abc import Sequence

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import ConflictResolution
from apps.review_results.views.mixins import check_session_access


def _has_session_access(
    request: Request,
    session: SearchSession,
    allow_roles: Sequence[str] | None = None,
) -> bool:
    """Check if the request user has access to *session*.

    Two access tiers (GH #230):
    1. **Participation** (always): the user is the session owner or an accepted
       reviewer (the canonical ``check_session_access`` rule used by the
       session-detail page and reporting). This is the only tier for screening
       surfaces (work queue, claim, decide).
    2. **Oversight** (opt-in via *allow_roles*): the user holds one of the given
       org-scoped permissions in the session's organisation (e.g.
       ``CONFLICT_RESOLVE`` for arbitration, ``REVIEW_CREATE``/``CONFLICT_VIEW``
       for dashboards). Lets arbitrators/leads reach oversight endpoints without
       a per-session invitation.

    Mere organisation membership is NOT sufficient -- the old org fast-path let a
    non-invited org member read (and, via claim->decide, write to) a session they
    were never invited to.
    """
    # Tier 1: participation (owner or accepted invitation)
    has_access, _reason = check_session_access(request.user, session)
    if has_access:
        return True

    # Tier 2: org-role oversight, only for endpoints that opt in. Requires a
    # real session organisation -- without one, has_perm() would fall back to
    # the requester's ambient org context (OrganisationMiddleware contextvar)
    # instead of failing closed, letting an unrelated org's role holder pass.
    if allow_roles and session.organisation:
        return any(
            request.user.has_perm(perm, session.organisation) for perm in allow_roles
        )

    return False


def get_validated_session(
    request: Request,
    session_id: str | None = None,
    allow_roles: Sequence[str] | None = None,
) -> tuple[SearchSession, None] | tuple[None, Response]:
    """Validate session access and return session or error Response.

    If *session_id* is ``None``, reads it from ``request.query_params``.
    *allow_roles* opts the endpoint into org-role oversight access (see
    ``_has_session_access``).
    Returns ``(session, None)`` on success or ``(None, error_response)`` on failure.
    """
    if session_id is None:
        session_id = request.query_params.get("session_id")
    if not session_id:
        return None, Response(
            {"error": "missing_parameter", "message": "session_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        session = SearchSession.objects.get(id=session_id)
    except SearchSession.DoesNotExist:
        return None, Response(
            {"error": "not_found", "message": "Session not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not _has_session_access(request, session, allow_roles):
        return None, Response(
            {"error": "not_found", "message": "Session not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    return session, None


def get_validated_result(
    request: Request,
    result_id: str,
    allow_roles: Sequence[str] | None = None,
) -> tuple[ProcessedResult, SearchSession, None] | tuple[None, None, Response]:
    """Validate access to a result via its parent session.

    *allow_roles* opts the endpoint into org-role oversight access (see
    ``_has_session_access``).
    Returns ``(result, session, None)`` on success or
    ``(None, None, error_response)`` on failure.
    """
    try:
        result = ProcessedResult.objects.select_related("session").get(id=result_id)
    except ProcessedResult.DoesNotExist:
        return (
            None,
            None,
            Response(
                {"error": "not_found", "message": "Result not found"},
                status=status.HTTP_404_NOT_FOUND,
            ),
        )

    session = result.session
    if not _has_session_access(request, session, allow_roles):
        return (
            None,
            None,
            Response(
                {"error": "not_found", "message": "Result not found"},
                status=status.HTTP_404_NOT_FOUND,
            ),
        )

    return result, session, None


def get_validated_conflict(
    request: Request,
    conflict_id: str,
    prefetch: bool = False,
    allow_roles: Sequence[str] | None = None,
) -> tuple[ConflictResolution, SearchSession, None] | tuple[None, None, Response]:
    """Validate access to a conflict via its parent session.

    When *prefetch* is ``True`` the query eagerly loads related decisions,
    comments, and revote proposals (for detail endpoints).

    *allow_roles* opts the endpoint into org-role oversight access (see
    ``_has_session_access``).

    Returns ``(conflict, session, None)`` on success or
    ``(None, None, error_response)`` on failure.
    """
    qs = ConflictResolution.objects.select_related(
        "result",
        "result__session",
    )
    if prefetch:
        qs = qs.prefetch_related(
            "conflicting_decisions__reviewer",
            "conflicting_decisions__assignment",
            "comments__author",
            "comments__replies__author",
            "revote_proposals__proposed_by",
            "revote_proposals__accepted_by",
        ).select_related("resolved_by", "final_decision")

    try:
        conflict = qs.get(id=conflict_id)
    except ConflictResolution.DoesNotExist:
        return (
            None,
            None,
            Response(
                {"error": "not_found", "message": "Conflict not found"},
                status=status.HTTP_404_NOT_FOUND,
            ),
        )

    session = conflict.result.session
    if not _has_session_access(request, session, allow_roles):
        return (
            None,
            None,
            Response(
                {"error": "not_found", "message": "Conflict not found"},
                status=status.HTTP_404_NOT_FOUND,
            ),
        )

    return conflict, session, None


def is_conflicting_reviewer(user, conflict: ConflictResolution) -> bool:
    """Check if user is one of the conflicting reviewers on this conflict."""
    reviewer_ids = conflict.conflicting_decisions.values_list("reviewer_id", flat=True)
    return user.id in reviewer_ids
