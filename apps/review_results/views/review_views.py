"""
Template-based views for the review_results app.

This module contains views that render HTML templates for the manual
review interface. These views handle the main review pages and forms.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Case, Count, Exists, F, OuterRef, Q, Subquery, Sum, When
from django.db.models.functions import Coalesce
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.results_manager.models import ProcessedResult
from apps.search_strategy.models import SearchQuery
from apps.serp_execution.models import SearchExecution

from ..models import (
    ConflictResolution,
    ReviewerCompletion,
    ReviewerDecision,
    SimpleReviewDecision,
)
from ..providers import get_results_provider
from ..services.review_cache_manager import ReviewCacheManager
from ..services.review_service import ReviewService
from ..services.simple_review_progress_service import SimpleReviewProgressService
from .mixins import SessionOwnershipMixin

logger = logging.getLogger(__name__)


class ResultsReviewView(LoginRequiredMixin, SessionOwnershipMixin, TemplateView):
    """
    Main manual review interface for Include/Exclude decisions.

    This view provides the primary interface where researchers systematically
    review processed search results to make Include/Exclude decisions. Features:

    - Display of processed results with title, URL, snippet, and metadata
    - Filtering by review status (pending, included, excluded)
    - Pagination for large result sets (25 items per page default)
    - Interactive decision buttons with exclusion reason selection
    - Notes system for reviewer comments and annotations
    - Progress tracking showing review completion percentage

    The interface follows PRISMA systematic review guidelines and enables
    researchers to efficiently process large sets of search results while
    maintaining audit trails and decision rationale.
    """

    template_name = "review_results/results_overview.html"

    def get(self, request, *args, **kwargs):
        """
        Handle GET request - show error if session requires blind screening.
        """
        # After dual-screening refactoring, the Django template (results_overview.html)
        # fully supports both workflows:
        # - Workflow #1 (min_reviewers_per_result = 1): Single reviewer mode
        # - Workflow #2 (min_reviewers_per_result >= 2): Multi-reviewer mode with blinding
        # No blocking or redirection needed - the template handles both cases appropriately

        return super().get(request, *args, **kwargs)

    def _handle_auto_transition(self, session) -> None:
        """Transition session from ready_for_review to under_review if needed."""
        if session.status != "ready_for_review":
            return

        from apps.review_manager.services.state_manager import SessionStateManager

        try:
            state_manager = SessionStateManager(session)
            state_manager.safely_start_review(
                metadata={
                    "trigger": "review_interface_accessed",
                    "automatic_transition": True,
                    "user_initiated": str(self.request.user.pk),
                }
            )
            session.refresh_from_db()
            logger.info(
                f"Automatically transitioned session {session.id} "
                f"from ready_for_review to under_review"
            )

            try:
                ReviewCacheManager.warm_review_cache(session)
                logger.debug(f"Warmed cache for review session {session.id}")
            except Exception as cache_error:
                logger.warning(
                    f"Failed to warm cache for session {session.id}: {cache_error}"
                )
        except Exception as e:
            logger.error(
                f"Failed to transition session {session.id} to under_review: {str(e)}"
            )

    def _annotate_review_status(self, queryset, user, is_workflow_2: bool):
        """Annotate queryset with user's review decision status."""
        if is_workflow_2:
            user_decision = ReviewerDecision.objects.filter(
                result=OuterRef("pk"),
                reviewer=user,
                is_revote=False,
            )
            return queryset.annotate(
                has_user_decision=Exists(user_decision),
                user_decision_type=Subquery(user_decision.values("decision")[:1]),
            )
        else:
            return queryset.annotate(
                simple_decision=F("simplereviewdecision__decision")
            )

    def _apply_status_filter(self, results, review_status: str, is_workflow_2: bool):
        """Apply workflow-aware review status filtering to results queryset."""
        if not review_status:
            return results

        results = self._annotate_review_status(
            results, self.request.user, is_workflow_2
        )

        if review_status == "pending":
            if is_workflow_2:
                return results.filter(has_user_decision=False)
            return results.filter(
                Q(simple_decision__isnull=True) | Q(simple_decision="pending")
            )
        elif review_status == "retrieved":
            return results.filter(is_retrieved=True)
        else:
            if is_workflow_2:
                decision_map = {
                    "include": "INCLUDE",
                    "exclude": "EXCLUDE",
                    "maybe": "MAYBE",
                }
                decision_value = decision_map.get(review_status, review_status.upper())
                return results.filter(
                    has_user_decision=True, user_decision_type=decision_value
                )
            return results.filter(simple_decision=review_status)

    def _get_review_statistics(self, session) -> dict:
        """Get review progress stats and processing counts for the session."""
        progress_service = SimpleReviewProgressService()
        progress_data = progress_service.get_progress_summary(
            str(session.id), session=session, user=self.request.user
        )

        processing_counts = ProcessedResult.objects.filter(session=session).aggregate(
            error_count=Count(Case(When(processing_status="error", then=1))),
            total_processed_count=Count("id"),
            filtered_count=Count(
                Case(
                    When(
                        processing_status="filtered",
                        processing_error_category="duplicate",
                        then=1,
                    )
                )
            ),
            file_type_filtered_count=Count(
                Case(
                    When(
                        processing_status="filtered",
                        processing_error_category="file_type_mismatch",
                        then=1,
                    )
                )
            ),
        )

        return {
            "pending_count": progress_data["pending_count"],
            "included_count": progress_data["include_count"],
            "excluded_count": progress_data["exclude_count"],
            "maybe_count": progress_data["maybe_count"],
            "retrieved_count": progress_data["retrieved_count"],
            "duplicate_count": progress_data["duplicates_removed"],
            "error_count": processing_counts["error_count"],
            "total_count": progress_data["total_results"],
            "total_processed_count": processing_counts["total_processed_count"],
            "successful_count": progress_data["total_results"],
            "duplicate_groups_count": processing_counts["filtered_count"],
            "file_type_filtered_count": processing_counts["file_type_filtered_count"],
        }

    def _get_workflow2_completion(self, session) -> dict:
        """Get Workflow #2 reviewer completion data (or empty defaults).

        Refreshes ReviewerCompletion.total_results and reviewed_results from
        live queries so the completion modal never shows stale counts (#82).
        """
        is_workflow_2 = (
            session.current_configuration
            and session.current_configuration.is_workflow_2
        )
        if not is_workflow_2:
            return {"user_completion": None, "all_completions": []}

        # Compute the live total of reviewable results (SUCCESS + not hidden).
        # This is the single source of truth that both total_results and
        # reviewed_results must be measured against.
        live_total = ProcessedResult.objects.filter(
            session=session,
            processing_status="success",
            is_hidden=False,
        ).count()

        # Bulk-sync every ReviewerCompletion.total_results for this session
        # so all reviewers see the same denominator.
        ReviewerCompletion.objects.filter(session=session).exclude(
            total_results=live_total
        ).update(total_results=live_total)

        # Refresh each reviewer's reviewed_results from ReviewerDecision counts.
        all_completions = (
            ReviewerCompletion.objects.filter(session=session)
            .select_related("reviewer")
            .order_by("reviewer__username")
        )
        for completion in all_completions:
            live_reviewed = (
                ReviewerDecision.objects.filter(
                    result__session=session,
                    result__processing_status="success",
                    result__is_hidden=False,
                    reviewer=completion.reviewer,
                    is_revote=False,
                )
                .values("result")
                .distinct()
                .count()
            )
            if completion.reviewed_results != live_reviewed:
                completion.reviewed_results = live_reviewed
                completion.save(update_fields=["reviewed_results", "updated_at"])

        # Re-fetch after the sync so template gets fresh values
        user_completion = ReviewerCompletion.objects.filter(
            session=session, reviewer=self.request.user
        ).first()
        all_completions = (
            ReviewerCompletion.objects.filter(session=session)
            .select_related("reviewer")
            .order_by("reviewer__username")
        )

        return {
            "user_completion": user_completion,
            "all_completions": all_completions,
        }

    def get_context_data(self, **kwargs):
        """
        Add results and review data to template context.

        Retrieves processed results for the session, applies filtering,
        handles pagination, and adds review progress information.
        """
        context = super().get_context_data(**kwargs)
        session = self.get_session()

        self._handle_auto_transition(session)

        try:
            ReviewCacheManager.update_review_activity(str(session.id))
        except Exception as e:
            logger.debug(f"Failed to update review activity: {e}")

        context["session"] = session

        # Query params
        review_status = self.request.GET.get("review_status", "")
        try:
            per_page = int(self.request.GET.get("per_page", 25))
            if per_page not in [10, 25, 50, 100]:
                per_page = 25
        except (ValueError, TypeError):
            per_page = 25
        page = self.request.GET.get("page", 1)

        # Filter results
        is_workflow_2 = (
            session.current_configuration
            and session.current_configuration.is_workflow_2
        )
        results_provider = get_results_provider()
        results = results_provider.get_results_queryset_for_session(session.id)
        results = self._apply_status_filter(results, review_status, is_workflow_2)

        # Statistics
        stats = self._get_review_statistics(session)
        context.update(stats)

        # Workflow #2 completion + pending conflicts
        context.update(self._get_workflow2_completion(session))
        if is_workflow_2:
            context["pending_conflicts_count"] = (
                ConflictResolution.objects.for_session(session).unresolved().count()
            )

        # Exclusion reasons for modals (single + bulk)
        context["exclusion_reasons"] = SimpleReviewDecision.EXCLUSION_REASONS

        # Pagination
        context["review_status"] = review_status
        context["per_page"] = per_page
        paginator = Paginator(results, per_page)
        context["results"] = paginator.get_page(page)

        return context


