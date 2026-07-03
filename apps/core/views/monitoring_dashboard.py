"""
Unified monitoring dashboard view for Phase 2 monitoring consolidation.

Provides real-time visibility into:
- Circuit breaker status
- Monitoring metrics
- Database connections
- System health
"""

import json
import logging
from datetime import datetime

from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.db import connections
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


@method_decorator(staff_member_required, name="dispatch")
class UnifiedMonitoringDashboard(TemplateView):
    """
    Unified monitoring dashboard showing real-time system metrics.

    Displays:
    - Circuit breaker status for all services
    - Latest monitoring run metrics
    - Database connection usage
    - Overall system health
    """

    template_name = "core/monitoring/unified_dashboard.html"

    def get_context_data(self, **kwargs):
        """Gather all monitoring data for dashboard display."""
        context = super().get_context_data(**kwargs)

        # Get monitor metrics from cache
        metrics = cache.get("monitor_metrics", {})

        # Get circuit breaker status
        circuit_status = self._get_circuit_breaker_status()

        # Get database connection status
        db_status = self._get_database_status()

        # Check overall health
        is_healthy = self._check_health(metrics)

        # Get monitoring history for charts
        history = self._get_monitoring_history()

        # Add rate limiter status
        try:
            from apps.serp_execution.services.rate_limiter import get_rate_limiter

            rate_limiter = get_rate_limiter()
            context["rate_limiter"] = rate_limiter.get_status("serper_api")
        except Exception as e:
            logger.warning(f"Could not get rate limiter status: {e}")
            context["rate_limiter"] = {"error": "Unable to fetch status"}

        context["celery_stats"] = self._get_celery_stats()

        context.update(
            {
                "monitor_metrics": metrics,
                "circuit_breakers": circuit_status,
                "db_connections": db_status,
                "is_healthy": is_healthy,
                "health_status": "healthy" if is_healthy else "warning",
                "last_run": metrics.get("last_run", "Never"),
                "next_run": self._calculate_next_run(metrics),
                "history": json.dumps(history),
                "stuck_sessions": self._get_stuck_sessions_count(),
                "failure_rate": self._calculate_failure_rate(metrics),
            }
        )

        return context

    def _get_circuit_breaker_status(self):
        """Get enhanced status of all circuit breakers with statistics."""
        try:
            from apps.core.services.circuit_breaker import (
                DynamicCircuitBreaker,
                database_circuit_breaker,
                serper_circuit_breaker,
            )

            # Get detailed statistics for each breaker
            serper_stats = DynamicCircuitBreaker.get_breaker_status("serper_api")
            database_stats = DynamicCircuitBreaker.get_breaker_status("database")

            circuit_status = {
                "serper_api": {
                    "name": "Serper API",
                    "state": serper_circuit_breaker.state.name,
                    "failures": serper_circuit_breaker.fail_counter,
                    "is_open": serper_circuit_breaker.state.name == "open",
                    "is_closed": serper_circuit_breaker.state.name == "closed",
                    "is_half_open": serper_circuit_breaker.state.name == "half-open",
                    "statistics": serper_stats,
                    "time_in_open": serper_stats.get("time_in_open_state", 0),
                    "recent_changes": serper_stats.get("recent_state_changes", [])[:3],
                    "daily_failures": serper_stats.get("daily_failures", {}),
                },
                "database": {
                    "name": "Database",
                    "state": database_circuit_breaker.state.name,
                    "failures": database_circuit_breaker.fail_counter,
                    "is_open": database_circuit_breaker.state.name == "open",
                    "is_closed": database_circuit_breaker.state.name == "closed",
                    "is_half_open": database_circuit_breaker.state.name == "half-open",
                    "statistics": database_stats,
                    "time_in_open": database_stats.get("time_in_open_state", 0),
                    "recent_changes": database_stats.get("recent_state_changes", [])[
                        :3
                    ],
                    "daily_failures": database_stats.get("daily_failures", {}),
                },
            }
        except Exception as e:
            logger.warning(f"Could not get circuit breaker status: {e}")
            circuit_status = {
                "serper_api": {
                    "name": "Serper API",
                    "state": "unknown",
                    "failures": 0,
                    "is_open": False,
                    "is_closed": False,
                    "is_half_open": False,
                },
                "database": {
                    "name": "Database",
                    "state": "unknown",
                    "failures": 0,
                    "is_open": False,
                    "is_closed": False,
                    "is_half_open": False,
                },
            }

        return circuit_status

    def _get_database_status(self):
        """Get database connection pool status."""
        try:
            # Try pg_stat_activity first (requires permissions)
            with connections["default"].cursor() as cursor:
                cursor.execute(
                    """
                    SELECT count(*) as active_connections
                    FROM pg_stat_activity
                    WHERE state != 'idle'
                    AND pid != pg_backend_pid()
                """
                )
                result = cursor.fetchone()
                active_connections = result[0] if result else 0
        except Exception as e:
            # Fallback to Django's connection introspection
            logger.info(f"Using fallback connection counting: {e}")
            active_connections = len(
                [
                    c
                    for c in connections.all()
                    if hasattr(c, "queries_logged") and c.queries_logged > 0
                ]
            )

        max_connections = 22  # DigitalOcean's limit

        return {
            "active": active_connections,
            "max": max_connections,
            "percentage": round((active_connections / max_connections) * 100, 1),
            "status": self._get_connection_status(active_connections, max_connections),
        }

    def _get_connection_status(self, active, max_conn):
        """Determine connection pool health status."""
        percentage = (active / max_conn) * 100

        if percentage < 60:
            return "healthy"
        elif percentage < 80:
            return "warning"
        else:
            return "critical"

    def _check_health(self, metrics):
        """Check if monitoring is healthy."""
        if not metrics:
            return False

        last_run = metrics.get("last_run")
        if not last_run:
            return False

        try:
            # Parse the ISO format timestamp
            if isinstance(last_run, str):
                last_run_time = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
            else:
                last_run_time = last_run

            # Check if ran within last 60 seconds
            time_since = (timezone.now() - last_run_time).total_seconds()
            return time_since < 60
        except Exception as e:
            logger.warning(f"Error checking health: {e}")
            return False

    def _calculate_next_run(self, metrics):
        """Calculate when the next monitoring run will occur."""
        if not metrics or "last_run" not in metrics:
            return "Unknown"

        try:
            last_run = metrics["last_run"]
            if isinstance(last_run, str):
                last_run_time = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
            else:
                last_run_time = last_run

            # Monitor runs every 30 seconds
            time_since = (timezone.now() - last_run_time).total_seconds()
            seconds_until_next = max(0, 30 - (time_since % 30))

            if seconds_until_next == 0:
                return "Any moment"
            elif seconds_until_next < 10:
                return f"In {int(seconds_until_next)} seconds"
            else:
                return f"In {int(seconds_until_next)} seconds"
        except Exception as e:
            logger.warning(f"Error calculating next run: {e}")
            return "Unknown"

    def _get_monitoring_history(self):
        """Get historical monitoring data for charts."""
        history_key = f"monitor_history:{timezone.now().strftime('%Y%m%d%H')}"
        history = cache.get(history_key, [])

        # Format for chart display
        formatted_history = []
        for entry in history[-20:]:  # Last 20 entries
            formatted_history.append(
                {
                    "time": entry.get("last_run", ""),
                    "sessions_checked": entry.get("sessions_checked", 0),
                    "stuck_fixed": entry.get("stuck_fixed", 0),
                    "failed_marked": entry.get("failed_marked", 0),
                    "run_time": entry.get("monitor_run_time", 0),
                }
            )

        return formatted_history

    def _get_stuck_sessions_count(self):
        """Get count of currently stuck sessions."""
        try:
            from datetime import timedelta

            from apps.review_manager.models import SearchSession

            stuck_count = SearchSession.objects.filter(
                state__in=["executing", "processing_results"],
                updated_at__lt=timezone.now() - timedelta(minutes=5),
            ).count()

            return stuck_count
        except Exception as e:
            logger.warning(f"Error counting stuck sessions: {e}")
            return 0

    def _calculate_failure_rate(self, metrics):
        """Calculate the failure rate from metrics."""
        if not metrics:
            return 0

        sessions_checked = metrics.get("sessions_checked", 0)
        failed_marked = metrics.get("failed_marked", 0)

        if sessions_checked == 0:
            return 0

        return round((failed_marked / sessions_checked) * 100, 1)

    def _get_celery_stats(self):
        """Get Celery queue statistics."""
        # Simplified - would need Celery inspect in production
        return {"status": "Celery monitoring available at /flower/"}
