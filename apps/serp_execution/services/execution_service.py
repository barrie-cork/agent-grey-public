"""
Simple execution service for serp_execution slice.
Business capability: Basic execution coordination.
"""

# Removed complex type hints for production compatibility
from uuid import UUID

from django.db.models import Count


class ExecutionService:
    """Simple service for managing search execution."""

    def get_execution_statistics(self, session_id: str):
        """Get basic execution statistics for a session."""
        from ..models import SearchExecution

        executions = SearchExecution.objects.filter(query__session_id=session_id)

        if not executions.exists():
            return self._empty_stats()

        total_executions = executions.count()
        successful_executions = executions.filter(status="completed").count()
        failed_executions = executions.filter(status="failed").count()

        success_rate = (
            (successful_executions / total_executions * 100)
            if total_executions > 0
            else 0
        )

        return {
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": failed_executions,
            "success_rate": round(success_rate, 1),
        }

    def _empty_stats(self):
        """Return empty statistics structure."""
        return {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "success_rate": 0,
        }

    @staticmethod
    def get_pending_execution_count(session_id: UUID) -> int:
        """Get the count of pending executions for a session."""
        from ..models import SearchExecution

        return SearchExecution.objects.filter(
            query__session_id=session_id, status__in=["pending", "in_progress"]
        ).count()

    @staticmethod
    def get_completed_execution_count(session_id: UUID) -> int:
        """Get the count of completed executions for a session."""
        from ..models import SearchExecution

        return SearchExecution.objects.filter(
            query__session_id=session_id, status="completed"
        ).count()

    @staticmethod
    def get_executions_with_results_count(session_id: UUID) -> int:
        """Get the count of executions that have results."""
        from ..models import SearchExecution

        return (
            SearchExecution.objects.filter(
                query__session_id=session_id, status="completed"
            )
            .annotate(result_count=Count("raw_results"))
            .filter(result_count__gt=0)
            .count()
        )

    @staticmethod
    def has_executions_with_results(session_id: UUID) -> bool:
        """Check if a session has any executions with results."""
        from ..models import SearchExecution

        return (
            SearchExecution.objects.filter(
                query__session_id=session_id, status="completed"
            )
            .annotate(result_count=Count("raw_results"))
            .filter(result_count__gt=0)
            .exists()
        )

    @staticmethod
    def get_execution_stats(session_id: UUID):
        """Get execution statistics for a session.

        This is an alias for get_execution_statistics for backward compatibility.
        Returns the same data with additional fields.

        Returns:
            dict: Dictionary with execution statistics including total_executions,
                  successful_executions, failed_executions, success_rate, total,
                  pending, in_progress, completed, failed, result_count
        """
        from ..models import RawSearchResult, SearchExecution

        executions = SearchExecution.objects.filter(query__session_id=session_id)

        # Get base statistics
        total_executions = executions.count()
        successful_executions = executions.filter(status="completed").count()
        failed_executions = executions.filter(status="failed").count()
        pending_executions = executions.filter(status="pending").count()
        in_progress_executions = executions.filter(status="in_progress").count()

        success_rate = (
            (successful_executions / total_executions * 100)
            if total_executions > 0
            else 0
        )

        # Return comprehensive stats that satisfy both method signatures
        return {
            # Original get_execution_statistics fields
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": failed_executions,
            "success_rate": round(success_rate, 1),
            # Additional get_execution_stats fields
            "total": total_executions,
            "pending": pending_executions,
            "in_progress": in_progress_executions,
            "completed": successful_executions,
            "failed": failed_executions,
            "result_count": RawSearchResult.objects.filter(
                execution__query__session_id=session_id
            ).count(),
        }
