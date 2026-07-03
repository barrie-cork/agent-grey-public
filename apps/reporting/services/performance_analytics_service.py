"""
Simplified performance analytics service for reporting slice.
Business capability: Basic search performance metrics.
"""

from apps.core.logging import ServiceLoggerMixin

# Use dependency injection instead of direct imports
from ..dependencies import get_results_manager, get_review_results, get_serp_execution


class PerformanceAnalyticsService(ServiceLoggerMixin):
    """Service for calculating basic search performance metrics."""

    def __init__(self):
        """Initialize service with dependencies."""
        self.results_manager = get_results_manager()
        self.review_results = get_review_results()
        self.serp_execution = get_serp_execution()

    def calculate_search_performance_metrics(self, session_id: str):
        """
        Calculate basic performance metrics for the search strategy.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with basic performance metrics
        """
        # Basic execution counts
        exec_stats = self.serp_execution.get_execution_statistics(session_id)
        total_executions = exec_stats["total_executions"]
        successful_executions = exec_stats["successful_executions"]

        # Result counts
        processed_results = self.results_manager.get_processed_results_for_session(
            session_id
        )
        unique_processed = len(processed_results)

        # Review counts
        inclusion_stats = self.review_results.get_inclusion_statistics(session_id)
        include_count = inclusion_stats["include"]
        exclude_count = inclusion_stats["exclude"]

        # Simple calculations with safe division
        success_rate = exec_stats["success_rate"]

        precision = (
            round((include_count / (include_count + exclude_count)) * 100, 1)
            if (include_count + exclude_count) > 0
            else 0
        )

        # Calculate average execution time (placeholder for now)
        avg_execution_time = 2.5  # seconds

        # Generate recommendations based on metrics
        recommendations = []
        if success_rate < 80:
            recommendations.append("Consider checking API connectivity or rate limits")
        if precision < 20:
            recommendations.append(
                "Review search terms to improve relevance of results"
            )
        if total_executions > 100:
            recommendations.append(
                "Consider using more targeted search queries to reduce API usage"
            )

        return {
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "success_rate": success_rate,
            "total_processed": unique_processed,
            "include_count": include_count,
            "exclude_count": exclude_count,
            "precision": precision,
            "avg_execution_time": avg_execution_time,
            "recommendations": recommendations,
        }

    def generate_execution_timeline(self, session_id: str):
        """
        Generate execution timeline data for visualization.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with timeline data
        """
        # Get all executions for the session
        executions = self.serp_execution.get_executions_for_session(session_id)

        timeline_data = []
        for execution in executions:
            timeline_data.append(
                {
                    "query_text": execution.get("query_text", ""),
                    "started_at": execution.get("started_at"),
                    "completed_at": execution.get("completed_at"),
                    "status": execution.get("status"),
                    "results_count": execution.get("results_count", 0),
                    "duration_seconds": execution.get("duration_seconds", 0),
                }
            )

        # Sort by start time
        timeline_data.sort(key=lambda x: x["started_at"] if x["started_at"] else "")

        # Calculate summary
        total_duration = 0
        if timeline_data:
            first_start = timeline_data[0].get("started_at")
            last_complete = timeline_data[-1].get("completed_at")

            if first_start and last_complete:
                # Calculate total duration in hours
                from datetime import datetime

                if isinstance(first_start, str):
                    first_start = datetime.fromisoformat(
                        first_start.replace("Z", "+00:00")
                    )
                if isinstance(last_complete, str):
                    last_complete = datetime.fromisoformat(
                        last_complete.replace("Z", "+00:00")
                    )

                total_duration = (last_complete - first_start).total_seconds() / 3600

        queries_per_hour = (
            len(timeline_data) / total_duration if total_duration > 0 else 0
        )

        return {
            "executions": timeline_data,
            "summary": {
                "total_duration": round(total_duration, 2),
                "queries_per_hour": round(queries_per_hour, 2),
            },
        }
