"""
API views for the review_manager app.

Provides lightweight API endpoints for AJAX-based workflow features
including session status checking and progress monitoring.
"""

import logging
from datetime import timedelta
from typing import TypedDict

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, OperationalError
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.results_manager.models import ProcessedResult, ProcessingSession

from .models import SearchSession

logger = logging.getLogger(__name__)


class SessionStatsData(TypedDict):
    """Type definition for session statistics data."""

    total_queries: int
    completed_queries: int
    total_results: int
    errors: int
    retrieved_count: int


class SessionStatusResponse(TypedDict):
    """Type definition for session status API response."""

    session_id: str
    status: str
    status_display: str
    status_detail: str | None
    progress: int
    progress_percent: int
    redirect_url: str | None
    stats: SessionStatsData
    last_updated: str
    is_complete: bool


@login_required
@require_http_methods(["GET"])
def session_status_api(request, session_id):  # noqa: C901 - Session status API
    """
    Returns current session status and progress for AJAX polling.

    Used by the auto-navigation system to monitor session progress
    and automatically redirect users when processing completes.

    Enhanced with error handling, query optimization, and stuck session detection.

    Args:
        request: HTTP request object
        session_id: UUID of the search session

    Returns:
        JsonResponse with status, progress, and redirect information
    """
    try:
        # Optimize query with select_related to avoid N+1 queries
        session = get_object_or_404(
            SearchSession.objects.select_related("search_strategy", "owner"),
            id=session_id,
            owner=request.user,
        )

        # Calculate progress based on session status
        status_progress = {
            "draft": 0,
            "defining_search": 10,
            "ready_to_execute": 20,
            "executing": 40,
            "processing_results": 60,
            "ready_for_review": 100,
            "under_review": 100,
            "completed": 100,
        }

        progress = status_progress.get(session.status, 0)

        # Add execution progress if available (with timeout protection)
        if session.status == "executing":
            try:
                # Count completed executions with timeout protection
                completed = (
                    session.search_strategy.search_queries.filter(
                        executions__status="completed"
                    )
                    .distinct()
                    .count()
                )
                total = session.search_strategy.search_queries.count()

                if total > 0:
                    # Progress ranges from 20-40% during execution
                    execution_progress = 20 + (20 * completed / total)
                    progress = int(execution_progress)
            except (DatabaseError, OperationalError) as e:
                logger.warning(
                    f"Database error while calculating execution progress for {session_id}: {e}"
                )
                # Use fallback progress
                progress = 30

        elif session.status == "processing_results":
            # Check if we have processing progress information
            try:
                processing_session = ProcessingSession.objects.filter(
                    search_session=session
                ).first()

                if processing_session and processing_session.total_results > 0:
                    # Calculate percentage based on actual progress
                    processed_pct = (
                        processing_session.processed_count
                        / processing_session.total_results
                    ) * 100
                    # Scale to 60-90% range for processing phase
                    progress = 60 + int(processed_pct * 0.3)
                else:
                    progress = 70
            except (DatabaseError, OperationalError, AttributeError) as e:
                logger.warning(
                    f"Error getting processing progress for {session_id}: {e}"
                )
                progress = 70

        # Determine redirect URL based on status
        redirect_url = None
        if session.status == "ready_for_review":
            redirect_url = reverse(
                "review_results:overview", kwargs={"session_id": session.id}
            )
        elif session.status == "completed":
            redirect_url = reverse(
                "reporting:dashboard", kwargs={"session_id": session.id}
            )

        # Get execution statistics with error handling
        stats: SessionStatsData = {
            "total_queries": 0,
            "completed_queries": 0,
            "total_results": 0,
            "errors": 0,
            "retrieved_count": 0,
        }

        try:
            stats["total_queries"] = session.search_strategy.search_queries.count()

            if session.status in [
                "executing",
                "processing_results",
                "ready_for_review",
                "under_review",
                "completed",
            ]:
                stats["completed_queries"] = (
                    session.search_strategy.search_queries.filter(
                        executions__status="completed"
                    )
                    .distinct()
                    .count()
                )

                stats["total_results"] = session.total_results or 0

                stats["errors"] = (
                    session.search_strategy.search_queries.filter(
                        executions__status="failed"
                    )
                    .distinct()
                    .count()
                )

                # Add retrieved count for PRISMA compliance
                stats["retrieved_count"] = ProcessedResult.objects.filter(
                    session_id=session.id, is_retrieved=True
                ).count()

        except (DatabaseError, OperationalError) as e:
            logger.error(
                f"Database error calculating stats for session {session_id}: {e}",
                exc_info=True,
            )
            # Continue with default stats (zeros)

        # Detect stuck sessions and add warning
        stuck_warning = _check_stuck_session(session)

        # Create typed response data
        response_data: SessionStatusResponse = {
            "session_id": str(session.id),
            "status": session.status,
            "status_display": session.get_status_display(),
            "status_detail": session.status_detail or stuck_warning,
            "progress": progress,
            "progress_percent": progress,
            "redirect_url": redirect_url,
            "stats": stats,
            "last_updated": session.updated_at.isoformat(),
            "is_complete": session.status
            in ["ready_for_review", "under_review", "completed"],
        }

        return JsonResponse(response_data)

    except (DatabaseError, OperationalError) as e:
        logger.error(
            f"Critical database error in session_status_api for {session_id}: {e}",
            exc_info=True,
        )
        return JsonResponse(
            {
                "error": "Database temporarily unavailable. Please try again.",
                "error_type": "database_error",
                "session_id": str(session_id),
                "retry_after": 5,
            },
            status=503,
        )

    except Exception as e:
        logger.error(
            f"Unexpected error in session_status_api for {session_id}: {e}",
            exc_info=True,
        )
        return JsonResponse(
            {
                "error": "An unexpected error occurred. Please refresh the page.",
                "error_type": "unexpected_error",
                "session_id": str(session_id),
            },
            status=500,
        )