class FilteredResultsView(LoginRequiredMixin, SessionOwnershipMixin, TemplateView):
    """
    View for displaying filtered/duplicate results for transparency (Issue #100).

    This view shows results that were filtered out during processing,
    allowing users to understand what was excluded and potentially
    recover results if needed.
    """

    template_name = "review_results/filtered_results.html"

    def get_context_data(self, **kwargs):
        """Add filtered results data to template context."""
        context = super().get_context_data(**kwargs)

        # Get session
        session = self.get_session()
        context["session"] = session

        # Get query parameters
        filter_type = self.request.GET.get(
            "filter_type", ""
        )  # duplicate, error, or all
        try:
            per_page = int(self.request.GET.get("per_page", 25))
            if per_page not in [10, 25, 50, 100]:
                per_page = 25
        except (ValueError, TypeError):
            per_page = 25
        page = self.request.GET.get("page", 1)

        # Get filtered results
        filtered_results = ReviewService.get_filtered_results(session.id)

        # Apply filter type
        if filter_type == "duplicate":
            filtered_results = [
                r for r in filtered_results if r.processing_status == "filtered"
            ]
        elif filter_type == "error":
            filtered_results = [
                r for r in filtered_results if r.processing_status == "error"
            ]
        # If filter_type is empty or "all", show all filtered results

        # Get processing statistics
        processing_stats = ReviewService.get_processing_stats(session.id)

        # Pagination
        paginator = Paginator(filtered_results, per_page)
        page_obj = paginator.get_page(page)

        context.update(
            {
                "filtered_results": page_obj,
                "per_page": per_page,
                "filter_type": filter_type,
                "processing_stats": processing_stats,
                "duplicate_count": processing_stats.get("filtered_duplicates", 0),
                "error_count": processing_stats.get("processing_errors", 0),
                "total_filtered": processing_stats.get("filtered_duplicates", 0)
                + processing_stats.get("processing_errors", 0),
                # Pass per_page for navigation links to preserve user's pagination preference
                "current_per_page": per_page,
            }
        )

        return context


