"""
Health check views for monitoring.

This module provides health check endpoints for uptime monitoring services
and system health verification.
"""

import logging
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from apps.core.services.health_check import (
    check_cache_health,
    check_celery_health,
    check_database_health,
)
from apps.review_manager.models import SearchSession

logger = logging.getLogger(__name__)


class HealthCheckView(View):
    """
    Health check endpoint for uptime monitoring services.

    Returns system health status for monitoring tools like UptimeRobot.
    Implements the health check requirements from Issue #85.
    """

    def get(self, request) -> JsonResponse:
        """
        Return system health status.

        Returns:
            JsonResponse: Health status with HTTP 200 for healthy, 503 for degraded
        """
        from apps.core.types.api_responses import HealthCheckResponse

        # Check individual components
        components = {
            "database": check_database_health(),
            "cache": check_cache_health(),
            "celery": check_celery_health(),
        }

        # Check for stuck sessions (Issue #83 requirement)
        stuck_count = SearchSession.objects.filter(
            status__in=["executing", "processing_results"],
            updated_at__lt=timezone.now() - timedelta(minutes=30),
        ).count()

        # Determine overall status and HTTP status code
        failed_components = [name for name, status in components.items() if not status]

        if not failed_components and stuck_count == 0:
            health_status = "healthy"
            status_code = 200
            issues = None
        elif len(failed_components) <= 1 and stuck_count < 5:
            health_status = "degraded"
            status_code = 200  # Still operational
            issues = []
            if failed_components:
                issues.append(f"{failed_components[0]} is not responding")
            if stuck_count > 0:
                issues.append(f"{stuck_count} sessions are stuck")
        else:
            health_status = "critical"
            status_code = 503  # Service unavailable
            issues = []
            if failed_components:
                issues.append(
                    f"Multiple components failing: {', '.join(failed_components)}"
                )
            if stuck_count >= 5:
                issues.append(f"High number of stuck sessions: {stuck_count}")

        health: HealthCheckResponse = {
            "status": health_status,
            "timestamp": timezone.now().isoformat(),
            "components": components,
            "stuck_sessions": stuck_count,
            "issues": issues,
        }

        return JsonResponse(health, status=status_code)
