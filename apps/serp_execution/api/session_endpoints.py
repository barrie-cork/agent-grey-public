"""
Session management and progress tracking API endpoints.
Contains functions for session status, progress monitoring, and execution statistics.
"""

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.utils.error_responses import (
    error_response,
    not_found_response,
    permission_denied_response,
)

from ..api_types import (
    ExecutionStatsResponse,
    QueryProgressResponse,
    SessionExecutionDataResponse,
    SessionProgressResponse,
    SessionQuickStatusResponse,
)
from ..services.api_service import SessionAPIService

logger = logging.getLogger(__name__)


def get_session_executions_data(
    session_id: str, include_failed: bool = False
) -> SessionExecutionDataResponse:
    """
    Get execution data for a session.

    Args:
        session_id: Session UUID string
        include_failed: Include failed executions in results

    Returns:
        SessionExecutionDataResponse: Execution data response
    """
    from ..models import SearchExecution

    # Query executions
    executions = SearchExecution.objects.filter(query__session_id=session_id)

    if not include_failed:
        executions = executions.exclude(status="failed")

    # Build execution data list
    execution_data = []
    for execution in executions:
        execution_data.append(
            {
                "id": str(execution.id),
                "query_id": str(execution.query.id),
                "status": execution.status,
                "results_count": execution.results_count,
                "execution_time": execution.duration_seconds,
                "started_at": (
                    execution.started_at.isoformat() if execution.started_at else None
                ),
                "completed_at": (
                    execution.completed_at.isoformat()
                    if execution.completed_at
                    else None
                ),
            }
        )

    # Calculate counts for response
    total_count = executions.count()
    completed_count = executions.filter(status="completed").count()
    failed_count = executions.filter(status="failed").count()
    pending_count = executions.filter(
        status__in=["pending", "running", "retrying"]
    ).count()

    # Build response
    response_data: SessionExecutionDataResponse = {
        "executions": execution_data,
        "total_count": total_count,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "pending_count": pending_count,
    }

    return response_data


def get_session_execution_stats(
    session_id: str, date_from: str | None = None, date_to: str | None = None
) -> ExecutionStatsResponse:
    """
    Get execution statistics for a session.

    Args:
        session_id: Session UUID string
        date_from: Optional start date filter (ISO format)
        date_to: Optional end date filter (ISO format)

    Returns:
        ExecutionStatsResponse: Execution statistics response
    """
    from datetime import datetime

    from django.db.models import Avg, Sum

    from ..models import SearchExecution

    # Query executions
    executions = SearchExecution.objects.filter(query__session_id=session_id)

    # Apply date filters if provided
    if date_from:
        try:
            from_date = datetime.fromisoformat(date_from)
            executions = executions.filter(created_at__gte=from_date)
        except ValueError:
            pass  # Skip invalid date format

    if date_to:
        try:
            to_date = datetime.fromisoformat(date_to)
            executions = executions.filter(created_at__lte=to_date)
        except ValueError:
            pass  # Skip invalid date format

    # Calculate statistics - use separate queries for reliability
    total_executions = executions.count()
    successful_executions = executions.filter(status="completed").count()
    failed_executions = executions.filter(status="failed").count()

    stats = executions.aggregate(
        avg_duration=Avg("duration_seconds"), total_results=Sum("results_count")
    )

    # Build response
    response_data: ExecutionStatsResponse = {
        "total_executions": total_executions,
        "successful_executions": successful_executions,
        "failed_executions": failed_executions,
        "average_duration": float(stats["avg_duration"] or 0),
        "total_results": stats["total_results"] or 0,
    }

    return response_data


