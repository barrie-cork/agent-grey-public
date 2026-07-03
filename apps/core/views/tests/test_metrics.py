"""
Tests for Prometheus metrics endpoint.

Tests authentication, response format, and access control.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from apps.core.tests.utils import create_test_user

User = get_user_model()


class MetricsViewTest(TestCase):
    """Test cases for Prometheus metrics endpoint."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        self.url = reverse("prometheus_metrics")

        self.staff_user = create_test_user(username_prefix="staffuser")
        self.staff_user.is_staff = True
        self.staff_user.save()

        self.normal_user = create_test_user(username_prefix="normaluser")

    def test_metrics_endpoint_allows_staff_user(self):
        """Test metrics endpoint allows staff users."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_metrics_endpoint_allows_debug_mode(self):
        """Test metrics endpoint allows unauthenticated in DEBUG mode."""
        with self.settings(DEBUG=True):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)

    def test_metrics_endpoint_returns_prometheus_format(self):
        """Test metrics endpoint returns Prometheus format."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)

        # Check content type
        self.assertIn("text/plain", response["Content-Type"])

        # Check response contains metric names
        content = response.content.decode("utf-8")
        self.assertIn("agent_grey_", content)

    def test_metrics_endpoint_not_cached(self):
        """Test metrics endpoint has no-cache headers."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)

        # Should have cache control headers (added by @never_cache)
        self.assertIn("Cache-Control", response)

    def test_metrics_endpoint_only_allows_get(self):
        """Test metrics endpoint only allows GET requests."""
        self.client.force_login(self.staff_user)

        # POST should not be allowed
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 405)  # Method Not Allowed

    def test_metrics_endpoint_requires_staff_in_production(self):
        """Test metrics endpoint requires staff user when not DEBUG."""
        with self.settings(DEBUG=False):
            # Unauthenticated
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 403)

            # Normal user
            self.client.force_login(self.normal_user)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 403)

            # Logout for next test
            self.client.logout()

    def test_metrics_endpoint_contains_custom_metrics(self):
        """Test metrics endpoint includes our custom metrics."""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)

        content = response.content.decode("utf-8")

        # Should contain at least some of our custom metrics
        # (not all may have data yet, but definitions should be there)
        self.assertTrue(
            "agent_grey_session" in content
            or "agent_grey_search" in content
            or "agent_grey_review" in content
            or "agent_grey_processing" in content,
            "No custom Agent Grey metrics found in response",
        )
