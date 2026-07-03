"""
Simple progress tracking for review completion.
"""

from uuid import UUID


class SimpleReviewProgressService:
    """Simple progress tracking for review completion using dependency injection."""

    def __init__(self, results_provider=None) -> None:
        """Initialize with optional results provider for dependency injection."""
        from apps.results_manager.providers import ResultsProvider

        self._results_provider: ResultsProvider = results_provider or ResultsProvider()

    def _get_duplicate_info(self, session_id: str) -> tuple[int, set[UUID]]:
        """Get duplicate removal count and duplicate result IDs.

        Source of truth: ProcessedResult records with processing_status='filtered'
        and processing_error_category='duplicate' (set by URLDeduplicationService).

        Returns:
            Tuple of (duplicates_removed count, set of duplicate result IDs).
        """
        from apps.results_manager.models import ProcessedResult

        filtered_duplicates = ProcessedResult.objects.filter(
            session__id=session_id,
            processing_status="filtered",
            processing_error_category="duplicate",
        )
        duplicates_removed: int = filtered_duplicates.count()
        duplicate_result_ids: set[UUID] = set(
            filtered_duplicates.values_list("id", flat=True)
        )
        return duplicates_removed, duplicate_result_ids

    def _get_workflow1_counts(
        self, session_id: str, duplicate_result_ids: set[UUID]
    ) -> dict[str, int]:
        """Get decision counts from SimpleReviewDecision (Workflow #1)."""
        from ..models import SimpleReviewDecision

        decisions = SimpleReviewDecision.objects.filter(
            session__id=session_id,
            result__processing_status="success",
            result__is_hidden=False,
        )

        if duplicate_result_ids:
            base = decisions.exclude(result_id__in=duplicate_result_ids)
        else:
            base = decisions

        return {
            "reviewed_count": base.exclude(decision="pending").count(),
            "include_count": base.filter(decision="include").count(),
            "exclude_count": base.filter(decision="exclude").count(),
            "maybe_count": base.filter(decision="maybe").count(),
        }

    def _get_workflow2_counts(
        self,
        session_id: str,
        user,
        duplicate_result_ids: set[UUID],
    ) -> dict[str, int]:
        """Get decision counts from ReviewerDecision (Workflow #2) for a specific user."""
        from ..models import ReviewerDecision

        decisions = ReviewerDecision.objects.filter(
            result__session__id=session_id,
            result__processing_status="success",
            result__is_hidden=False,
            reviewer=user,
            is_revote=False,
        )

        if duplicate_result_ids:
            base = decisions.exclude(result_id__in=duplicate_result_ids)
        else:
            base = decisions

        return {
            "reviewed_count": base.count(),
            "include_count": base.filter(decision="INCLUDE").count(),
            "exclude_count": base.filter(decision="EXCLUDE").count(),
            "maybe_count": base.filter(decision="MAYBE").count(),
        }

    def get_progress_summary(
        self,
        session_id: str,
        session=None,
        user=None,
    ) -> dict[str, int | float]:
        """Get basic progress statistics.

        Args:
            session_id: UUID of the search session (as string).
            session: Optional SearchSession instance. If provided with user,
                enables Workflow #2 aware counting.
            user: Optional User instance. Required for Workflow #2 to count
                per-user ReviewerDecision records.
        """
        from apps.results_manager.models import ProcessedResult

        # Count only reviewable results (success + not hidden) to match
        # what the review interface actually displays.
        # Filtered duplicates already have processing_status='filtered',
        # so they are excluded from this count automatically.
        total_results: int = ProcessedResult.objects.filter(
            session__id=session_id,
            processing_status="success",
            is_hidden=False,
        ).count()
        duplicates_removed, duplicate_result_ids = self._get_duplicate_info(session_id)
        file_type_filtered_count: int = ProcessedResult.objects.filter(
            session__id=session_id,
            processing_status="filtered",
            processing_error_category="file_type_mismatch",
        ).count()

        # Determine workflow type and get appropriate counts
        is_workflow_2: bool = bool(
            session
            and user
            and getattr(session, "current_configuration", None)
            and session.current_configuration.is_workflow_2
        )

        if is_workflow_2 and user is not None:
            counts = self._get_workflow2_counts(session_id, user, duplicate_result_ids)
        else:
            counts = self._get_workflow1_counts(session_id, duplicate_result_ids)

        reviewed_count: int = counts["reviewed_count"]
        include_count: int = counts["include_count"]
        exclude_count: int = counts["exclude_count"]
        maybe_count: int = counts["maybe_count"]

        # Calculate retrieved count (URL clicks) - important for PRISMA reporting
        # Only count reviewable results to match the review interface
        retrieved_qs = ProcessedResult.objects.filter(
            session__id=session_id,
            is_retrieved=True,
            processing_status="success",
            is_hidden=False,
        )
        retrieved_count: int = retrieved_qs.count()

        # total_results already excludes filtered duplicates (they have
        # processing_status='filtered', not 'success'), so no subtraction needed.
        pending_count: int = max(0, total_results - reviewed_count)

        completion_percentage: float = (
            min(100.0, round((reviewed_count / total_results * 100), 1))
            if total_results > 0
            else 0.0
        )

        return {
            "total_results": total_results,
            "reviewed_count": reviewed_count,
            "pending_count": pending_count,
            "include_count": include_count,
            "exclude_count": exclude_count,
            "maybe_count": maybe_count,
            "retrieved_count": retrieved_count,
            "duplicates_removed": duplicates_removed,
            "file_type_filtered_count": file_type_filtered_count,
            "completion_percentage": completion_percentage,
        }
