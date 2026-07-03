"""
Tests for Prometheus metrics registry.

Verifies that all custom metrics are properly initialized and
follow naming conventions.
"""

from django.test import TestCase
from prometheus_client import REGISTRY

from apps.core.metrics.registry import (
    deduplication_rate,
    processing_duration_seconds,
    results_processed_total,
    review_decisions_total,
    review_velocity_per_hour,
    search_api_errors_total,
    search_duration_seconds,
    search_queries_total,
    search_results_count,
    session_state_duration_seconds,
    session_state_gauge,
    session_transitions_total,
)


class MetricsRegistryTest(TestCase):
    """Test cases for metrics registry initialization."""

    def test_session_metrics_registered(self):
        """Test session metrics are registered in REGISTRY."""
        # These should not raise errors when accessing
        _sample = REGISTRY.get_sample_value(
            "agent_grey_session_state", {"state": "draft"}
        )
        # Can be None (not set yet) but metric should exist
        self.assertIsNotNone(session_state_gauge)
        self.assertIsNotNone(session_transitions_total)
        self.assertIsNotNone(session_state_duration_seconds)

    def test_search_metrics_registered(self):
        """Test search metrics are registered in REGISTRY."""
        self.assertIsNotNone(search_queries_total)
        self.assertIsNotNone(search_duration_seconds)
        self.assertIsNotNone(search_results_count)
        self.assertIsNotNone(search_api_errors_total)

    def test_processing_metrics_registered(self):
        """Test processing metrics are registered in REGISTRY."""
        self.assertIsNotNone(processing_duration_seconds)
        self.assertIsNotNone(deduplication_rate)
        self.assertIsNotNone(results_processed_total)

    def test_review_metrics_registered(self):
        """Test review metrics are registered in REGISTRY."""
        self.assertIsNotNone(review_decisions_total)
        self.assertIsNotNone(review_velocity_per_hour)

    def test_metric_naming_convention(self):
        """Test all metrics follow agent_grey_ prefix."""
        self.assertTrue(session_state_gauge._name.startswith("agent_grey_"))
        self.assertTrue(session_transitions_total._name.startswith("agent_grey_"))
        self.assertTrue(search_queries_total._name.startswith("agent_grey_"))
        self.assertTrue(review_decisions_total._name.startswith("agent_grey_"))
        self.assertTrue(results_processed_total._name.startswith("agent_grey_"))

    def test_counter_metrics_have_total_suffix(self):
        """Test Counter metrics follow _total naming convention."""
        # Counter metrics should have _total in their registered name
        # When exposed to Prometheus, the client adds _total suffix automatically
        from prometheus_client import generate_latest

        metrics_output = generate_latest().decode()

        # Verify metrics are exposed with _total suffix
        self.assertIn("agent_grey_session_transitions_total", metrics_output)
        self.assertIn("agent_grey_search_queries_total", metrics_output)
        self.assertIn("agent_grey_search_api_errors_total", metrics_output)
        self.assertIn("agent_grey_results_processed_total", metrics_output)
        self.assertIn("agent_grey_review_decisions_total", metrics_output)

    def test_histogram_metrics_have_seconds_suffix(self):
        """Test Histogram metrics for durations end with _seconds."""
        self.assertTrue("seconds" in session_state_duration_seconds._name)
        self.assertTrue("seconds" in search_duration_seconds._name)
        self.assertTrue("seconds" in processing_duration_seconds._name)

    def test_gauge_metrics_descriptive_names(self):
        """Test Gauge metrics have descriptive names."""
        self.assertIn("state", session_state_gauge._name)
        self.assertIn("rate", deduplication_rate._name)
        self.assertIn("velocity", review_velocity_per_hour._name)
