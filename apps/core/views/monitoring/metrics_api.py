"""
Metrics API views for monitoring.

This module provides API endpoints for connection metrics.
"""

import logging

from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from apps.core.services.aggregators.connection_metrics import (
    ConnectionMetricsAggregator,
)

logger = logging.getLogger(__name__)


class ConnectionMonitoringAPI(UserPassesTestMixin, View):
    """
    API endpoint for real-time database connection monitoring using ConnectionMetricsAggregator.

    Provides connection metrics including API call statistics and connection health.
    Updated to use service aggregator pattern as per PRP refactoring plan.
    """

    def __init__(self):
        """Initialize connection metrics aggregator."""
        super().__init__()
        self.connection_aggregator = ConnectionMetricsAggregator()

    def test_func(self):
        """Only staff users can access connection monitoring."""
        return self.request.user.is_staff

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """Return connection metrics as JSON using aggregator service."""

        try:
            # Get metrics from aggregator service
            connection_data = self.connection_aggregator.get_metrics(hours_back=24)

            # Format for API response
            base_metrics = {
                "api_calls_last_hour": connection_data["api_calls_last_hour"],
                "api_calls_last_24h": connection_data["api_calls_last_24h"],
                "successful_calls": connection_data["successful_calls"],
                "failed_calls": connection_data["failed_calls"],
                "avg_response_time_ms": connection_data["avg_response_time_ms"],
                "api_error_rate": connection_data["api_error_rate"],
                "timeout_errors": connection_data["timeout_errors"],
                "connection_healthy": connection_data["connection_healthy"],
                "api_call_distribution": connection_data["api_call_distribution"][
                    :5
                ],  # Top 5 only
                "timestamp": timezone.now().isoformat(),
            }

            # Determine status based on error rate and health
            if (
                connection_data["api_error_rate"] > 20
                or not connection_data["connection_healthy"]
            ):
                base_metrics["status"] = "critical"
                base_metrics["recommendation"] = (
                    "Critical: High API error rate or connection issues detected."
                )
            elif connection_data["api_error_rate"] > 10:
                base_metrics["status"] = "warning"
                base_metrics["recommendation"] = (
                    "Warning: Elevated API error rate detected."
                )
            else:
                base_metrics["status"] = "healthy"
                base_metrics["recommendation"] = (
                    "Healthy: API connections within normal parameters."
                )

            metrics = base_metrics
            return JsonResponse(metrics)

        except Exception as e:
            logger.error(f"ConnectionMonitoringAPI failed: {e}")
            # Return error response
            error_metrics = {
                "status": "error",
                "api_calls_last_hour": 0,
                "api_calls_last_24h": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "avg_response_time_ms": 0.0,
                "api_error_rate": 0.0,
                "timeout_errors": 0,
                "connection_healthy": False,
                "api_call_distribution": [],
                "timestamp": timezone.now().isoformat(),
                "recommendation": "Error: Unable to collect connection metrics.",
            }
            return JsonResponse(error_metrics, status=500)
