"""
Tests for performance tracking middleware.

Tests the PerformanceTrackingMiddleware and SlowQueryLoggingMiddleware:
- Automatic view tracking
- Path exclusion
- Performance headers
- Slow query detection
"""

import time
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core.middleware.performance import (
    PerformanceTrackingMiddleware,
    SlowQueryLoggingMiddleware,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class PerformanceTrackingMiddlewareTests(TestCase):
    """Test PerformanceTrackingMiddleware functionality."""

    def setUp(self):
        """Set up test environment."""
        self.factory = RequestFactory()
        self.user = create_test_user()

        # Mock response function
        def get_response(request):
            time.sleep(0.05)  # Simulate processing time
            return HttpResponse("OK")

        self.middleware = PerformanceTrackingMiddleware(get_response)

    @override_settings(
        PERFORMANCE_MONITORING={"ENABLED": True, "TRACK_ANONYMOUS": False}
    )
    def test_authenticated_request_tracking(self):
        """Test that authenticated requests are tracked."""
        request = self.factory.get("/test-path/")
        request.user = self.user

        with patch(
            "apps.core.monitoring.performance.PerformanceMonitor.track"
        ) as mock_track:
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock(return_value="op-123")
            mock_context.__exit__ = MagicMock(return_value=None)
            mock_track.return_value = mock_context

            _response = self.middleware(request)

            # Should track the request
            mock_track.assert_called_once()
            args, kwargs = mock_track.call_args

            # Verify operation name includes view name
            self.assertIn("view:", args[0])

            # Verify metadata
            metadata = args[1] if len(args) > 1 else kwargs.get("metadata", {})
            self.assertEqual(metadata["path"], "/test-path/")
            self.assertEqual(metadata["method"], "GET")
            self.assertEqual(metadata["user_id"], str(self.user.id))
            self.assertIn("is_staff", metadata)

    @override_settings(
        PERFORMANCE_MONITORING={"ENABLED": True, "TRACK_ANONYMOUS": False}
    )
    def test_anonymous_request_not_tracked(self):
        """Test that anonymous requests are not tracked by default."""
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/test-path/")
        request.user = AnonymousUser()

        with patch(
            "apps.core.monitoring.performance.PerformanceMonitor.track"
        ) as mock_track:
            _response = self.middleware(request)

            # Should not track anonymous requests
            mock_track.assert_not_called()

    @override_settings(
        PERFORMANCE_MONITORING={"ENABLED": True, "TRACK_ANONYMOUS": True}
    )
    def test_anonymous_request_tracked_when_enabled(self):
        """Test that anonymous requests are tracked when enabled."""
        from django.contrib.auth.models import AnonymousUser

        # Re-create middleware after override_settings takes effect
        def get_response(request):
            return HttpResponse("OK")

        middleware = PerformanceTrackingMiddleware(get_response)

        request = self.factory.get("/test-path/")
        request.user = AnonymousUser()

        with patch(
            "apps.core.monitoring.performance.PerformanceMonitor.track"
        ) as mock_track:
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock(return_value="op-123")
            mock_context.__exit__ = MagicMock(return_value=None)
            mock_track.return_value = mock_context

            _response = middleware(request)

            mock_track.assert_called_once()

    def test_excluded_paths(self):
        """Test that excluded paths are not tracked."""
        excluded_paths = [
            "/static/test.css",
            "/media/image.jpg",
            "/favicon.ico",
            "/robots.txt",
            "/__debug__/toolbar/",
            "/admin/jsi18n/",
        ]

        for path in excluded_paths:
            request = self.factory.get(path)
            request.user = self.user

            with patch(
                "apps.core.monitoring.performance.PerformanceMonitor.track"
            ) as mock_track:
                _response = self.middleware(request)

                # Should not track excluded paths
                mock_track.assert_not_called()

    @override_settings(DEBUG=True)
    def test_performance_headers_in_debug(self):
        """Test that performance headers are added in DEBUG mode."""
        request = self.factory.get("/test-path/")
        request.user = self.user

        with patch(
            "apps.core.monitoring.performance.PerformanceMonitor.track"
        ) as mock_track:
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock(return_value="op-123")
            mock_context.__exit__ = MagicMock(return_value=None)
            mock_track.return_value = mock_context

            response = self.middleware(request)

            # Should have performance headers
            self.assertIn("X-View-Time", response)
            self.assertIn("X-View-Name", response)
            self.assertEqual(response["X-Operation-ID"], "op-123")

            # View time should be reasonable
            view_time = float(response["X-View-Time"].rstrip("s"))
            self.assertGreaterEqual(view_time, 0.05)
            self.assertLess(view_time, 1.0)

    @override_settings(DEBUG=False)
    def test_performance_headers_for_staff(self):
        """Test that staff users get performance headers in production."""
        request = self.factory.get("/test-path/")
        request.user = self.user
        request.user.is_staff = True

        response = self.middleware(request)

        # Staff should still get headers
        self.assertIn("X-View-Time", response)

    def test_ajax_request_metadata(self):
        """Test that AJAX requests are tracked with appropriate metadata."""
        request = self.factory.get(
            "/test-path/", HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        request.user = self.user

        with patch(
            "apps.core.monitoring.performance.PerformanceMonitor.track"
        ) as mock_track:
            mock_context = MagicMock()
            mock_context.__enter__ = MagicMock(return_value="op-123")
            mock_context.__exit__ = MagicMock(return_value=None)
            mock_track.return_value = mock_context

            _response = self.middleware(request)

            # Check metadata includes AJAX flag
            args, kwargs = mock_track.call_args
            metadata = args[1] if len(args) > 1 else kwargs.get("metadata", {})
            self.assertTrue(metadata["is_ajax"])

    def test_options_request_not_tracked(self):
        """Test that OPTIONS requests are not tracked."""
        request = self.factory.options("/test-path/")
        request.user = self.user

        with patch(
            "apps.core.monitoring.performance.PerformanceMonitor.track"
        ) as mock_track:
            _response = self.middleware(request)

            # Should not track OPTIONS requests
            mock_track.assert_not_called()

    @override_settings(PERFORMANCE_MONITORING={"ENABLED": False})
    def test_disabled_monitoring(self):
        """Test that monitoring can be disabled."""
        request = self.factory.get("/test-path/")
        request.user = self.user

        # Recreate middleware with new settings
        def get_response(request):
            return HttpResponse("OK")

        middleware = PerformanceTrackingMiddleware(get_response)

        with patch(
            "apps.core.monitoring.performance.PerformanceMonitor.track"
        ) as mock_track:
            _response = middleware(request)

            # Should not track when disabled
            mock_track.assert_not_called()


class SlowQueryLoggingMiddlewareTests(TestCase):
    """Test SlowQueryLoggingMiddleware functionality."""

    def setUp(self):
        """Set up test environment."""
        self.factory = RequestFactory()

        def get_response(request):
            # Simulate database queries
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                # Simulate slow query
                cursor.execute("SELECT pg_sleep(0.6)")
            return HttpResponse("OK")

        self.middleware = SlowQueryLoggingMiddleware(get_response)

    @override_settings(
        DEBUG=True,
        PERFORMANCE_MONITORING={"TRACK_QUERIES": True, "SLOW_QUERY_THRESHOLD": 0.5},
    )
    @patch("apps.core.middleware.performance.logger")
    def test_slow_query_detection(self, mock_logger):
        """Test that slow queries are detected and logged."""
        request = self.factory.get("/test-path/")

        # Create middleware after @override_settings so self.enabled = True
        def get_response(request):
            return HttpResponse("OK")

        middleware = SlowQueryLoggingMiddleware(get_response)

        mock_connection = MagicMock()
        mock_connection.queries = [
            {"sql": "SELECT 1", "time": "0.001"},
            {"sql": "SELECT pg_sleep(0.6)", "time": "0.601"},
        ]
        mock_connection.queries_log = MagicMock()

        with patch("django.db.connection", mock_connection):
            _response = middleware(request)

            mock_logger.warning.assert_called()
            warning_calls = mock_logger.warning.call_args_list
            self.assertTrue(
                any("Slow queries detected" in str(call) for call in warning_calls)
            )

    @override_settings(
        DEBUG=True,
        PERFORMANCE_MONITORING={"TRACK_QUERIES": True, "SLOW_QUERY_THRESHOLD": 0.5},
    )
    @patch("apps.core.middleware.performance.logger")
    def test_no_slow_queries(self, mock_logger):
        """Test that fast queries don't trigger warnings."""
        request = self.factory.get("/test-path/")

        mock_connection = MagicMock()
        mock_connection.queries = [
            {"sql": "SELECT 1", "time": "0.001"},
            {"sql": "SELECT 2", "time": "0.002"},
        ]
        mock_connection.queries_log = MagicMock()

        with patch("django.db.connection", mock_connection):
            _response = self.middleware(request)

            mock_logger.warning.assert_not_called()

    @override_settings(DEBUG=False)
    def test_disabled_in_production(self):
        """Test that query logging is disabled in production."""
        request = self.factory.get("/test-path/")

        # Recreate middleware with production settings
        def get_response(request):
            return HttpResponse("OK")

        middleware = SlowQueryLoggingMiddleware(get_response)

        with patch("django.db.connection") as mock_connection:
            _response = middleware(request)

            # Should not access queries in production
            mock_connection.queries_log.clear.assert_not_called()

    @override_settings(
        DEBUG=True,
        PERFORMANCE_MONITORING={"TRACK_QUERIES": True, "SLOW_QUERY_THRESHOLD": 0.1},
    )
    @patch("apps.core.middleware.performance.logger")
    def test_truncated_sql_in_logs(self, mock_logger):
        """Test that very long SQL queries are truncated in logs."""
        request = self.factory.get("/test-path/")

        long_sql = (
            "SELECT " + ", ".join([f"column_{i}" for i in range(100)]) + " FROM table"
        )

        # Create middleware after @override_settings so self.enabled = True
        def get_response(request):
            return HttpResponse("OK")

        middleware = SlowQueryLoggingMiddleware(get_response)

        mock_connection = MagicMock()
        mock_connection.queries = [
            {"sql": long_sql, "time": "0.6"},
        ]
        mock_connection.queries_log = MagicMock()

        with patch("django.db.connection", mock_connection):
            _response = middleware(request)

            warning_calls = mock_logger.warning.call_args_list
            logged_sql = None
            for call in warning_calls:
                if "SELECT" in str(call):
                    logged_sql = str(call)
                    break

            self.assertIsNotNone(logged_sql)
            self.assertIn("...", logged_sql)
            self.assertLess(len(logged_sql), len(long_sql))  # type: ignore[arg-type]


class MiddlewareIntegrationTests(TestCase):
    """Integration tests for middleware with real views."""

    def setUp(self):
        """Set up test environment."""
        self.user = create_test_user()

    @override_settings(PERFORMANCE_MONITORING={"ENABLED": True}, DEBUG=True)
    def test_middleware_with_real_view(self):
        """Test middleware with actual Django views."""
        self.client.login(username=self.user.username, password="testpass123")

        # Make request to a real view
        response = self.client.get(reverse("review_manager:dashboard"))

        # Should have performance headers
        self.assertIn("X-View-Time", response)
        self.assertIn("X-View-Name", response)

        # View name should match
        self.assertEqual(response["X-View-Name"], "review_manager:dashboard")
