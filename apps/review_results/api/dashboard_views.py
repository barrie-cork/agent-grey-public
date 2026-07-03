"""
Dashboard API Views.

Provides 3 endpoints:
1. GET /api/dashboard/stats/ - Team metrics and progress
2. GET /api/dashboard/irr/ - Inter-rater reliability metrics
3. GET /api/dashboard/progress/ - Reviewer progress breakdown
"""

from datetime import timedelta
from typing import cast

from django.core.cache import cache
from django.db.models import Avg, Count, F, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import Permissions
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.api.utils import get_validated_session
from apps.review_results.models import (
    ConflictResolution,
    ReviewerAssignment,
    ReviewerDecision,
)
from apps.review_results.serializers import InterRaterReliabilitySerializer
from apps.review_results.services.irr_service import InterRaterReliabilityService


# Org roles that grant oversight access to dashboard/IRR endpoints without a
# per-session invitation (GH #230). Mirrors _has_dashboard_access.
_DASHBOARD_ROLES = (Permissions.REVIEW_CREATE, Permissions.CONFLICT_VIEW)


def _has_dashboard_access(user, organisation) -> bool:
    """Check if user has lead reviewer or above access for dashboard endpoints."""
    return user.has_perm(Permissions.REVIEW_CREATE, organisation) or user.has_perm(
        Permissions.CONFLICT_VIEW, organisation
    )


def _clean_pct(value: float, decimals: int = 1) -> int | float:
    """Round a percentage and strip trailing .0 (e.g. 0.0 -> 0, 25.5 -> 25.5)."""
    result = round(value, decimals)
    return int(result) if result == int(result) else result


def _format_time_ago(dt) -> str:
    """Format a datetime as a human-readable relative time string."""
    if not dt:
        return "Never"
    delta = timezone.now() - dt
    seconds = delta.total_seconds()
    if seconds < 300:
        return "Just now"
    elif seconds < 3600:
        return f"{int(seconds / 60)} minutes ago"
    elif seconds < 86400:
        return f"{int(seconds / 3600)} hours ago"
    return f"{int(seconds / 86400)} days ago"


def _get_overview_stats(session: SearchSession) -> dict:
    """Compute overview statistics for a session (counts, conflicts)."""
    total_results = ProcessedResult.objects.filter(session=session).count()
    reviewed_results = ProcessedResult.objects.filter(
        session=session, reviewers_completed__gte=F("min_reviewers_required")
    ).count()

    decisions = ReviewerDecision.objects.filter(result__session=session).exclude(
        decision="ABSTAIN"
    )

    conflict_qs = ConflictResolution.objects.filter(result__session=session)
    total_conflicts = conflict_qs.count()
    resolved_conflicts = conflict_qs.filter(status="RESOLVED").count()

    return {
        "total_results": total_results,
        "reviewed": reviewed_results,
        "pending": total_results - reviewed_results,
        "included": decisions.filter(decision="INCLUDE").count(),
        "excluded": decisions.filter(decision="EXCLUDE").count(),
        "conflicts": total_conflicts,
        "conflicts_resolved": resolved_conflicts,
        "pending_conflicts": total_conflicts - resolved_conflicts,
    }


