"""
Business logic service for SearchExecutionStatusView.

Handles execution monitoring, statistics calculation, and status updates
extracted from the view to maintain single responsibility.
"""

import logging

from ...models import SearchExecution
from ..statistics_service import ExecutionStatisticsService

logger = logging.getLogger(__name__)


class StatusViewService:
    """Service for execution status view business logic."""

    def __init__(self):
        self.stats_service = ExecutionStatisticsService()

    def get_execution_data(self, session):
        """
        Get comprehensive execution data for status display.

        Args:
            session: The search session object

        Returns:
            dict: Execution data including statistics and status
        """
        # Get all executions for this session
        executions = (
            SearchExecution.objects.filter(query__session_id=session.id)
            .select_related("query")
            .order_by("-created_at")
        )

        # Calculate enhanced statistics
        stats = self.stats_service.calculate_enhanced_statistics(
            executions, str(session.id)
        )

        # Get failed executions info
        failed_executions = executions.filter(status="failed")

        # Check if any executions are still running
        has_running = executions.filter(status__in=["pending", "running"]).exists()

        return {
            "executions": executions,
            "stats": stats,
            "failed_executions": failed_executions,
            "has_running": has_running,
            "refresh_interval": 5000 if has_running else 0,  # 5 seconds if running
        }

    def should_auto_refresh(self, executions):
        """
        Determine if the page should auto-refresh based on execution status.

        Args:
            executions: QuerySet of SearchExecution objects

        Returns:
            bool: True if page should auto-refresh
        """
        return executions.filter(status__in=["pending", "running"]).exists()
