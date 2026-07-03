"""
Tests for monitoring views.

Tests the WorkflowMonitoringDashboard and ConnectionMonitoringAPI views:
- Staff-only access control
- Dashboard context data
- Connection monitoring API responses
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from apps.core.tests.utils import create_test_user

User = get_user_model()


class MonitoringViewsTestCase(TestCase):
    """Test the monitoring views."""

    def setUp(self):
        """Set up test client and users."""
        self.client = Client()

        self.staff_user = create_test_user(username_prefix="staffuser", is_staff=True)

        self.regular_user = create_test_user(
            username_prefix="regularuser", is_staff=False
        )

    def test_dashboard_requires_staff(self):
        """Test that monitoring dashboard requires staff access."""
        # Not logged in - should redirect
        response = self.client.get("/core/monitoring/workflow/")
        self.assertEqual(response.status_code, 302)

        # Regular user - should be forbidden
        self.client.login(username=self.regular_user.username, password="testpass123")
        response = self.client.get("/core/monitoring/workflow/")
        self.assertIn(response.status_code, [302, 403])

        # Staff user - should work
        self.client.login(username=self.staff_user.username, password="testpass123")
        response = self.client.get("/core/monitoring/workflow/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_context_has_required_keys(self):
        """Test that dashboard context includes expected data."""
        self.client.login(username=self.staff_user.username, password="testpass123")
        response = self.client.get("/core/monitoring/workflow/")

        self.assertEqual(response.status_code, 200)
        # Check for keys from get_context_data
        self.assertIn("system_health", response.context)
        self.assertIn("workflow_stats", response.context)
        self.assertIn("performance_metrics", response.context)
        self.assertIn("recent_activities", response.context)
        self.assertIn("stuck_sessions", response.context)
        self.assertIn("resource_stats", response.context)

    def test_connection_monitoring_api_requires_staff(self):
        """Test that connection monitoring API requires staff access."""
        url = "/core/api/monitoring/connections/"

        # Not logged in - should be forbidden
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])

        # Regular user - should be forbidden
        self.client.login(username=self.regular_user.username, password="testpass123")
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])

    @patch("apps.core.views.monitoring.metrics_api.ConnectionMetricsAggregator")
    def test_connection_monitoring_api_response(self, mock_aggregator_class):
        """Test connection monitoring API response format."""
        mock_aggregator = MagicMock()
        mock_aggregator.get_metrics.return_value = {
            "api_calls_last_hour": 10,
            "api_calls_last_24h": 100,
            "successful_calls": 95,
            "failed_calls": 5,
            "avg_response_time_ms": 150.0,
            "api_error_rate": 5.0,
            "timeout_errors": 1,
            "connection_healthy": True,
            "api_call_distribution": [],
        }
        mock_aggregator_class.return_value = mock_aggregator

        from apps.core.views.monitoring import ConnectionMonitoringAPI

        view = ConnectionMonitoringAPI()
        view.request = MagicMock()
        view.request.user = self.staff_user

        response = view.get(view.request)
        self.assertEqual(response.status_code, 200)

        import json

        data = json.loads(response.content)
        self.assertEqual(data["status"], "healthy")
        self.assertIn("recommendation", data)
        self.assertIn("timestamp", data)
        self.assertEqual(data["api_calls_last_hour"], 10)

    @patch("apps.core.views.monitoring.metrics_api.ConnectionMetricsAggregator")
    def test_connection_monitoring_api_critical_status(self, mock_aggregator_class):
        """Test connection monitoring API with critical status."""
        mock_aggregator = MagicMock()
        mock_aggregator.get_metrics.return_value = {
            "api_calls_last_hour": 50,
            "api_calls_last_24h": 200,
            "successful_calls": 150,
            "failed_calls": 50,
            "avg_response_time_ms": 500.0,
            "api_error_rate": 25.0,
            "timeout_errors": 10,
            "connection_healthy": False,
            "api_call_distribution": [],
        }
        mock_aggregator_class.return_value = mock_aggregator

        from apps.core.views.monitoring import ConnectionMonitoringAPI

        view = ConnectionMonitoringAPI()
        view.request = MagicMock()
        view.request.user = self.staff_user

        response = view.get(view.request)

        import json

        data = json.loads(response.content)
        self.assertEqual(data["status"], "critical")
        self.assertIn("Critical", data["recommendation"])

    @patch("apps.core.views.monitoring.metrics_api.ConnectionMetricsAggregator")
    def test_connection_monitoring_api_healthy_status(self, mock_aggregator_class):
        """Test connection monitoring API with healthy status."""
        mock_aggregator = MagicMock()
        mock_aggregator.get_metrics.return_value = {
            "api_calls_last_hour": 5,
            "api_calls_last_24h": 50,
            "successful_calls": 49,
            "failed_calls": 1,
            "avg_response_time_ms": 100.0,
            "api_error_rate": 2.0,
            "timeout_errors": 0,
            "connection_healthy": True,
            "api_call_distribution": [],
        }
        mock_aggregator_class.return_value = mock_aggregator

        from apps.core.views.monitoring import ConnectionMonitoringAPI

        view = ConnectionMonitoringAPI()
        view.request = MagicMock()
        view.request.user = self.staff_user

        response = view.get(view.request)

        import json

        data = json.loads(response.content)
        self.assertEqual(data["status"], "healthy")
        self.assertIn("Healthy", data["recommendation"])