class BulkResetReviewsView(LoginRequiredMixin, SessionOwnershipMixin, View):
    """
    Bulk reset all review decisions for a session.

    This view allows users to clear all review decisions for a search session,
    effectively resetting the review process. Useful when:

    - Criteria for inclusion/exclusion have changed
    - Multiple reviewers need to start fresh
    - Errors were made in the initial review process
    - Testing or training purposes require a clean slate

    The reset operation:
    - Deletes all SimpleReviewDecision records for the session
    - Resets ProcessedResult.is_reviewed flag to False
    - Maintains all search results and other session data
    - Allows immediate restart of the review process
    """

    def post(self, request, session_id):
        """
        Reset all review decisions for the specified session.

        Args:
            request: HTTP request object with POST data.
            session_id: UUID of the session to reset reviews for.

        Returns:
            HttpResponse: Redirect back to review interface with success message.
        """
        session = self.get_session()

        # Count existing decisions for feedback
        decision_count = SimpleReviewDecision.objects.filter(session=session).count()

        if decision_count > 0:
            # Delete all review decisions for this session
            SimpleReviewDecision.objects.filter(session=session).delete()

            # Reset the is_reviewed flag on all processed results
            ProcessedResult.objects.filter(session=session).update(is_reviewed=False)

            messages.success(
                request,
                f"Successfully reset {decision_count} review decisions. "
                "You can now start the review process again.",
            )
            logger.info(
                f"Reset {decision_count} review decisions for session {session_id}"
            )
        else:
            messages.info(request, "No review decisions to reset.")

        return redirect("review_results:overview", session_id=session_id)


