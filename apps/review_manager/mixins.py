from typing import Dict, Any

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


class UserOwnerMixin(UserPassesTestMixin):
    """Mixin to ensure user owns the session."""

    def test_func(self) -> bool:
        session = self.get_object()
        return session.owner == self.request.user

    def handle_no_permission(self) -> HttpResponse:
        messages.error(
            self.request, "You don't have permission to access this session."
        )
        return redirect("review_manager:dashboard")


class SessionNavigationMixin:
    """Mixin for smart session navigation based on status."""

    def get_session_next_url(self, session) -> Dict[str, Any]:
        """Determine where to send user when they click on a session.

        Routes to appropriate review interface based on workflow type:
        - Workflow #2 (min_reviewers_per_result >= 2): Django templates with multi-reviewer mode
        - Workflow #1 (min_reviewers_per_result = 1): Django templates (or optionally Vue SPA)

        Args:
            session: SearchSession instance to generate navigation for

        Returns:
            Dict containing url, text, icon, and help text for navigation

        Raises:
            AttributeError: If session is missing required attributes
        """
        # Both workflows use Django templates after dual-screening refactoring
        # The Django template (results_overview.html) supports both:
        # - Workflow #1: Single reviewer mode with SimpleReviewDecision
        # - Workflow #2: Multi-reviewer mode with ReviewerDecision, blinding, and conflict detection
        review_url = reverse(
            "review_results:overview", kwargs={"session_id": session.id}
        )
        review_text_start = "Start Review"
        review_text_continue = "Continue Review"

        navigation_map = {
            "draft": {
                "url": reverse(
                    "search_strategy:strategy_form", kwargs={"session_id": session.id}
                ),
                "text": "Define Search Strategy",
                "icon": "bi-search",
                "help": "Define your Population, Interest, and Context terms",
            },
            "defining_search": {
                "url": reverse(
                    "search_strategy:strategy_form", kwargs={"session_id": session.id}
                ),
                "text": "Complete Strategy",
                "icon": "bi-pencil",
                "help": "Finish defining your search strategy",
            },
            "ready_to_execute": {
                "url": reverse(
                    "serp_execution:execution_status", kwargs={"session_id": session.id}
                ),
                "text": "View Execution Status",
                "icon": "bi-play-circle",
                "help": "View search execution progress",
            },
            "executing": {
                "url": reverse(
                    "serp_execution:execution_status", kwargs={"session_id": session.id}
                ),
                "text": "View Progress",
                "icon": "bi-hourglass-split",
                "help": "Monitor search execution progress",
            },
            "processing_results": {
                # Results manager URLs are disabled, show session detail instead
                "url": reverse(
                    "review_manager:session_detail", kwargs={"session_id": session.id}
                ),
                "text": "Processing...",
                "icon": "bi-gear-wide-connected",
                "help": "Results are being deduplicated and processed",
            },
            "ready_for_review": {
                "url": review_url,
                "text": review_text_start,
                "icon": "bi-journal-check",
                "help": f"{session.total_results} results ready for review",
            },
            "under_review": {
                "url": review_url,
                "text": review_text_continue,
                "icon": "bi-journal-bookmark",
                "help": f"{session.reviewed_results} of {session.total_results} reviewed",
            },
            "completed": {
                "url": reverse(
                    "reporting:dashboard", kwargs={"session_id": session.id}
                ),
                "text": "View Report",
                "icon": "bi-file-earmark-text",
                "help": "Access final report and export options",
            },
            "archived": {
                "url": reverse(
                    "reporting:dashboard", kwargs={"session_id": session.id}
                ),
                "text": "View Archived",
                "icon": "bi-archive",
                "help": "Access archived review report",
            },
        }

        return navigation_map.get(
            session.status,
            {
                "url": reverse(
                    "review_manager:session_detail", kwargs={"session_id": session.id}
                ),
                "text": "View Details",
                "icon": "bi-info-circle",
                "help": "View session information",
            },
        )

    def get_status_explanation(self, status: str) -> str:
        """Get user-friendly explanation of session status.

        Args:
            status: The session status string to explain

        Returns:
            str: Human-readable explanation of the status
        """
        explanations = {
            "draft": "Your session is created but needs a search strategy.",
            "defining_search": "You are defining the search strategy for this review.",
            "ready_to_execute": "Your search strategy is defined. Ready to execute searches.",
            "executing": "Searches are currently running across selected sources.",
            "processing_results": "Search results are being processed and deduplicated.",
            "ready_for_review": "Results are ready for your review.",
            "under_review": "You are actively reviewing the search results.",
            "completed": "Your review is complete and ready for reporting.",
            "archived": "This session has been archived but remains accessible.",
        }
        return explanations.get(status, "Session status unknown.")