def _get_team_performance(session: SearchSession) -> dict:
    """Compute team performance metrics (reviewers, velocity, avg time, conflict rate)."""
    decisions = ReviewerDecision.objects.filter(result__session=session)
    now = timezone.now()

    active_reviewers = decisions.order_by().values("reviewer").distinct().count()

    reviews_today = decisions.filter(
        decided_at__gte=now.replace(hour=0, minute=0, second=0),
    ).count()

    reviews_this_week = decisions.filter(
        decided_at__gte=now - timedelta(days=7),
    ).count()

    avg_time = (
        decisions.exclude(decision="ABSTAIN")
        .filter(time_spent_seconds__isnull=False)
        .aggregate(avg=Avg("time_spent_seconds"))["avg"]
        or 0
    )

    total_results = ProcessedResult.objects.filter(session=session).count()
    reviewed_results = ProcessedResult.objects.filter(
        session=session, reviewers_completed__gte=F("min_reviewers_required")
    ).count()
    total_conflicts = ConflictResolution.objects.filter(result__session=session).count()
    conflict_rate = (
        (total_conflicts / reviewed_results * 100) if reviewed_results > 0 else 0
    )
    progress_pct = (reviewed_results / total_results * 100) if total_results > 0 else 0

    return {
        "active_reviewers": active_reviewers,
        "reviews_today": reviews_today,
        "reviews_this_week": reviews_this_week,
        "average_time_per_review_seconds": int(avg_time),
        "conflict_rate_percentage": _clean_pct(conflict_rate, 2),
        "_progress_percentage": progress_pct,
    }


def _get_reviewer_breakdown(session: SearchSession, request_user) -> list[dict]:
    """
    Build per-reviewer stats using annotated queries (avoids N+1).

    Fetches all reviewer users in a single query, then uses annotated aggregations
    per reviewer to minimise database round-trips.
    """
    from apps.review_results.services.blinding_service import BlindingService

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0)
    is_blinded = BlindingService.should_blind(session)

    # Single query: all reviewers with aggregated stats
    reviewer_users = (
        User.objects.filter(
            review_decisions__result__session=session,
        )
        .distinct()
        .annotate(
            total_reviews=Count(
                "review_decisions",
                filter=Q(review_decisions__result__session=session),
            ),
            reviews_today_count=Count(
                "review_decisions",
                filter=Q(
                    review_decisions__result__session=session,
                    review_decisions__decided_at__gte=today_start,
                ),
            ),
            avg_time_reviewer=Avg(
                "review_decisions__time_spent_seconds",
                filter=Q(
                    review_decisions__result__session=session,
                    review_decisions__time_spent_seconds__isnull=False,
                ),
            ),
            include_count=Count(
                "review_decisions",
                filter=Q(
                    review_decisions__result__session=session,
                    review_decisions__decision="INCLUDE",
                ),
            ),
        )
    )

    result = []
    for idx, reviewer in enumerate(reviewer_users, start=1):
        total = reviewer.total_reviews
        inclusion_rate = (reviewer.include_count / total * 100) if total > 0 else 0

        has_active = ReviewerAssignment.objects.filter(
            result__session=session, reviewer=reviewer, is_active=True
        ).exists()

        last_decision = (
            ReviewerDecision.objects.filter(result__session=session, reviewer=reviewer)
            .order_by("-decided_at")
            .values_list("decided_at", flat=True)
            .first()
        )

        if is_blinded and reviewer != request_user:
            reviewer_info = {
                "id": "blinded",
                "username": f"Reviewer {idx}",
                "email": "blinded@reviewer.local",
            }
        else:
            reviewer_info = {
                "id": str(reviewer.id),
                "username": reviewer.username,
                "email": reviewer.email,
            }

        result.append(
            {
                "reviewer": reviewer_info,
                "total_reviews": total,
                "reviews_today": reviewer.reviews_today_count,
                "average_time_seconds": int(reviewer.avg_time_reviewer or 0),
                "inclusion_rate_percentage": _clean_pct(inclusion_rate),
                "current_status": "active" if has_active else "idle",
                "last_activity": _format_time_ago(last_decision),
            }
        )

    return result


# ============================================================================
# TEAM STATS
# ============================================================================


