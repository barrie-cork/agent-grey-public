"""
Workflow statistics aggregation service.

Replaces large inline methods in monitoring views with a focused,
cacheable service for collecting workflow execution statistics.
"""

from datetime import timedelta
from typing import Any, Dict, List

from django.db.models import Count, Q
from django.utils import timezone

from apps.core.services.base import BaseService
from apps.core.types.monitoring_types import StatusDistributionData, WorkflowStatsData


class WorkflowStatsConfig(Dict[str, Any]):
    """Configuration for workflow statistics aggregation."""

    cache_timeout: int
    status_timeout_minutes: int
    error_rate_threshold: float


class WorkflowStatsAggregator(BaseService[WorkflowStatsConfig]):
    """
    Aggregates workflow statistics for monitoring dashboards.

    Replaces the large _get_workflow_statistics method from monitoring views
    with a focused, testable, and cacheable service.
    """

    SERVICE_NAME = "WorkflowStatsAggregator"
    SERVICE_VERSION = "1.0.0"

    def _initialize(self) -> None:
        """Initialize the workflow stats aggregator."""
        self.cache_timeout = self.config.get("cache_timeout", 60)  # 1 minute default
        self.status_timeout_minutes = self.config.get("status_timeout_minutes", 30)
        self.error_rate_threshold = self.config.get("error_rate_threshold", 0.1)  # 10%

    def health_check(self) -> bool:
        """Check if the service can access required models."""
        try:
            from apps.review_manager.models import SearchSession

            # Quick count to verify database access
            SearchSession.objects.count()
            return True
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False

    def get_default_config(self) -> WorkflowStatsConfig:
        """Get default configuration."""
        return WorkflowStatsConfig(
            cache_timeout=60, status_timeout_minutes=30, error_rate_threshold=0.1
        )

    def get_stats(self, hours_back: int = 24) -> WorkflowStatsData:
        """
        Get aggregated workflow statistics.

        Args:
            hours_back: Number of hours to look back for statistics

        Returns:
            WorkflowStatsData with aggregated statistics
        """
        cache_key = f"workflow_stats_{hours_back}h"

        # Check cache first
        cached_stats = self.get_cached_value(cache_key)
        if cached_stats:
            return cached_stats

        # Generate fresh statistics
        with self._measure_performance("get_workflow_stats"):
            try:
                stats = self._collect_workflow_statistics(hours_back)

                # Cache the results
                self.set_cached_value(cache_key, stats)

                return stats

            except Exception as e:
                self._handle_error(e, {"hours_back": hours_back}, "get_workflow_stats")
                # Return empty stats on error
                return self._get_empty_stats()

    def _collect_workflow_statistics(self, hours_back: int) -> WorkflowStatsData:
        """Collect workflow statistics from the database."""
        from apps.review_manager.models import SearchSession

        cutoff_time = timezone.now() - timedelta(hours=hours_back)
        cutoff_1h = timezone.now() - timedelta(hours=1)

        # Get sessions within time period
        sessions_qs = SearchSession.objects.filter(updated_at__gte=cutoff_time)
        sessions_1h_qs = SearchSession.objects.filter(updated_at__gte=cutoff_1h)

        # Count sessions by time periods
        sessions_last_hour = sessions_1h_qs.count()
        sessions_last_24h = sessions_qs.count()

        # Get status distribution
        status_distribution = self._get_status_distribution(sessions_qs)

        # Calculate completion time and error rate
        avg_completion_time_hours = self._calculate_avg_completion_time(sessions_qs)
        error_rate_24h = self._calculate_error_rate(sessions_qs)

        # Count processing and stuck sessions
        processing_sessions = sessions_qs.filter(
            status__in=["executing", "processing_results"]
        ).count()

        stuck_sessions = self._count_stuck_sessions()

        return WorkflowStatsData(
            sessions_last_hour=sessions_last_hour,
            sessions_last_24h=sessions_last_24h,
            status_distribution=status_distribution,
            avg_completion_time_hours=avg_completion_time_hours,
            error_rate_24h=error_rate_24h,
            processing_sessions=processing_sessions,
            stuck_sessions=stuck_sessions,
        )

    def _get_status_distribution(self, sessions_qs) -> StatusDistributionData:
        """Get the distribution of session statuses."""
        status_counts = sessions_qs.values("status").annotate(count=Count("id"))

        distribution = StatusDistributionData(
            draft=0,
            defining_search=0,
            ready_to_execute=0,
            executing=0,
            processing_results=0,
            ready_for_review=0,
            under_review=0,
            completed=0,
            archived=0,
        )

        for item in status_counts:
            status = item["status"]
            count = item["count"]
            if status in distribution:
                distribution[status] = count

        return distribution

    def _calculate_avg_completion_time(self, sessions_qs) -> float:
        """Calculate average completion time for sessions."""
        completed_sessions = sessions_qs.filter(
            status__in=["completed", "archived"],
            created_at__isnull=False,
            updated_at__isnull=False,
        )

        if not completed_sessions.exists():
            return 0.0

        # Calculate duration for each completed session
        durations = []
        for session in completed_sessions:
            if session.created_at and session.updated_at:
                duration = session.updated_at - session.created_at
                durations.append(duration.total_seconds() / 3600)  # Convert to hours

        return sum(durations) / len(durations) if durations else 0.0

    def _calculate_error_rate(self, sessions_qs) -> float:
        """Calculate error rate for sessions."""
        total_sessions = sessions_qs.count()
        if total_sessions == 0:
            return 0.0

        # Count sessions with errors (you may need to adjust this based on your error tracking)
        error_sessions = sessions_qs.filter(
            Q(status="failed")
            | Q(status_detail__icontains="error")  # If you have a failed status
            | Q(  # If errors are tracked in status_detail
                status_detail__icontains="Error"
            )
        ).count()

        return (error_sessions / total_sessions) * 100 if total_sessions > 0 else 0.0

    def _count_stuck_sessions(self) -> int:
        """Count sessions that appear to be stuck in processing states."""
        from apps.review_manager.models import SearchSession

        timeout_cutoff = timezone.now() - timedelta(minutes=self.status_timeout_minutes)

        stuck_sessions = SearchSession.objects.filter(
            status__in=["executing", "processing_results"],
            updated_at__lt=timeout_cutoff,
        ).count()

        return stuck_sessions

    def _get_empty_stats(self) -> WorkflowStatsData:
        """Return empty statistics structure."""
        return WorkflowStatsData(
            sessions_last_hour=0,
            sessions_last_24h=0,
            status_distribution=StatusDistributionData(
                draft=0,
                defining_search=0,
                ready_to_execute=0,
                executing=0,
                processing_results=0,
                ready_for_review=0,
                under_review=0,
                completed=0,
                archived=0,
            ),
            avg_completion_time_hours=0.0,
            error_rate_24h=0.0,
            processing_sessions=0,
            stuck_sessions=0,
        )

    def get_detailed_stats(self, hours_back: int = 24) -> Dict[str, Any]:
        """
        Get detailed workflow statistics with additional metrics.

        Args:
            hours_back: Number of hours to look back

        Returns:
            Dictionary with detailed statistics
        """
        basic_stats = self.get_stats(hours_back)

        # Add additional detailed metrics
        detailed_stats = dict(basic_stats)
        detailed_stats.update(
            {
                "collection_timestamp": timezone.now().isoformat(),
                "cache_hit": bool(
                    self.get_cached_value(f"workflow_stats_{hours_back}h")
                ),
                "service_metrics": self.metrics.get_stats(),
                "error_threshold_exceeded": basic_stats["error_rate_24h"]
                > self.error_rate_threshold,
                "has_stuck_sessions": basic_stats["stuck_sessions"] > 0,
            }
        )

        return detailed_stats

    def get_trends(self, days_back: int = 7) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get trend data for workflow statistics.

        Args:
            days_back: Number of days of trend data to collect

        Returns:
            Dictionary with trend arrays for key metrics
        """
        trends = {"daily_sessions": [], "completion_rates": [], "error_rates": []}

        for day in range(days_back):
            date = timezone.now().date() - timedelta(days=day)
            # This would require more complex queries to get historical data
            # For now, return empty trends
            trends["daily_sessions"].append({"date": date.isoformat(), "sessions": 0})

        return trends
