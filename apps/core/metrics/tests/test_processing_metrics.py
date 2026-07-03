"""
Tests for result processing metrics instrumentation.
"""

import time

from django.test import TestCase
from prometheus_client import REGISTRY

from apps.core.metrics.enums import ProcessingStatus
from apps.core.metrics.processing_metrics import (
    record_processing_result,
    track_processing_operation,
    update_deduplication_rate,
)


class ProcessingMetricsTest(TestCase):
    """Test cases for processing metrics."""

    def test_track_processing_operation_context_manager(self):
        """Test processing operation tracking."""
        count_before = REGISTRY.get_sample_value(
            "agent_grey_processing_duration_seconds_count",
            {"operation": "deduplication"},
        )
        if count_before is None:
            count_before = 0

        with track_processing_operation("deduplication"):
            time.sleep(0.05)  # Simulate 50ms processing

        # Check histogram count
        count_after = REGISTRY.get_sample_value(
            "agent_grey_processing_duration_seconds_count",
            {"operation": "deduplication"},
        )
        self.assertIsNotNone(count_after)
        self.assertGreater(count_after, count_before)

    def test_track_processing_operation_with_exception(self):
        """Test operation tracking still records duration on exception."""
        count_before = REGISTRY.get_sample_value(
            "agent_grey_processing_duration_seconds_count",
            {"operation": "normalisation"},
        )
        if count_before is None:
            count_before = 0

        with self.assertRaises(ValueError):
            with track_processing_operation("normalisation"):
                raise ValueError("Processing error")

        # Should still record duration
        count_after = REGISTRY.get_sample_value(
            "agent_grey_processing_duration_seconds_count",
            {"operation": "normalisation"},
        )
        self.assertIsNotNone(count_after)
        self.assertGreater(count_after, count_before)

    def test_record_processing_result_success(self):
        """Test recording successful processing result."""
        before = REGISTRY.get_sample_value(
            "agent_grey_results_processed_total",
            {"status": ProcessingStatus.SUCCESS.value},
        )
        if before is None:
            before = 0

        record_processing_result(ProcessingStatus.SUCCESS)

        after = REGISTRY.get_sample_value(
            "agent_grey_results_processed_total",
            {"status": ProcessingStatus.SUCCESS.value},
        )

        self.assertEqual(after - before, 1.0)

    def test_record_processing_result_duplicate(self):
        """Test recording duplicate result."""
        before = REGISTRY.get_sample_value(
            "agent_grey_results_processed_total",
            {"status": ProcessingStatus.DUPLICATE.value},
        )
        if before is None:
            before = 0

        record_processing_result(ProcessingStatus.DUPLICATE)

        after = REGISTRY.get_sample_value(
            "agent_grey_results_processed_total",
            {"status": ProcessingStatus.DUPLICATE.value},
        )

        self.assertEqual(after - before, 1.0)

    def test_update_deduplication_rate_calculation(self):
        """Test deduplication rate calculation."""
        # 100 total results, 80 unique (20% duplicates)
        update_deduplication_rate(total_results=100, unique_results=80)

        rate = REGISTRY.get_sample_value("agent_grey_deduplication_rate")

        # Should be 20.0 (percentage)
        self.assertEqual(rate, 20.0)

    def test_update_deduplication_rate_zero_duplicates(self):
        """Test deduplication rate with no duplicates."""
        update_deduplication_rate(total_results=50, unique_results=50)

        rate = REGISTRY.get_sample_value("agent_grey_deduplication_rate")

        # Should be 0.0
        self.assertEqual(rate, 0.0)

    def test_update_deduplication_rate_handles_zero_results(self):
        """Test deduplication rate handles zero results gracefully."""
        # Should not crash
        try:
            update_deduplication_rate(total_results=0, unique_results=0)
        except Exception as e:
            self.fail(f"update_deduplication_rate raised {e}")
