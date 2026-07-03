"""Custom QuerySets for results_manager models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from apps.review_manager.models import SearchSession


class ProcessedResultQuerySet(models.QuerySet):
    """Optimised queryset for ProcessedResult with common filter patterns."""

    def for_session(self, session: SearchSession) -> ProcessedResultQuerySet:
        """Filter results belonging to a specific session."""
        return self.filter(session=session)

    def successfully_processed(self) -> ProcessedResultQuerySet:
        """Filter to results that were successfully processed."""
        from apps.results_manager.models import ProcessedResult

        return self.filter(processing_status=ProcessedResult.STATUS_SUCCESS)

    def reviewed(self) -> ProcessedResultQuerySet:
        """Filter to results that have been reviewed."""
        return self.filter(is_reviewed=True)

    def pending_review(self) -> ProcessedResultQuerySet:
        """Filter to successfully processed results awaiting review."""
        from apps.results_manager.models import ProcessedResult

        return self.filter(
            is_reviewed=False, processing_status=ProcessedResult.STATUS_SUCCESS
        )

    def with_review_data(self) -> ProcessedResultQuerySet:
        """Prefetch related data commonly needed during review."""
        return self.select_related(
            "raw_result__execution__query",
        )
