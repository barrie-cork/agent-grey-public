"""
Connection metrics aggregation service.

Replaces large inline methods in monitoring views with a focused,
cacheable service for collecting connection and API metrics.
"""

from typing import Any, Dict, List

from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.core.services.base import BaseService
from apps.core.types.monitoring_types import ApiCallData, ConnectionMetricsData


class ConnectionMetricsConfig(Dict[str, Any]):
    """Configuration for connection metrics aggregation."""

    cache_timeout: int
    api_timeout_seconds: int
    error_rate_threshold: float
    connection_timeout_seconds: int


class ConnectionMetricsAggregator(BaseService[ConnectionMetricsConfig]):
    """
    Aggregates connection and API metrics for monitoring dashboards.

    Replaces large inline methods from monitoring views with a focused,
    testable, and cacheable service for tracking connection health.
    """

    SERVICE_NAME = "ConnectionMetricsAggregator"
    SERVICE_VERSION = "1.0.0"

    def _initialize(self) -> None:
        """Initialize the connection metrics aggregator."""
        self.cache_timeout = self.config.get("cache_timeout", 120)  # 2 minutes default
        self.api_timeout_seconds = self.config.get("api_timeout_seconds", 30)
        self.error_rate_threshold = self.config.get("error_rate_threshold", 0.05)  # 5%
        self.connection_timeout_seconds = self.config.get(
            "connection_timeout_seconds", 10
        )

    def health_check(self) -> bool:
        """Check if the service can access required dependencies."""
        try:
            self.get_cached_value("health_check_test")
            self.set_cached_value("health_check_test", "ok", timeout=1)
            return True
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False

    def get_default_config(self) -> ConnectionMetricsConfig:
        """Get default configuration."""
        return ConnectionMetricsConfig(
            cache_timeout=120,
            api_timeout_seconds=30,
            error_rate_threshold=0.05,
            connection_timeout_seconds=10,
        )

    def get_metrics(self, hours_back: int = 24) -> ConnectionMetricsData:
        """
        Get aggregated connection metrics.

        Args:
            hours_back: Number of hours to look back for metrics

        Returns:
            ConnectionMetricsData with aggregated metrics
        """
        cache_key = f"connection_metrics_{hours_back}h"

        # Check cache first
        cached_metrics = self.get_cached_value(cache_key)
        if cached_metrics:
            return cached_metrics

        # Generate fresh metrics
        with self._measure_performance("get_connection_metrics"):
            try:
                metrics = self._collect_connection_metrics(hours_back)

                # Cache the results
                self.set_cached_value(cache_key, metrics)

                return metrics

            except Exception as e:
                self._handle_error(
                    e, {"hours_back": hours_back}, "get_connection_metrics"
                )
                # Return empty metrics on error
                return self._get_empty_metrics()

    def _collect_connection_metrics(self, hours_back: int) -> ConnectionMetricsData:
        """Collect connection metrics from the database.

        Note: ApiCallLog model has been removed. Returns empty metrics until
        a replacement logging mechanism is implemented.
        """
        return self._get_empty_metrics()

    def _calculate_avg_response_time(self, api_calls_qs: Any) -> float:
        """Calculate average response time for API calls."""
        response_times = api_calls_qs.filter(
            response_time_ms__isnull=False
        ).values_list("response_time_ms", flat=True)

        if not response_times:
            return 0.0

        return sum(response_times) / len(response_times)

    def _get_api_call_distribution(self, api_calls_qs: Any) -> List[ApiCallData]:
        """Get the distribution of API calls by endpoint."""
        distribution_data = (
            api_calls_qs.values("endpoint")
            .annotate(
                count=Count("id"),
                avg_response_time=Avg("response_time_ms"),
                success_rate=Count("id", filter=Q(status_code__range=(200, 299)))
                * 100.0
                / Count("id"),
            )
            .order_by("-count")[:10]
        )  # Top 10 endpoints

        distribution = []
        for item in distribution_data:
            distribution.append(
                ApiCallData(
                    endpoint=item["endpoint"] or "unknown",
                    call_count=item["count"],
                    avg_response_time_ms=item["avg_response_time"] or 0.0,
                    success_rate=item["success_rate"] or 0.0,
                )
            )

        return distribution

    def _check_connection_health(self) -> bool:
        """Check the health of external connections.

        Note: ApiCallLog model has been removed. Returns True (healthy)
        until a replacement logging mechanism is implemented.
        """
        return True

    def _get_empty_metrics(self) -> ConnectionMetricsData:
        """Return empty metrics structure."""
        return ConnectionMetricsData(
            api_calls_last_hour=0,
            api_calls_last_24h=0,
            successful_calls=0,
            failed_calls=0,
            avg_response_time_ms=0.0,
            api_call_distribution=[],
            api_error_rate=0.0,
            timeout_errors=0,
            connection_healthy=True,
        )

    def get_detailed_metrics(self, hours_back: int = 24) -> Dict[str, Any]:
        """
        Get detailed connection metrics with additional diagnostic data.

        Args:
            hours_back: Number of hours to look back

        Returns:
            Dictionary with detailed metrics
        """
        basic_metrics = self.get_metrics(hours_back)

        # Add additional detailed metrics
        detailed_metrics = dict(basic_metrics)
        detailed_metrics.update(
            {
                "collection_timestamp": timezone.now().isoformat(),
                "cache_hit": bool(
                    self.get_cached_value(f"connection_metrics_{hours_back}h")
                ),
                "service_metrics": self.metrics.get_stats(),
                "error_threshold_exceeded": basic_metrics["api_error_rate"]
                > self.error_rate_threshold,
                "has_timeout_errors": basic_metrics["timeout_errors"] > 0,
                "connection_status": (
                    "healthy" if basic_metrics["connection_healthy"] else "degraded"
                ),
            }
        )

        return detailed_metrics

    def get_api_health_summary(self) -> Dict[str, Any]:
        """Get a quick summary of API health status.

        Note: ApiCallLog model has been removed. Returns no-data status
        until a replacement logging mechanism is implemented.
        """
        cache_key = "api_health_summary"

        cached_summary = self.get_cached_value(cache_key)
        if cached_summary:
            return cached_summary

        summary = {
            "status": "no_data",
            "success_rate": 100.0,
            "avg_response_time_ms": 0.0,
            "total_calls_30min": 0,
            "timestamp": timezone.now().isoformat(),
        }

        self.set_cached_value(cache_key, summary, timeout=60)
        return summary
