"""Custom QuerySets for review_results models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from apps.review_manager.models import SearchSession


class ConflictResolutionQuerySet(models.QuerySet):
    """Optimised queryset for ConflictResolution with common filter patterns."""

    def unresolved(self) -> ConflictResolutionQuerySet:
        """Filter to conflicts awaiting resolution (excludes ESCALATED)."""
        from apps.review_results.models import ConflictResolution

        return self.filter(
            status__in=[
                ConflictResolution.STATUS_PENDING,
                ConflictResolution.STATUS_IN_DISCUSSION,
            ]
        )

    def resolved(self) -> ConflictResolutionQuerySet:
        """Filter to resolved conflicts."""
        from apps.review_results.models import ConflictResolution

        return self.filter(status=ConflictResolution.STATUS_RESOLVED)

    def for_session(self, session: SearchSession) -> ConflictResolutionQuerySet:
        """Filter conflicts belonging to a specific session."""
        return self.filter(result__session=session)

    def with_decisions(self) -> ConflictResolutionQuerySet:
        """Prefetch related decision data for conflict display."""
        return self.select_related(
            "result",
            "final_decision",
        ).prefetch_related(
            "conflicting_decisions__reviewer",
        )
