"""
Performance tracking middleware for automatic view monitoring.

Tracks execution time and database queries for all views,
feeding data into the performance monitoring system.
"""

import time

import structlog
from django.conf import settings
from django.urls import resolve
from django.urls.exceptions import Resolver404

from apps.core.monitoring.performance import PerformanceMonitor

logger = structlog.get_logger(__name__)


class PerformanceTrackingMiddleware:
    """
    Middleware to automatically track performance of all views.

    Features:
    - Automatic view performance tracking
    - Excludes static files and media
    - Tracks only authenticated requests (configurable)
    - Adds performance headers to responses
    - Conditional tracking for optimised review paths
    """

    # Paths to exclude from tracking
    EXCLUDED_PATHS = [
        "/static/",
        "/media/",
        "/favicon.ico",
        "/robots.txt",
        "/__debug__/",
        "/admin/jsi18n/",  # Django admin JS
    ]

    # Paths that need minimal tracking (unless in debug mode)
    LIGHT_TRACKING_PATHS = [
        "/review_results/",  # Review interfaces - already optimised
        "/health/",  # Health checks
    ]

    def __init__(self, get_response):
        self.get_response = get_response

        # Check if performance monitoring is enabled
        self.enabled = getattr(settings, "PERFORMANCE_MONITORING", {}).get(
            "ENABLED", True
        )
        self.track_anonymous = getattr(settings, "PERFORMANCE_MONITORING", {}).get(
            "TRACK_ANONYMOUS", False
        )

    def __call__(self, request):  # noqa: C901 - Performance tracking
        """Process the request and track performance."""
        # Skip if monitoring is disabled
        if not self.enabled:
            return self.get_response(request)

        # Skip excluded paths
        if self._should_skip(request):
            return self.get_response(request)

        # Light tracking: skip performance tracking for optimised paths unless in debug mode
        if not settings.DEBUG and self._is_light_tracking_path(request):
            return self.get_response(request)

        # Skip if user is not authenticated and we're not tracking anonymous
        if not request.user.is_authenticated and not self.track_anonymous:
            return self.get_response(request)

        # Get view name from URL resolver
        view_name = self._get_view_name(request)
        if not view_name:
            return self.get_response(request)

        # Prepare metadata
        metadata = {
            "path": request.path,
            "method": request.method,
            "is_ajax": request.headers.get("X-Requested-With") == "XMLHttpRequest",
        }

        if request.user.is_authenticated:
            metadata["user_id"] = str(request.user.id)
            metadata["is_staff"] = request.user.is_staff

        # Track performance with error handling
        start_time = time.time()

        try:
            with PerformanceMonitor.track(
                f"view:{view_name}", metadata
            ) as operation_id:
                response = self.get_response(request)

                # Add performance headers (useful for debugging)
                if settings.DEBUG or (
                    request.user.is_authenticated and request.user.is_staff
                ):
                    duration = time.time() - start_time
                    response["X-View-Time"] = f"{duration:.3f}s"
                    response["X-View-Name"] = view_name
                    response["X-Operation-ID"] = operation_id

        except Exception as e:
            # If performance monitoring fails, continue without it
            logger.warning(
                "performance_monitoring_failed",
                view_name=view_name,
                error=str(e),
            )
            response = self.get_response(request)

            # Still add timing header if possible
            if settings.DEBUG or (
                request.user.is_authenticated and request.user.is_staff
            ):
                duration = time.time() - start_time
                response["X-View-Time"] = f"{duration:.3f}s"
                response["X-View-Name"] = view_name
                response["X-Performance-Error"] = "monitoring-failed"

        return response

    def _should_skip(self, request):
        """Check if request should be skipped from tracking."""
        path = request.path

        # Skip excluded paths
        for excluded in self.EXCLUDED_PATHS:
            if path.startswith(excluded):
                return True

        # Skip OPTIONS requests
        if request.method == "OPTIONS":
            return True

        return False

    def _is_light_tracking_path(self, request):
        """Check if request is for a light-tracking path."""
        path = request.path

        for light_path in self.LIGHT_TRACKING_PATHS:
            if path.startswith(light_path):
                return True

        return False

    def _get_view_name(self, request):
        """Get view name from URL resolver."""
        try:
            resolver_match = resolve(request.path)
            if resolver_match:
                # Get the view name
                if resolver_match.url_name:
                    # Use URL name if available
                    if resolver_match.namespace:
                        return f"{resolver_match.namespace}:{resolver_match.url_name}"
                    return resolver_match.url_name
                elif resolver_match.view_name:
                    # Fall back to view name
                    return resolver_match.view_name
                else:
                    # Use function name as last resort
                    return resolver_match.func.__name__
        except Resolver404:
            # URL not found - will result in 404
            return "404_not_found"
        except Exception as e:
            logger.debug(f"Error resolving view name for {request.path}: {e}")
            return None


class SlowQueryLoggingMiddleware:
    """
    Middleware to log slow database queries.

    Works in conjunction with Django's database query logging
    to identify and log queries that exceed threshold.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = settings.DEBUG and getattr(
            settings, "PERFORMANCE_MONITORING", {}
        ).get("TRACK_QUERIES", True)
        self.threshold = getattr(settings, "PERFORMANCE_MONITORING", {}).get(
            "SLOW_QUERY_THRESHOLD", 0.5
        )

    def __call__(self, request):
        """Process request and check for slow queries."""
        if not self.enabled:
            return self.get_response(request)

        # Import here to avoid issues if not in DEBUG mode
        from django.db import connection

        # Reset queries before request
        connection.queries_log.clear()

        response = self.get_response(request)

        # Check for slow queries
        slow_queries = []
        for query in connection.queries:
            try:
                time_float = float(query.get("time", 0))
                if time_float > self.threshold:
                    slow_queries.append(
                        {
                            "sql": query["sql"],
                            "time": time_float,
                        }
                    )
            except (ValueError, TypeError):
                continue

        # Log slow queries
        if slow_queries:
            logger.warning(
                f"Slow queries detected on {request.path}: "
                f"{len(slow_queries)} queries exceeded {self.threshold}s threshold"
            )
            for i, query in enumerate(slow_queries[:3]):  # Log first 3
                logger.warning(
                    f"Slow query #{i + 1} ({query['time']}s): {query['sql'][:200]}..."
                )

        return response