@login_required
@require_http_methods(["GET"])
def session_progress_api(request, session_id) -> JsonResponse:
    """Get session status directly from database."""
    try:
        # Get session with permission check
        from apps.review_manager.models import SearchSession

        try:
            session = SearchSession.objects.get(id=session_id, owner=request.user)
        except SearchSession.DoesNotExist:
            return JsonResponse(
                {"error": "Session not found or access denied"}, status=404
            )

        # Return typed response
        response_data: SessionProgressResponse = {
            "session_id": str(session_id),
            "session_status": session.status,
            "status": session.status,
            "current_step": session.status_detail or session.status,
            "component": "session_monitor",
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error getting session status: {str(e)}")
        return error_response(e, status_code=500)


@staff_member_required
def session_diagnostic_api(request, session_id) -> JsonResponse:
    """
    Diagnostic endpoint for debugging session workflow issues.
    Only accessible to staff members.
    """
    from ..dependencies import get_session_provider
    from ..models import SearchExecution

    # Basic validation
    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)

    session_provider = get_session_provider()

    try:
        # Get session and diagnostic data
        session = session_provider.get_session(session_id)
        if session is None:
            return not_found_response("session", session_id)
        session_data = session_provider.get_session_for_diagnostic(session_id)

        # Use diagnostic data from provider
        diagnostics = {
            "session": session_data,
            "executions": {
                "total": SearchExecution.objects.filter(query__session=session).count(),
                "completed": SearchExecution.objects.filter(
                    query__session=session, status="completed"
                ).count(),
                "failed": SearchExecution.objects.filter(
                    query__session=session, status="failed"
                ).count(),
            },
            "results": {
                "total": session.processed_results.count(),
                "unique": session.processed_results.filter(is_duplicate=False).count(),
            },
            "timing": {
                "time_in_current_state": (
                    timezone.now() - session.updated_at
                ).total_seconds(),
            },
            "health_checks": {
                "has_owner": bool(session.owner),
                "has_strategy": hasattr(session, "search_strategy"),
                "has_queries": session.search_queries_denorm.exists(),
                "celery_task_id": getattr(session, "celery_task_id", None),
            },
        }

        # Add warnings for common issues
        warnings = []

        if diagnostics["timing"]["time_in_current_state"] > 1800:  # 30 minutes
            warnings.append(f"Session stuck in {session.status} for over 30 minutes")

        if session.status == "executing" and diagnostics["executions"]["total"] == 0:
            warnings.append("Session in 'executing' but no executions found")

        if (
            session.status == "ready_to_execute"
            and not session.search_queries_denorm.filter(is_active=True).exists()
        ):
            warnings.append("Session ready to execute but no active queries")

        diagnostics["warnings"] = warnings

        # Return diagnostics without Pydantic validation
        return JsonResponse(diagnostics, json_dumps_params={"indent": 2})

    except Exception as e:
        if "DoesNotExist" in str(type(e)):
            return not_found_response("session", session_id)
        return error_response(e, status_code=500)


@login_required
@require_http_methods(["POST"])
def cancel_session_api(request, session_id) -> JsonResponse:
    """
    Cancel all running executions for a session via AJAX.

    Cancels all pending or running executions for the specified session,
    providing immediate feedback for user-initiated cancellation.
    """
    from ..dependencies import get_session_provider

    service = SessionAPIService()
    session_provider = get_session_provider()

    try:
        response_data = service.cancel_session_executions(
            session_id, request.user, session_provider
        )
        return JsonResponse(response_data)
    except Exception as e:
        if hasattr(e, "status_code") and e.status_code == 404:  # type: ignore[attr-defined]
            return not_found_response("session", session_id)
        elif isinstance(e, PermissionError):
            return permission_denied_response("cancel executions", "session")
        else:
            logger.error(f"Error cancelling session executions: {str(e)}")
            return error_response(e, status_code=500)


