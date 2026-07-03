"""
Views for displaying filtered duplicate results in review sessions.

Shows results that were removed by URLDeduplicationService
(processing_status='filtered', processing_error_category='duplicate').
"""

import logging
from collections import defaultdict
from urllib.parse import urlparse

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.views.generic import TemplateView

from apps.results_manager.models import ProcessedResult

from .mixins import SessionOwnershipMixin

logger = logging.getLogger(__name__)


class DuplicateGroupsView(LoginRequiredMixin, SessionOwnershipMixin, TemplateView):
    """
    View for filtered duplicate results.

    Displays results removed by URLDeduplicationService, grouped by domain.
    Each group shows the domain name, result count, and collapsible list.

    Template: review_results/duplicate_groups.html
    """

    template_name = "review_results/duplicate_groups.html"

    def get_context_data(self, **kwargs):
        """Add filtered duplicate results grouped by domain to template context."""
        context = super().get_context_data(**kwargs)

        session = self.get_session()
        context["session"] = session

        try:
            per_page = int(self.request.GET.get("per_page", 25))
            if per_page not in [10, 25, 50, 100]:
                per_page = 25
        except (ValueError, TypeError):
            per_page = 25
        page = self.request.GET.get("page", 1)

        # Query filtered duplicates
        filtered_duplicates = (
            ProcessedResult.objects.filter(
                session=session,
                processing_status="filtered",
                processing_error_category="duplicate",
            )
            .select_related("raw_result__execution__query")
            .order_by("-processed_at")
        )

        total_duplicates = filtered_duplicates.count()

        # Group by domain
        domain_groups: dict[str, list[ProcessedResult]] = defaultdict(list)
        for result in filtered_duplicates:
            try:
                domain = urlparse(result.url).netloc or "unknown"
            except ValueError:
                domain = "unknown"
            domain_groups[domain].append(result)

        # Build sorted group list (largest groups first)
        duplicate_groups = sorted(
            [
                {
                    "domain": domain,
                    "results": results,
                    "count": len(results),
                    "representative": results[0] if results else None,
                }
                for domain, results in domain_groups.items()
            ],
            key=lambda g: g["count"],
            reverse=True,
        )

        # Paginate groups
        paginator = Paginator(duplicate_groups, per_page)
        page_obj = paginator.get_page(page)

        context.update(
            {
                "duplicate_groups": page_obj.object_list,
                "filtered_duplicates": page_obj,
                "page_obj": page_obj,
                "per_page": per_page,
                "total_groups": len(duplicate_groups),
                "total_duplicate_results": total_duplicates,
                "current_per_page": per_page,
            }
        )

        return context
