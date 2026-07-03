"""
Views for the results_manager app.

NOTE: This app works entirely in the background via Celery tasks.
Web UI views have been archived to apps/results_manager/archive/

The processing pipeline runs automatically:
1. SERP execution completes
2. process_session_results_task is triggered automatically
3. Results are processed in the background
4. Session status updates to ready_for_review
5. Users access results via the review_results app
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.review_manager.models import SearchSession

from .api_types import FilteringStatsData, ProcessingStatusResponse
from .models import ProcessedResult, ProcessingSession

# This file intentionally left minimal as results_manager
# operates as a background service without web interface.
#
# For actual processing logic, see:
# - apps/results_manager/tasks/ - Celery background tasks
# - apps/results_manager/services/ - Business logic services
# - apps/results_manager/models.py - Data models with processing methods


def get_filtering_statistics(session_id) -> FilteringStatsData:
    """
    Get detailed filtering statistics for transparency (Issue #100).

    Args:
        session_id: UUID of the SearchSession

    Returns:
        Dictionary with filtering breakdown and transparency info
    """
    from apps.serp_execution.models import RawSearchResult

    # Get all processed results for this session
    processed_results = ProcessedResult.objects.filter(session__id=session_id)

    # Count by processing status
    status_counts = {
        "success": processed_results.filter(processing_status="success").count(),
        "filtered": processed_results.filter(processing_status="filtered").count(),
        "error": processed_results.filter(processing_status="error").count(),
    }

    # Get raw results count from SERP execution
    raw_results_count = RawSearchResult.objects.filter(
        execution__query__session_id=session_id
    ).count()

    # Calculate filtering breakdown
    total_processed = sum(status_counts.values())
    success_rate = (
        (status_counts["success"] / total_processed * 100) if total_processed > 0 else 0
    )
    filter_rate = (
        (status_counts["filtered"] / total_processed * 100)
        if total_processed > 0
        else 0
    )
    error_rate = (
        (status_counts["error"] / total_processed * 100) if total_processed > 0 else 0
    )

    # Get error categories for transparency
    error_categories = {}
    if status_counts["error"] > 0:
        error_results = processed_results.filter(processing_status="error")
        for result in error_results:
            category = result.processing_error_category or "unknown_error"
            error_categories[category] = error_categories.get(category, 0) + 1

    # Get filter reasons (mostly duplicates)
    filter_reasons = {}
    if status_counts["filtered"] > 0:
        filtered_results = processed_results.filter(processing_status="filtered")
        for result in filtered_results:
            reason = result.processing_error_category or "duplicate_result"
            filter_reasons[reason] = filter_reasons.get(reason, 0) + 1

    return {
        "raw_results_retrieved": raw_results_count,
        "total_processed_records": total_processed,
        "results_by_status": status_counts,
        "success_rate_percent": round(success_rate, 1),
        "filter_rate_percent": round(filter_rate, 1),
        "error_rate_percent": round(error_rate, 1),
        "filter_reasons": filter_reasons,
        "error_categories": error_categories,
        "accounting_check": {
            "raw_count": raw_results_count,
            "processed_count": total_processed,
            "difference": raw_results_count - total_processed,
            "is_complete": raw_results_count == total_processed,
        },
    }


class ProcessingStatusView(LoginRequiredMixin, TemplateView):
    """
    Display real-time processing status with detailed progress feedback.
    """

    template_name = "results_manager/processing_status.html"

    def get(self, request, *args, **kwargs):
        session_id = self.kwargs["session_id"]
        session = get_object_or_404(SearchSession, id=session_id, owner=request.user)

        # Ensure we have the latest session state
        session.refresh_from_db()

        # Check if session is completed with zero results
        if session.status == "completed" and session.total_results == 0:
            from apps.serp_execution.models import SearchExecution

            search_executions = (
                SearchExecution.objects.filter(query__session=session)
                .select_related("query")
                .order_by("created_at")
            )

            # Detect API failures: check if any executions failed
            failed_executions = search_executions.filter(status="failed")
            api_error = failed_executions.exists()
            error_messages = (
                list(
                    failed_executions.exclude(error_message="")
                    .values_list("error_message", flat=True)
                    .distinct()[:5]
                )
                if api_error
                else []
            )

            context = {
                "session": session,
                "search_executions": search_executions,
                "api_error": api_error,
                "error_messages": error_messages,
            }
            return render(request, "results_manager/no_results_found.html", context)

        # Otherwise render normal processing status
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session_id = self.kwargs["session_id"]

        # Get session and processing session
        session = get_object_or_404(
            SearchSession, id=session_id, owner=self.request.user
        )
        # Ensure we have the latest session state
        session.refresh_from_db()
        processing_session = ProcessingSession.objects.filter(
            search_session=session
        ).first()

        if not processing_session:
            # Create a placeholder if doesn't exist yet
            processing_session = ProcessingSession.objects.create(
                search_session=session,
                status="pending",
                total_raw_results=session.total_results or 0,
            )

        # Calculate completed stages
        stages = {
            "fetching": {"completed": False},
            "url_normalization": {"completed": False},
            "duplicate_detection": {"completed": False},
            "metadata_extraction": {"completed": False},
            "quality_scoring": {"completed": False},
            "finalization": {"completed": False},
        }

        stage_order = list(stages.keys())
        current_stage_index = (
            stage_order.index(processing_session.current_stage)
            if processing_session.current_stage in stage_order
            else -1
        )

        for i, stage in enumerate(stage_order):
            if i < current_stage_index:
                stages[stage]["completed"] = True

        # Get filtering statistics for transparency (Issue #100)
        filtering_stats = get_filtering_statistics(session_id)

        context.update(
            {
                "session": session,
                "processing_session": processing_session,
                "stages": stages,
                "filtering_stats": filtering_stats,  # Issue #100: Add filtering transparency
            }
        )

        return context


class ProcessingStatusAPIView(LoginRequiredMixin, View):
    """
    API endpoint for real-time processing status updates.
    """

    def get(self, request, session_id):
        # Get session and processing session
        session = get_object_or_404(SearchSession, id=session_id, owner=request.user)
        processing_session = ProcessingSession.objects.filter(
            search_session=session
        ).first()

        if not processing_session:
            return JsonResponse(
                {
                    "status": "pending",
                    "progress_percentage": 0,
                    "message": "Processing has not started yet",
                }
            )

        # Calculate time remaining
        estimated_time_remaining = None
        if processing_session.estimated_completion:
            time_remaining = processing_session.estimated_completion - timezone.now()
            if time_remaining.total_seconds() > 0:
                minutes = int(time_remaining.total_seconds() / 60)
                seconds = int(time_remaining.total_seconds() % 60)
                if minutes > 0:
                    estimated_time_remaining = (
                        f"{minutes} minute{'s' if minutes != 1 else ''}"
                    )
                else:
                    estimated_time_remaining = (
                        f"{seconds} second{'s' if seconds != 1 else ''}"
                    )

        # Determine completed stages
        stage_order = [
            "fetching",
            "url_normalization",
            "duplicate_detection",
            "metadata_extraction",
            "quality_scoring",
            "finalization",
        ]
        completed_stages = []
        if processing_session.current_stage in stage_order:
            current_index = stage_order.index(processing_session.current_stage)
            completed_stages = stage_order[:current_index]

        # Check if we should redirect to review
        redirect_to_review = False
        if session.status == "ready_for_review":
            redirect_to_review = True

        # Get filtering statistics for transparency (Issue #100)
        filtering_stats = get_filtering_statistics(session.id)

        response_data: ProcessingStatusResponse = {
            "status": processing_session.status,
            "progress_percentage": processing_session.progress_percentage,
            "current_stage": processing_session.current_stage,
            "stage_progress": processing_session.stage_progress,
            "processed_count": processing_session.processed_count,
            "total_raw_results": processing_session.total_raw_results,
            "duplicate_count": processing_session.duplicate_count,
            "unique_count": processing_session.unique_count,
            "error_count": processing_session.error_count,
            "estimated_completion": (
                processing_session.estimated_completion.isoformat()
                if processing_session.estimated_completion
                else None
            ),
            "estimated_time_remaining": estimated_time_remaining,
            "completed_stages": completed_stages,
            "redirect_to_review": redirect_to_review,
            "session_status": session.status,
            "total_results": session.total_results,
            "filtering_stats": filtering_stats,
        }
        return JsonResponse(response_data)