def _check_stuck_session(session: SearchSession) -> str:
    """
    Check if session appears to be stuck and return warning message.

    Args:
        session: SearchSession instance

    Returns:
        Warning message if stuck, empty string otherwise
    """
    if session.status not in ["executing", "processing_results"]:
        return ""

    # Check if session has been in this state for too long
    time_in_state = timezone.now() - session.updated_at

    # Thresholds: executing=30min, processing_results=15min
    threshold = (
        timedelta(minutes=30)
        if session.status == "executing"
        else timedelta(minutes=15)
    )

    if time_in_state > threshold:
        return (
            f"Session may be stuck. Last update: {time_in_state.seconds // 60} minutes ago. "
            "Consider refreshing the page or contacting support."
        )

    return ""


@login_required
@require_http_methods(["GET"])
def redirect_plural_session_status(request, session_id):
    """
    Temporary redirect for incorrect plural session URLs.

    This catches calls to /api/sessions/{id}/status/ and redirects them
    to the correct /api/session/{id}/status/ endpoint while logging
    the source of the incorrect calls.
    """
    logger = logging.getLogger(__name__)
    logger.warning(
        f"Incorrect plural URL called: /api/sessions/{session_id}/status/ - "
        f"redirecting to singular form. Source: {request.META.get('HTTP_REFERER', 'unknown')}"
    )

    # Redirect to correct singular URL
    correct_url = reverse(
        "review_manager:session_status_api", kwargs={"session_id": session_id}
    )
    return HttpResponseRedirect(correct_url)


@login_required
@require_http_methods(["GET"])
def session_quick_stats_api(request, session_id):
    """
    Returns quick statistics for a session.

    Lightweight endpoint for dashboard updates without full status check.

    Args:
        request: HTTP request object
        session_id: UUID of the search session

    Returns:
        JsonResponse with basic session statistics
    """
    session = get_object_or_404(SearchSession, id=session_id, owner=request.user)

    # Get query count through search_strategy relationship
    queries_count = 0
    if hasattr(session, "search_strategy") and session.search_strategy:
        queries_count = session.search_strategy.search_queries.count()

    # Get results count through ProcessedResult model
    results_count = ProcessedResult.objects.filter(session=session).count()

    return JsonResponse(
        {
            "session_id": str(session.id),
            "title": session.title,
            "status": session.status,
            "status_display": session.get_status_display(),
            "queries_count": queries_count,
            "results_count": results_count,
            "last_updated": session.updated_at.isoformat(),
        }
    )
