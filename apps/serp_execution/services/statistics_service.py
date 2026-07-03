"""
Statistics calculation service for SERP execution data.

This service provides centralized statistics calculation functionality
extracted from views to maintain single responsibility principle and
improve testability.
"""

import logging

from django.db.models import Case, Count, F, IntegerField, Sum, When
from django.utils import timezone

from ..utils import get_execution_statistics

logger = logging.getLogger(__name__)


class ExecutionStatisticsService:
    """Service for calculating execution statistics."""

    def calculate_enhanced_statistics(
        self, executions, session_id: str | None = None
    ) -> dict:
        """
        Calculate enhanced execution statistics for dashboard display.

        Computes aggregated metrics including success rates, result counts,
        and execution timing data optimized for card-based layout visualization.
        Uses database-level aggregation for optimal performance.

        Args:
            executions: QuerySet of SearchExecution objects
            session_id: Optional session ID for additional statistics

        Returns:
            dict: Comprehensive statistics dictionary
        """
        # Get basic statistics if session_id is provided
        basic_stats = {}
        if session_id:
            basic_stats = get_execution_statistics(session_id)

        # Calculate additional statistics efficiently using aggregation
        stats = executions.aggregate(
            total_executions=Count("id"),
            successful_executions=Count(
                Case(When(status="completed", then=1), output_field=IntegerField())
            ),
            failed_executions=Count(
                Case(When(status="failed", then=1), output_field=IntegerField())
            ),
            running_executions=Count(
                Case(When(status="running", then=1), output_field=IntegerField())
            ),
            pending_executions=Count(
                Case(When(status="pending", then=1), output_field=IntegerField())
            ),
            retrying_executions=Count(
                Case(
                    When(status="pending", retry_count__gt=0, then=1),
                    output_field=IntegerField(),
                )
            ),
            total_results=Sum(F("results_count"), default=0),
        )

        total_executions = stats["total_executions"]
        successful_executions = stats["successful_executions"]
        failed_executions = stats["failed_executions"]
        running_executions = stats["running_executions"]
        pending_executions = stats["pending_executions"]
        retrying_executions = stats["retrying_executions"]
        total_results = stats["total_results"]

        # Calculate success rate
        success_rate = (
            (successful_executions / total_executions * 100)
            if total_executions > 0
            else 0
        )

        # Get timing information
        last_execution_date = executions.filter(completed_at__isnull=False).first()
        last_execution_date = (
            last_execution_date.completed_at if last_execution_date else None
        )

        # Enhanced statistics dictionary
        enhanced_stats = {
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": failed_executions,
            "running_executions": running_executions,
            "pending_executions": pending_executions,
            "retrying_executions": retrying_executions,
            "total_results": total_results,
            "success_rate": round(success_rate, 1),
            "last_execution_date": last_execution_date,
        }

        # Merge with basic stats for backward compatibility
        enhanced_stats.update(basic_stats)

        return enhanced_stats


class SessionProgressService:
    """
    Service for calculating session status metrics.
    NO PERCENTAGES as per CORE_REQUIREMENTS.md.
    """

    def __init__(self):
        self.stats_service = ExecutionStatisticsService()

    def get_session_status(self, executions, session_id: str) -> dict:
        """
        Get current status for a session.
        NO PERCENTAGES - only counts and status messages.

        Args:
            executions: QuerySet of SearchExecution objects
            session_id: The session ID

        Returns:
            dict: Status data including counts and statistics
        """
        # Get enhanced statistics
        stats = self.stats_service.calculate_enhanced_statistics(executions, session_id)

        # Get current executions data
        executions_data = list(
            executions.values(
                "id", "status", "results_count", "error_message", "current_step"
            )
        )

        # Determine if still running
        has_running = any(
            e["status"] in ["pending", "running"] for e in executions_data
        )

        # Get current step from running execution
        current_step = ""
        for e in executions_data:
            if e["status"] == "running" and e.get("current_step"):
                current_step = e["current_step"]
                break

        return {
            "statistics": stats,
            "executions": executions_data,
            "has_running": has_running,
            "total_results": stats["total_results"],
            "queries_completed": stats["successful_executions"]
            + stats["failed_executions"],
            "queries_total": stats["total_executions"],
            "current_step": current_step,
            "updated_at": timezone.now().isoformat(),
        }
