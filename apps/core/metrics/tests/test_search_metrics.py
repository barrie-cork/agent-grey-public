"""
Tests for search execution metrics instrumentation.

Tests SearchTracker context manager, result recording, and error tracking.
"""

import time
from unittest.mock import MagicMock

from django.test import TestCase
from prometheus_client import REGISTRY

from apps.core.metrics.enums import ErrorType, SearchStatus
from apps.core.metrics.search_metrics import SearchTracker, track_search_execution


class SearchMetricsTest(TestCase):
    """Test cases for search metrics."""

    def test_track_search_execution_context_manager(self):
        """Test track_search_execution yields SearchTracker."""
        query = MagicMock()
        query.id = "test-query-123"
        query.query_text = "test query"

        with track_search_execution(query) as tracker:
            self.assertIsInstance(tracker, SearchTracker)
            self.assertEqual(tracker.query, query)
            self.assertEqual(tracker.api_provider, "serper")

    def test_track_search_execution_records_success(self):
        """Test context manager records successful search."""
        query = MagicMock()
        query.id = "test-query-123"

        # Get counter before
        before = REGISTRY.get_sample_value(
            "agent_grey_search_queries_total",
            {"status": SearchStatus.SUCCESS.value, "api_provider": "serper"},
        )
        if before is None:
            before = 0

        with track_search_execution(query) as tracker:
            # Simulate search returning 10 results
            tracker.record_results(10, status=SearchStatus.SUCCESS)

        # Get counter after
        after = REGISTRY.get_sample_value(
            "agent_grey_search_queries_total",
            {"status": SearchStatus.SUCCESS.value, "api_provider": "serper"},
        )

        self.assertEqual(after - before, 1.0)

    def test_track_search_execution_records_duration(self):
        """Test context manager records search duration."""
        query = MagicMock()
        query.id = "test-query-123"

        count_before = REGISTRY.get_sample_value(
            "agent_grey_search_duration_seconds_count", {"api_provider": "serper"}
        )
        if count_before is None:
            count_before = 0

        with track_search_execution(query) as tracker:
            time.sleep(0.1)  # Simulate 100ms search
            tracker.record_results(5, status=SearchStatus.SUCCESS)

        # Check histogram count incremented
        count_after = REGISTRY.get_sample_value(
            "agent_grey_search_duration_seconds_count", {"api_provider": "serper"}
        )
        self.assertIsNotNone(count_after)
        self.assertGreater(count_after, count_before)

    def test_track_search_execution_records_result_count(self):
        """Test result count is observed in histogram."""
        query = MagicMock()
        query.id = "test-query-123"

        count_before = REGISTRY.get_sample_value(
            "agent_grey_search_results_count_count", {"api_provider": "serper"}
        )
        if count_before is None:
            count_before = 0

        with track_search_execution(query) as tracker:
            tracker.record_results(25, status=SearchStatus.SUCCESS)

        # Check histogram count incremented
        count_after = REGISTRY.get_sample_value(
            "agent_grey_search_results_count_count", {"api_provider": "serper"}
        )
        self.assertIsNotNone(count_after)
        self.assertGreater(count_after, count_before)

    def test_track_search_execution_handles_exception(self):
        """Test context manager records error on exception."""
        query = MagicMock()
        query.id = "test-query-123"

        # Get error counter before
        before = REGISTRY.get_sample_value(
            "agent_grey_search_queries_total",
            {"status": SearchStatus.ERROR.value, "api_provider": "serper"},
        )
        if before is None:
            before = 0

        with self.assertRaises(Exception):
            with track_search_execution(query) as _tracker:
                raise Exception("Timeout error")

        # Get counter after - should have recorded error
        after = REGISTRY.get_sample_value(
            "agent_grey_search_queries_total",
            {"status": SearchStatus.ERROR.value, "api_provider": "serper"},
        )

        self.assertIsNotNone(after)
        self.assertGreater(after, before)

    def test_search_tracker_prevents_double_recording(self):
        """Test SearchTracker._recorded flag prevents double-recording."""
        query = MagicMock()
        query.id = "test-query-123"

        tracker = SearchTracker(query, "serper", time.time())

        # Get counter before
        before = REGISTRY.get_sample_value(
            "agent_grey_search_queries_total",
            {"status": SearchStatus.SUCCESS.value, "api_provider": "serper"},
        )
        if before is None:
            before = 0

        # Record results twice
        tracker.record_results(10, status=SearchStatus.SUCCESS)
        tracker.record_results(20, status=SearchStatus.SUCCESS)

        # Get counter after
        after = REGISTRY.get_sample_value(
            "agent_grey_search_queries_total",
            {"status": SearchStatus.SUCCESS.value, "api_provider": "serper"},
        )

        # Should only increment once
        self.assertEqual(after - before, 1.0)

    def test_error_type_categorisation_timeout(self):
        """Test timeout error messages are categorised correctly."""
        query = MagicMock()
        query.id = "test-query-123"

        tracker = SearchTracker(query, "serper", time.time())

        before = REGISTRY.get_sample_value(
            "agent_grey_search_api_errors_total",
            {"api_provider": "serper", "error_type": ErrorType.TIMEOUT.value},
        )
        if before is None:
            before = 0

        # Test timeout error
        tracker.record_error("Request timeout after 30 seconds")

        after = REGISTRY.get_sample_value(
            "agent_grey_search_api_errors_total",
            {"api_provider": "serper", "error_type": ErrorType.TIMEOUT.value},
        )
        self.assertEqual(after - before, 1.0)

    def test_error_type_categorisation_rate_limit(self):
        """Test rate limit error messages are categorised correctly."""
        query = MagicMock()
        query.id = "test-query-123"

        tracker = SearchTracker(query, "serper", time.time())

        before = REGISTRY.get_sample_value(
            "agent_grey_search_api_errors_total",
            {"api_provider": "serper", "error_type": ErrorType.RATE_LIMIT.value},
        )
        if before is None:
            before = 0

        tracker.record_error("Rate limit exceeded")

        after = REGISTRY.get_sample_value(
            "agent_grey_search_api_errors_total",
            {"api_provider": "serper", "error_type": ErrorType.RATE_LIMIT.value},
        )
        self.assertEqual(after - before, 1.0)

    def test_track_search_execution_custom_api_provider(self):
        """Test context manager with custom API provider."""
        query = MagicMock()
        query.id = "test-query-123"

        with track_search_execution(query, api_provider="google") as tracker:
            self.assertEqual(tracker.api_provider, "google")
            tracker.record_results(5, status=SearchStatus.SUCCESS)

        # Check metric has correct label
        count = REGISTRY.get_sample_value(
            "agent_grey_search_queries_total",
            {"status": SearchStatus.SUCCESS.value, "api_provider": "google"},
        )
        self.assertIsNotNone(count)
