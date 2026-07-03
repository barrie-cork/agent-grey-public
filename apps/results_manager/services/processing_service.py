"""Processing service for results manager app."""

from uuid import UUID

# Models imported lazily in methods for Celery compatibility


class ProcessingService:
    """Service for processing-related operations."""

    @staticmethod
    def has_active_processing(session_id: UUID) -> bool:
        """Check if a session has any active processing."""
        # Lazy import to avoid Django initialization timing issues in Celery
        from apps.results_manager.models import ProcessingSession

        return ProcessingSession.objects.filter(
            search_session_id=session_id, status__in=["pending", "in_progress"]
        ).exists()

    @staticmethod
    def has_completed_processing(session_id: UUID) -> bool:
        """Check if a session has any completed processing."""
        # Lazy import to avoid Django initialization timing issues in Celery
        from apps.results_manager.models import ProcessingSession

        return ProcessingSession.objects.filter(
            search_session_id=session_id, status="completed"
        ).exists()

    @staticmethod
    def get_processed_result_count(session_id: UUID) -> int:
        """Get the count of processed results for a session."""
        # Lazy import to avoid Django initialization timing issues in Celery
        from apps.results_manager.models import ProcessedResult

        return ProcessedResult.objects.filter(
            raw_result__execution__query__session_id=session_id
        ).count()

    @staticmethod
    def get_processing_stats(session_id: UUID) -> dict:
        """Get processing statistics for a session."""
        # Lazy import to avoid Django initialization timing issues in Celery
        from apps.results_manager.models import ProcessedResult, ProcessingSession

        processing_sessions = ProcessingSession.objects.filter(
            search_session_id=session_id
        )

        stats = {
            "total_sessions": processing_sessions.count(),
            "pending": processing_sessions.filter(status="pending").count(),
            "in_progress": processing_sessions.filter(status="in_progress").count(),
            "completed": processing_sessions.filter(status="completed").count(),
            "failed": processing_sessions.filter(status="failed").count(),
            "processed_results": ProcessedResult.objects.filter(
                raw_result__execution__query__session_id=session_id
            ).count(),
        }

        return stats