def _calculate_query_statistics(session, executions):
    """
    Calculate query execution statistics for a session.

    Extracted helper function to reduce complexity of session_quick_status_api.
    Computes current query details, recent queries, and progress metrics.

    Args:
        session: SearchSession instance
        executions: QuerySet of SearchExecution objects

    Returns:
        tuple: (current_query_data, recent_queries, progress_percentage)
            - current_query_data: Dict with currently executing query details or None
            - recent_queries: List of recently completed queries with pagination info
            - progress_percentage: Float representing completion percentage
    """
    # Get total queries from strategy (more reliable during execution)
    if hasattr(session, "search_strategy"):
        total_queries = session.search_strategy.search_queries.count()
    else:
        total_queries = 0

    completed_queries = executions.filter(status="completed").count()

    # Calculate progress percentage
    progress_percentage = 0.0
    if total_queries:
        progress_percentage = (completed_queries / total_queries) * 100

    # Get current query details if executing
    current_query_data = None
    if session.status in ["executing", "processing_results"]:
        current_execution = (
            executions.filter(status="running").order_by("started_at").first()
        )

        if current_execution:
            step_meta = current_execution.step_metadata or {}
            pagination_info = step_meta.get("pagination", {}) or {}

            total_pages = (
                pagination_info.get("max_pages")
                or pagination_info.get("pages_target")
                or pagination_info.get("total_pages")
                or pagination_info.get("configured_pages")
                or pagination_info.get("allowed_pages")
            )

            current_query_data = {
                "execution_id": str(current_execution.id),
                "query_text": current_execution.query.query_text,
                "status": current_execution.status,
                "current_page": pagination_info.get("pages_fetched")
                or pagination_info.get("current_page"),
                "total_pages": total_pages,
                "results_so_far": current_execution.api_result_count
                or current_execution.results_count,
                "stopped_reason": pagination_info.get("stopped_reason"),
            }

    # Get recent completed queries
    recent_queries = []
    if session.status in ["executing", "processing_results"]:
        recent_executions = executions.filter(status="completed").order_by(
            "-completed_at", "-updated_at"
        )[:3]

        for execution in recent_executions:
            step_meta = execution.step_metadata or {}
            pagination_info = step_meta.get("pagination", {}) or {}

            recent_queries.append(
                {
                    "query_text": execution.query.query_text,
                    "results_count": execution.api_result_count
                    or execution.results_count,
                    "pages_fetched": pagination_info.get("pages_fetched"),
                    "stopped_reason": pagination_info.get("stopped_reason"),
                    "completed_at": (
                        execution.completed_at.isoformat()
                        if execution.completed_at
                        else None
                    ),
                }
            )

    return (
        current_query_data,
        recent_queries,
        progress_percentage,
        total_queries,
        completed_queries,
    )


@login_required
@require_http_methods(["GET"])
def session_quick_status_api(request, session_id) -> JsonResponse:
    """
    Get quick session status for polling fallback.

    Lightweight endpoint that returns just the essential status information
    for polling when SSE connection fails. Used by SessionMonitor JavaScript.

    Args:
        request: The HTTP request object
        session_id: UUID string identifying the search session

    Returns:
        JsonResponse: Quick status with state and progress
    """
    from django.db.models import Sum
    from django.db.models.functions import Coalesce
    from django.urls import reverse

    from apps.review_manager.models import SearchSession

    try:
        session = SearchSession.objects.get(id=session_id, owner=request.user)
    except SearchSession.DoesNotExist:
        return JsonResponse({"error": "Session not found"}, status=404)

    from ..models import SearchExecution

    try:
        session.refresh_from_db()

        # Get executions with related data
        executions = SearchExecution.objects.filter(
            query__session=session
        ).select_related("query")

        # Calculate query statistics and progress using helper function
        (
            current_query_data,
            recent_queries,
            progress_percentage,
            total_queries,
            completed_queries,
        ) = _calculate_query_statistics(session, executions)

        # Calculate aggregate counts for response
        running_queries = executions.filter(status="running").count()
        failed_queries = executions.filter(status="failed").count()

        totals = executions.aggregate(
            total_raw_results=Coalesce(Sum("api_result_count"), 0)
        )
        total_raw_results = int(totals["total_raw_results"] or 0)

        response: SessionQuickStatusResponse = {
            "session_id": str(session.id),
            "status": session.status,
            "session_status_display": session.get_status_display(),
            "status_detail": session.status_detail,
            "current_step": session.status_detail or session.status,
            "processed_count": completed_queries,
            "total_count": total_queries,
            "total_queries": total_queries,
            "completed_queries": completed_queries,
            "progress_percentage": progress_percentage,
            "total_raw_results": total_raw_results,
            "query_stats": {
                "total_queries": total_queries,
                "completed_queries": completed_queries,
                "running_queries": running_queries,
                "failed_queries": failed_queries,
            },
            "metadata": {},
            "current_query": current_query_data,  # pyright: ignore[reportAssignmentType]
            "recent_queries": recent_queries,
            "timestamp": timezone.now().isoformat(),
        }

        if session.status == "ready_for_review":
            response["metadata"]["review_url"] = reverse(  # type: ignore[index]
                "review_results:overview", kwargs={"session_id": session_id}
            )

        return JsonResponse(response)

    except Exception as exc:
        logger.error("Error fetching quick status: %s", exc, exc_info=True)
        return JsonResponse({"error": "Failed to fetch status"}, status=500)


