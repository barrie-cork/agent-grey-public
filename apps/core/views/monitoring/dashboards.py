"""
Monitoring dashboard views.

This module provides the main monitoring dashboard interface for administrators,
displaying system health, workflow statistics, and performance metrics.
"""

import logging
from datetime import timedelta

from django.contrib.auth.mixins import UserPassesTestMixin
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.core.monitoring.performance import PerformanceMonitor
from apps.core.services.aggregators.connection_metrics import (
    ConnectionMetricsAggregator,
)
from apps.core.services.aggregators.system_health import SystemHealthAggregator
from apps.core.services.aggregators.workflow_stats import WorkflowStatsAggregator
from apps.core.services.health_check import (
    check_cache_health,
    check_celery_health,
    check_database_health,
)
from apps.review_manager.models import SearchSession, SessionActivity

logger = logging.getLogger(__name__)


class WorkflowMonitoringDashboard(UserPassesTestMixin, TemplateView):
    """
    Real-time workflow monitoring dashboard for administrators.

    Provides:
    - System health overview (via SystemHealthAggregator)
    - Performance metrics
    - Workflow statistics (via WorkflowStatsAggregator)
    - Connection metrics (via ConnectionMetricsAggregator)
    - Recent activities
    - Stuck session detection

    Updated to use service aggregator pattern as per PRP refactoring plan.
    """

    template_name = "core/monitoring/dashboard.html"

    def __init__(self):
        """Initialize aggregator services."""
        super().__init__()
        self.workflow_aggregator = WorkflowStatsAggregator()
        self.connection_aggregator = ConnectionMetricsAggregator()
        self.health_aggregator = SystemHealthAggregator()

    def test_func(self):
        """Only staff users can access monitoring dashboard."""
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        """Gather comprehensive monitoring data using service aggregators."""
        context = super().get_context_data(**kwargs)

        # Time windows for analysis
        now = timezone.now()
        last_week = now - timedelta(days=7)

        # 1. System Health Check (using SystemHealthAggregator)
        context["system_health"] = self._get_system_health_via_aggregator()

        # 2. Workflow Statistics (using WorkflowStatsAggregator)
        context["workflow_stats"] = self._get_workflow_stats_via_aggregator()

        # 3. Performance Metrics
        context["performance_metrics"] = PerformanceMonitor.get_dashboard_metrics()

        # 4. Recent Activities
        context["recent_activities"] = self._get_recent_activities()

        # 5. Stuck Sessions
        context["stuck_sessions"] = self._get_stuck_sessions()

        # 6. Resource Utilization (using ConnectionMetricsAggregator)
        context["resource_stats"] = self._get_resource_stats_via_aggregator()

        # 7. Trend Analysis
        context["trends"] = self._get_trend_analysis(last_week)

        return context

    def _get_system_health_via_aggregator(self):
        """
        Get system health using SystemHealthAggregator service.

        Returns:
            dict: Health status with components and issues, formatted for template compatibility
        """
        try:
            # Get comprehensive health data from aggregator
            health_data = self.health_aggregator.get_health_data(include_detailed=False)

            # Convert SystemHealthData to template-compatible format
            template_health = {
                "overall_status": self._convert_health_status(
                    health_data.overall_health_score
                ),
                "components": self._convert_service_statuses(
                    health_data.service_statuses
                ),
                "issues": [alert["message"] for alert in health_data.alerts],
                "health_score": health_data.overall_health_score,
                "resource_usage": health_data.resource_usage,
                "last_updated": health_data.last_updated.isoformat(),
            }

            return template_health

        except Exception as e:
            logger.error(f"SystemHealthAggregator failed: {e}")
            # Fallback to legacy health check
            return self._legacy_health_check()

    def _convert_health_status(self, health_score: float) -> str:
        """Convert numeric health score to status string."""
        if health_score >= 80:
            return "healthy"
        elif health_score >= 50:
            return "warning"
        else:
            return "critical"

    def _convert_service_statuses(self, service_statuses) -> dict:
        """Convert service status list to dictionary for template compatibility."""
        return {
            service.name.lower(): service.status == "healthy"
            for service in service_statuses
        }

    def _legacy_health_check(self):
        """Legacy health check as fallback."""
        components = {
            "database": check_database_health(),
            "cache": check_cache_health(),
            "celery": check_celery_health(),
        }

        failed_components = [name for name, status in components.items() if not status]

        return {
            "overall_status": "healthy" if not failed_components else "critical",
            "components": components,
            "issues": (
                [f"Failed components: {', '.join(failed_components)}"]
                if failed_components
                else []
            ),
        }

    def _get_workflow_stats_via_aggregator(self):
        """
        Get workflow statistics using WorkflowStatsAggregator service.

        Returns:
            dict: Workflow statistics formatted for template compatibility
        """
        try:
            # Get comprehensive stats from aggregator (24h lookback)
            stats_data = self.workflow_aggregator.get_stats(hours_back=24)

            # Convert WorkflowStatsData to template-compatible format
            template_stats = {
                "sessions_last_hour": stats_data["sessions_last_hour"],
                "sessions_last_24h": stats_data["sessions_last_24h"],
                "status_distribution": dict(
                    stats_data["status_distribution"]
                ),  # Convert TypedDict to dict
                "avg_completion_time_hours": stats_data["avg_completion_time_hours"],
                "error_rate_24h": stats_data["error_rate_24h"],
                "total_active_sessions": stats_data.get("processing_sessions", 0),
                "stuck_sessions": stats_data.get("stuck_sessions", 0),
                # Add total sessions count for compatibility
                "total_sessions": SearchSession.objects.count(),
            }

            return template_stats

        except Exception as e:
            logger.error(f"WorkflowStatsAggregator failed: {e}")
            # Fallback to simple stats
            return self._legacy_workflow_stats()

    def _legacy_workflow_stats(self):
        """Legacy workflow stats as fallback."""
        now = timezone.now()
        last_hour = now - timedelta(hours=1)
        last_24h = now - timedelta(hours=24)

        return {
            "sessions_last_hour": SearchSession.objects.filter(
                updated_at__gte=last_hour
            ).count(),
            "sessions_last_24h": SearchSession.objects.filter(
                updated_at__gte=last_24h
            ).count(),
            "status_distribution": dict(
                SearchSession.objects.values("status")
                .annotate(count=Count("id"))
                .values_list("status", "count")
            ),
            "avg_completion_time_hours": 0.0,
            "error_rate_24h": 0.0,
            "total_active_sessions": SearchSession.objects.filter(
                status__in=["executing", "processing_results", "under_review"]
            ).count(),
            "total_sessions": SearchSession.objects.count(),
        }

    def _get_resource_stats_via_aggregator(self):
        """
        Get resource statistics using ConnectionMetricsAggregator service.

        Returns:
            dict: Resource usage data including database and performance metrics
        """
        try:
            # Get connection metrics from aggregator
            connection_data = self.connection_aggregator.get_metrics(hours_back=24)

            # Get performance metrics
            perf_metrics = PerformanceMonitor.get_dashboard_metrics()

            # Convert to template-compatible format
            template_stats = {
                "database": {
                    "total_sessions": SearchSession.objects.count(),
                    "total_activities": SessionActivity.objects.count(),
                    "avg_queries_per_operation": {},  # Could be enhanced with aggregator data
                    "connections": {
                        "api_calls_last_hour": connection_data["api_calls_last_hour"],
                        "api_calls_last_24h": connection_data["api_calls_last_24h"],
                        "successful_calls": connection_data["successful_calls"],
                        "failed_calls": connection_data["failed_calls"],
                        "avg_response_time_ms": connection_data["avg_response_time_ms"],
                        "api_error_rate": connection_data["api_error_rate"],
                        "connection_healthy": connection_data["connection_healthy"],
                    },
                },
                "performance": {
                    "health_score": perf_metrics.get("health_score", 0),
                    "total_operations": perf_metrics.get("total_operations", 0),
                    "slow_operations": perf_metrics.get("total_slow_operations", 0),
                },
                "api_metrics": {
                    "call_distribution": connection_data["api_call_distribution"],
                    "timeout_errors": connection_data["timeout_errors"],
                },
            }

            return template_stats

        except Exception as e:
            logger.error(f"ConnectionMetricsAggregator failed: {e}")
            # Fallback to legacy resource stats
            return self._legacy_resource_stats()

    def _legacy_resource_stats(self):
        """Legacy resource stats as fallback."""
        perf_metrics = PerformanceMonitor.get_dashboard_metrics()

        return {
            "database": {
                "total_sessions": SearchSession.objects.count(),
                "total_activities": SessionActivity.objects.count(),
                "avg_queries_per_operation": {},
                "connections": {"connection_healthy": True},
            },
            "performance": {
                "health_score": perf_metrics.get("health_score", 0),
                "total_operations": perf_metrics.get("total_operations", 0),
                "slow_operations": perf_metrics.get("total_slow_operations", 0),
            },
        }

    def _get_recent_activities(self, limit=20):
        """
        Get recent session activities.

        Args:
            limit: Number of activities to return

        Returns:
            List of recent activities
        """
        activities = SessionActivity.objects.select_related("session", "user").order_by(
            "-created_at"
        )[:limit]

        return [
            {
                "id": str(activity.id),
                "session_id": str(activity.session.id),
                "session_title": activity.session.title,
                "activity_type": activity.activity_type,
                "type_display": activity.get_activity_type_display(),
                "description": activity.description,
                "user": activity.user.username if activity.user else "System",
                "created_at": activity.created_at,
                "time_ago": timezone.now() - activity.created_at,
            }
            for activity in activities
        ]

    def _get_stuck_sessions(self):
        """
        Identify sessions that appear to be stuck.

        Returns:
            List of stuck session details
        """
        threshold_times = {
            "executing": timedelta(hours=2),
            "processing_results": timedelta(hours=1),
            "ready_to_execute": timedelta(days=7),
        }

        stuck_sessions = []

        for status, threshold in threshold_times.items():
            cutoff = timezone.now() - threshold
            sessions = SearchSession.objects.filter(
                status=status, updated_at__lt=cutoff
            ).select_related("owner")

            for session in sessions:
                stuck_duration = timezone.now() - session.updated_at
                stuck_sessions.append(
                    {
                        "id": str(session.id),
                        "title": session.title,
                        "status": session.status,
                        "owner": session.owner.username,
                        "stuck_duration": stuck_duration,
                        "stuck_hours": stuck_duration.total_seconds() / 3600,
                        "last_updated": session.updated_at,
                    }
                )

        # Sort by how long they've been stuck
        stuck_sessions.sort(key=lambda x: x["stuck_hours"], reverse=True)

        return stuck_sessions[:10]  # Top 10 most stuck

    def _get_trend_analysis(self, since):
        """
        Analyze trends over time period.

        Args:
            since (datetime): Start date for trend analysis

        Returns:
            dict: Trend data including sessions by day and activities by type
        """
        # Sessions created per day
        sessions_by_day = (
            SearchSession.objects.filter(created_at__gte=since)
            .extra(select={"day": "date(created_at)"})
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )

        # Activities by type
        activities_by_type = dict(
            SessionActivity.objects.filter(created_at__gte=since)
            .values("activity_type")
            .annotate(count=Count("id"))
            .values_list("activity_type", "count")
        )

        return {
            "sessions_by_day": list(sessions_by_day),
            "activities_by_type": activities_by_type,
            "period_days": (timezone.now() - since).days,
        }


class WorkflowMonitoringAPI(UserPassesTestMixin, TemplateView):
    """
    API endpoint for real-time monitoring updates.

    Returns JSON data for dashboard auto-refresh.
    """

    def test_func(self):
        """Only staff users can access monitoring API."""
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """Return monitoring data as JSON."""
        from apps.core.types.api_responses import MonitoringAPIResponse

        view = WorkflowMonitoringDashboard()
        view.request = request

        # Get the same context data
        context = view.get_context_data()

        # Convert to JSON-serializable format
        response_data: MonitoringAPIResponse = {
            "system_health": context["system_health"],
            "workflow_stats": context["workflow_stats"],
            "recent_activities": [
                {
                    "id": a["id"],
                    "session_title": a["session_title"],
                    "type_display": a["type_display"],
                    "user": a["user"],
                    "time_ago": str(a["time_ago"]),
                }
                for a in context["recent_activities"][:5]  # Only recent 5
            ],
            "stuck_sessions_count": len(context["stuck_sessions"]),
            "timestamp": timezone.now().isoformat(),
        }

        return JsonResponse(response_data)