@extend_schema(
    parameters=[
        OpenApiParameter(
            "session_id", str, description="Session ID (required)", required=True
        ),
        OpenApiParameter(
            "period",
            str,
            description="Time period (today, week, month, all)",
            required=False,
        ),
    ],
    responses={200: OpenApiResponse(description="Team statistics")},
    summary="Get team dashboard stats",
    description="Get comprehensive team metrics including progress, IRR, and reviewer performance.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_team_stats(request: Request) -> Response:
    """Get team dashboard statistics for a session."""
    session, error = get_validated_session(request, allow_roles=_DASHBOARD_ROLES)
    if error:
        return error
    session = cast(SearchSession, session)

    if not _has_dashboard_access(request.user, session.organisation):
        return Response(
            {
                "error": "permission_denied",
                "message": "Dashboard access requires lead reviewer role or above",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # Check cache
    period = request.query_params.get("period", "all")
    cache_key = f"team_stats_{session.id}_{period}"
    cached_stats = cache.get(cache_key)
    if cached_stats:
        return Response(cached_stats, status=status.HTTP_200_OK)

    overview = _get_overview_stats(session)
    performance = _get_team_performance(session)
    reviewer_breakdown = _get_reviewer_breakdown(session, request.user)

    irr_service = InterRaterReliabilityService()
    irr_summary = irr_service.get_irr_summary(session.organisation, session)

    stats = {
        "session": {
            "id": str(session.id),
            "title": session.title,
            "status": session.status,
        },
        "overview": overview,
        "progress": {
            "percentage_complete": _clean_pct(performance.pop("_progress_percentage")),
        },
        "team_performance": performance,
        "inter_rater_reliability": irr_summary,
        "reviewer_breakdown": reviewer_breakdown,
    }

    cache.set(cache_key, stats, 300)
    return Response(stats, status=status.HTTP_200_OK)


# ============================================================================
# IRR METRICS
# ============================================================================


@extend_schema(
    parameters=[
        OpenApiParameter(
            "session_id", str, description="Session ID (required)", required=True
        ),
    ],
    responses={200: InterRaterReliabilitySerializer(many=True)},
    summary="Get IRR metrics",
    description="Get inter-rater reliability metrics for a session including Cohen's Kappa for all reviewer pairs.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_irr_metrics(request: Request) -> Response:
    """Get inter-rater reliability metrics."""
    session, error = get_validated_session(request, allow_roles=_DASHBOARD_ROLES)
    if error:
        return error
    session = cast(SearchSession, session)

    if not _has_dashboard_access(request.user, session.organisation):
        return Response(
            {
                "error": "permission_denied",
                "message": "Dashboard access requires lead reviewer role or above",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    irr_service = InterRaterReliabilityService()
    metrics = irr_service.get_irr_metrics(session.organisation, session)

    serializer = InterRaterReliabilitySerializer(metrics, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ============================================================================
# REVIEWER PROGRESS
# ============================================================================


@extend_schema(
    parameters=[
        OpenApiParameter(
            "session_id", str, description="Session ID (required)", required=True
        ),
    ],
    responses={200: OpenApiResponse(description="Reviewer progress breakdown")},
    summary="Get reviewer progress",
    description="Get detailed progress breakdown for all reviewers in a session.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_reviewer_progress(request: Request) -> Response:
    """Get detailed progress breakdown for each reviewer."""
    session, error = get_validated_session(request, allow_roles=_DASHBOARD_ROLES)
    if error:
        return error
    session = cast(SearchSession, session)

    if not _has_dashboard_access(request.user, session.organisation):
        return Response(
            {
                "error": "permission_denied",
                "message": "Dashboard access requires lead reviewer role or above",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # Single query: all reviewers with annotated decision breakdowns
    reviewer_users = (
        User.objects.filter(
            review_decisions__result__session=session,
        )
        .distinct()
        .annotate(
            total_decisions=Count(
                "review_decisions",
                filter=Q(review_decisions__result__session=session),
            ),
            include_count=Count(
                "review_decisions",
                filter=Q(
                    review_decisions__result__session=session,
                    review_decisions__decision="INCLUDE",
                ),
            ),
            exclude_count=Count(
                "review_decisions",
                filter=Q(
                    review_decisions__result__session=session,
                    review_decisions__decision="EXCLUDE",
                ),
            ),
            maybe_count=Count(
                "review_decisions",
                filter=Q(
                    review_decisions__result__session=session,
                    review_decisions__decision="MAYBE",
                ),
            ),
        )
    )

    progress_data = []
    for reviewer in reviewer_users:
        active_assignments = ReviewerAssignment.objects.filter(
            result__session=session, reviewer=reviewer, is_active=True
        ).count()

        conflicts_count = (
            ConflictResolution.objects.filter(
                result__session=session, conflicting_decisions__reviewer=reviewer
            )
            .distinct()
            .count()
        )

        progress_data.append(
            {
                "reviewer": {
                    "id": str(reviewer.id),
                    "username": reviewer.username,
                    "email": reviewer.email,
                },
                "total_decisions": reviewer.total_decisions,
                "decisions_breakdown": {
                    "include": reviewer.include_count,
                    "exclude": reviewer.exclude_count,
                    "maybe": reviewer.maybe_count,
                },
                "active_assignments": active_assignments,
                "conflicts_involved": conflicts_count,
            }
        )

    return Response(
        {
            "session": {
                "id": str(session.id),
                "title": session.title,
            },
            "reviewers": progress_data,
        },
        status=status.HTTP_200_OK,
    )


# ============================================================================
# SESSION IRR METRICS (Alternative route pattern)
# ============================================================================


@extend_schema(
    parameters=[
        OpenApiParameter(
            "session_id",
            str,
            description="Session ID (UUID)",
            required=True,
            location="path",
        ),
    ],
    responses={200: InterRaterReliabilitySerializer(many=True)},
    summary="Get session IRR metrics (alternative route)",
    description="Get inter-rater reliability metrics for a specific session. Alternative route pattern matching /api/sessions/{uuid}/irr-metrics/.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_session_irr_metrics(request: Request, session_id: str) -> Response:
    """Get inter-rater reliability metrics for a session (alternative route)."""
    session, error = get_validated_session(
        request, session_id=session_id, allow_roles=_DASHBOARD_ROLES
    )
    if error:
        return error
    session = cast(SearchSession, session)

    irr_service = InterRaterReliabilityService()
    irr_summary = irr_service.get_irr_summary(session.organisation, session)

    is_session_owner = request.user == session.owner
    response_data = {
        "session_wide_metrics": irr_summary,
        "is_session_owner": is_session_owner,
    }

    include_breakdown = request.query_params.get("include_breakdown")
    if include_breakdown == "true":
        if not is_session_owner:
            return Response(
                {"error": "per_reviewer_breakdown_forbidden"},
                status=status.HTTP_403_FORBIDDEN,
            )
        response_data["per_reviewer_breakdown"] = (
            irr_service.get_per_reviewer_breakdown(session.organisation, session)
        )

    return Response(response_data, status=status.HTTP_200_OK)


@extend_schema(
    parameters=[
        OpenApiParameter(
            "session_id",
            str,
            description="Session ID (UUID)",
            required=True,
            location="path",
        ),
    ],
    responses={202: OpenApiResponse(description="IRR calculation triggered")},
    summary="Trigger IRR calculation for session",
    description="Triggers background IRR calculation for all reviewer pairs in a session.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def trigger_session_irr_calculation(request: Request, session_id: str) -> Response:
    """Trigger IRR calculation for a session (async via Celery)."""
    session, error = get_validated_session(
        request, session_id=session_id, allow_roles=_DASHBOARD_ROLES
    )
    if error:
        return error
    session = cast(SearchSession, session)

    from apps.review_results.tasks import calculate_session_irr_task

    calculate_session_irr_task.delay(session_id=str(session.id))

    return Response(
        {"status": "calculating", "message": "IRR calculation triggered."},
        status=status.HTTP_202_ACCEPTED,
    )