@login_required
@require_http_methods(["GET"])
def session_query_progress_api(request, session_id) -> JsonResponse:
    """
    Get detailed query-level progress for a session via AJAX.

    Returns progress information for each query in the session including:
    - Individual query status and progress percentage
    - Current step and processing phase
    - Results count and error messages
    - Real-time execution tracking

    Used by frontend JavaScript for granular progress monitoring during execution.
    """
    from ..models import SearchExecution

    # Basic validation - ensure session_id is provided
    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)

    from ..dependencies import get_session_provider

    session_provider = get_session_provider()

    try:
        # Convert session_id to string for all operations
        session_id_str = str(session_id)

        # Check if session exists
        if not session_provider.session_exists(session_id_str):
            return JsonResponse({"error": "Session not found"}, status=404)

        # Verify session ownership
        if not session_provider.verify_session_ownership(session_id_str, request.user):
            return JsonResponse({"error": "Permission denied"}, status=403)

        # Get all executions for this session with related data
        executions = (
            SearchExecution.objects.filter(query__session_id=session_id_str)
            .select_related("query")
            .order_by("query__created_at")
        )

        # Build query progress data
        query_progress = []
        total_queries = executions.count()
        completed_queries = 0

        for execution in executions:
            # Track completed queries
            if execution.status == "completed":
                completed_queries += 1

            progress_entry = {
                "execution_id": str(execution.id),
                "query_id": str(execution.query.id),
                "query_text": execution.query.query_text,
                "status": execution.status,
                "current_step": execution.current_step,
                "processing_phase": execution.processing_phase,
                "results_count": execution.api_result_count or 0,
                "error_message": execution.error_message or "",
                "is_active": execution.status in ["pending", "running", "retrying"],
                "started_at": (
                    execution.started_at.isoformat() if execution.started_at else None
                ),
                "completed_at": (
                    execution.completed_at.isoformat()
                    if execution.completed_at
                    else None
                ),
                "duration_seconds": execution.duration_seconds,
            }
            query_progress.append(progress_entry)

        # Find currently executing query
        current_query = next(
            (q for q in query_progress if q["status"] == "running"), None
        )

        response_data: QueryProgressResponse = {
            "session_id": str(session_id),
            "session_status": session_provider.get_session_state(session_id),
            "total_queries": total_queries,
            "completed_queries": completed_queries,
            "current_query": current_query,
            "queries": query_progress,
            "timestamp": timezone.now().isoformat(),
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error getting query progress for session {session_id}: {str(e)}")
        return JsonResponse({"error": "Internal server error"}, status=500)
