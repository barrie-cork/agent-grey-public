"""Review service for review results app."""

from uuid import UUID

from apps.results_manager.models import ProcessedResult
from apps.review_results.models import SimpleReviewDecision


class ReviewService:
    """Service for review-related operations."""

    @staticmethod
    def get_review_decision_count(session_id: UUID) -> int:
        """Get the count of review decisions for a session."""
        return SimpleReviewDecision.objects.filter(
            result__session_id=session_id
        ).count()

    @staticmethod
    def get_included_count(session_id: UUID) -> int:
        """Get the count of included results for a session."""
        return SimpleReviewDecision.objects.filter(
            result__session_id=session_id, decision="include"
        ).count()

    @staticmethod
    def get_excluded_count(session_id: UUID) -> int:
        """Get the count of excluded results for a session."""
        return SimpleReviewDecision.objects.filter(
            result__session_id=session_id, decision="exclude"
        ).count()

    @staticmethod
    def get_review_stats(session_id: UUID) -> dict:
        """Get review statistics for a session."""
        decisions = SimpleReviewDecision.objects.filter(result__session_id=session_id)

        stats = {
            "total_decisions": decisions.count(),
            "included": decisions.filter(decision="include").count(),
            "excluded": decisions.filter(decision="exclude").count(),
            "pending": decisions.filter(decision__isnull=True).count(),
        }

        return stats

    @staticmethod
    def get_filtered_results(session_id: UUID) -> list:
        """Get filtered/duplicate results for transparency (Issue #100)."""
        filtered_results = (
            ProcessedResult.objects.filter(
                session_id=session_id, processing_status__in=["filtered", "error"]
            )
            .select_related("raw_result")
            .order_by("processed_at")
        )

        return filtered_results

    @staticmethod
    def get_filtered_count(session_id: UUID) -> int:
        """Get count of filtered results."""
        return ProcessedResult.objects.filter(
            session_id=session_id, processing_status__in=["filtered", "error"]
        ).count()

    @staticmethod
    def get_processing_stats(session_id: UUID) -> dict:
        """Get processing transparency statistics (Issue #100)."""
        results = ProcessedResult.objects.filter(session__id=session_id)

        stats = {
            "total_results": results.count(),
            "successful": results.filter(processing_status="success").count(),
            "filtered_duplicates": results.filter(processing_status="filtered").count(),
            "processing_errors": results.filter(processing_status="error").count(),
        }

        return stats