class SearchStatisticsView(LoginRequiredMixin, SessionOwnershipMixin, TemplateView):
    """
    Display comprehensive search query execution statistics.

    Shows completion rates, provider breakdown, deduplication stats,
    and per-execution details. Paginates SearchExecution objects so
    multi-provider queries show one row per provider.
    """

    template_name = "review_results/search_statistics.html"

    def get_queryset(self):
        """Get all executions for active queries, ordered by query then provider."""
        session = self.get_session()
        return (
            SearchExecution.objects.filter(
                query__session=session, query__is_active=True
            )
            .select_related("query", "query__strategy")
            .order_by("query__execution_order", "serp_provider", "created_at")
        )

    def _get_provider_stats(self, session):
        """Aggregate execution stats per SERP provider."""
        stats = list(
            SearchExecution.objects.filter(
                query__session=session, query__is_active=True
            )
            .values("serp_provider", "serp_provider_display")
            .annotate(
                total_executions=Count("id"),
                completed=Count("id", filter=Q(status="completed")),
                failed=Count("id", filter=Q(status="failed")),
                rate_limited=Count("id", filter=Q(status="rate_limited")),
                total_results=Coalesce(
                    Sum("results_count", filter=Q(status="completed")), 0
                ),
            )
            .order_by("serp_provider")
        )
        for entry in stats:
            total = entry["total_executions"]
            entry["success_rate"] = (
                round(entry["completed"] / total * 100, 1) if total > 0 else 0
            )
        return stats

    def _get_overlap_count(self, session, provider_count):
        """Count URLs found by 2+ providers. Skip if only one provider."""
        if provider_count < 2:
            return 0
        from apps.serp_execution.models import RawSearchResult

        return (
            RawSearchResult.objects.filter(
                execution__query__session=session,
                execution__query__is_active=True,
            )
            .values("link")
            .annotate(provider_count=Count("execution__serp_provider", distinct=True))
            .filter(provider_count__gt=1)
            .count()
        )

    def get_context_data(self, **kwargs):
        """Add session, executions, provider stats, and dedup stats to context."""
        context = super().get_context_data(**kwargs)

        session = self.get_session()
        context["session"] = session

        # Per-page preference
        try:
            per_page = int(self.request.GET.get("per_page", 25))
            if per_page not in [10, 25, 50, 100]:
                per_page = 25
        except (ValueError, TypeError):
            per_page = 25

        context["per_page"] = per_page
        context["current_per_page"] = per_page

        # Query-level stats (for overall cards)
        active_queries = SearchQuery.objects.filter(session=session, is_active=True)
        total_queries = active_queries.count()

        annotated_queries = active_queries.annotate(
            execution_count=Count("executions"),
            completed_count=Count(
                "executions", filter=Q(executions__status="completed")
            ),
        )

        # Overall execution stats
        overall_stats = active_queries.aggregate(
            total_executions=Count("executions"),
            completed_executions=Count(
                "executions", filter=Q(executions__status="completed")
            ),
            failed_executions=Count(
                "executions", filter=Q(executions__status="failed")
            ),
            pending_executions=Count(
                "executions", filter=Q(executions__status="pending")
            ),
            running_executions=Count(
                "executions", filter=Q(executions__status="running")
            ),
            total_results=Coalesce(Sum("executions__results_count"), 0),
        )

        # Completion rate
        completion_rate = 0.0
        if total_queries > 0:
            queries_with_completion = annotated_queries.filter(
                completed_count__gt=0
            ).count()
            completion_rate = queries_with_completion / total_queries * 100

        # Success rate
        success_rate = 0.0
        if overall_stats["total_executions"] > 0:
            success_rate = (
                overall_stats["completed_executions"]
                / overall_stats["total_executions"]
                * 100
            )

        context["overall_stats"] = {
            "total_queries": total_queries,
            "queries_with_executions": annotated_queries.filter(
                execution_count__gt=0
            ).count(),
            "queries_without_executions": annotated_queries.filter(
                execution_count=0
            ).count(),
            "total_executions": overall_stats["total_executions"],
            "completed": overall_stats["completed_executions"],
            "failed": overall_stats["failed_executions"],
            "pending": overall_stats["pending_executions"],
            "running": overall_stats["running_executions"],
            "total_results": overall_stats["total_results"],
            "completion_rate": round(completion_rate, 1),
            "success_rate": round(success_rate, 1),
        }

        # Provider breakdown
        provider_stats = self._get_provider_stats(session)
        context["provider_stats"] = provider_stats

        # Cross-provider overlap
        overlap_count = self._get_overlap_count(session, len(provider_stats))
        context["overlap_count"] = overlap_count

        # Overlap percentage (of total raw results from completed executions)
        total_raw = sum(p["total_results"] for p in provider_stats)
        context["overlap_percentage"] = (
            round(overlap_count / total_raw * 100, 1) if total_raw > 0 else 0
        )

        # Deduplication stats
        from apps.results_manager.api import get_deduplication_stats

        context["dedup_stats"] = get_deduplication_stats(str(session.id))

        # Paginate executions (not queries)
        all_executions = self.get_queryset()
        page = self.request.GET.get("page", 1)
        paginator = Paginator(all_executions, per_page)
        page_obj = paginator.get_page(page)

        context["executions"] = page_obj
        context["is_paginated"] = paginator.num_pages > 1
        context["page_obj"] = page_obj
        context["paginator"] = paginator

        # Keep 'queries' for backward compat with empty state check
        context["queries"] = page_obj

        return context
