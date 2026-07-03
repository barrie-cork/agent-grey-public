"""
Tests for metric label enums.

Verifies enum values match expected strings for Prometheus labels.
"""

from django.test import TestCase

from apps.core.metrics.enums import (
    ErrorType,
    ProcessingStatus,
    ReviewDecision,
    SearchStatus,
)


class MetricsEnumsTest(TestCase):
    """Test cases for metrics enums."""

    def test_search_status_values(self):
        """Test SearchStatus enum has correct values."""
        self.assertEqual(SearchStatus.SUCCESS.value, "success")
        self.assertEqual(SearchStatus.ERROR.value, "error")
        self.assertEqual(SearchStatus.EMPTY.value, "empty")

    def test_error_type_values(self):
        """Test ErrorType enum has correct values."""
        self.assertEqual(ErrorType.TIMEOUT.value, "timeout")
        self.assertEqual(ErrorType.RATE_LIMIT.value, "rate_limit")
        self.assertEqual(ErrorType.AUTHENTICATION.value, "authentication")
        self.assertEqual(ErrorType.NETWORK.value, "network")
        self.assertEqual(ErrorType.UNKNOWN.value, "unknown")

    def test_review_decision_values(self):
        """Test ReviewDecision enum has correct values."""
        self.assertEqual(ReviewDecision.INCLUDE.value, "include")
        self.assertEqual(ReviewDecision.EXCLUDE.value, "exclude")
        self.assertEqual(ReviewDecision.UNDECIDED.value, "undecided")

    def test_processing_status_values(self):
        """Test ProcessingStatus enum has correct values."""
        self.assertEqual(ProcessingStatus.SUCCESS.value, "success")
        self.assertEqual(ProcessingStatus.DUPLICATE.value, "duplicate")
        self.assertEqual(ProcessingStatus.ERROR.value, "error")

    def test_search_status_is_str_compatible(self):
        """Test SearchStatus can be used as string."""
        status = SearchStatus.SUCCESS
        self.assertIsInstance(status.value, str)
        self.assertEqual(f"Status: {status.value}", "Status: success")

    def test_enum_members_are_unique(self):
        """Test all enum members have unique values."""
        search_values = [s.value for s in SearchStatus]
        self.assertEqual(len(search_values), len(set(search_values)))

        error_values = [e.value for e in ErrorType]
        self.assertEqual(len(error_values), len(set(error_values)))

        review_values = [r.value for r in ReviewDecision]
        self.assertEqual(len(review_values), len(set(review_values)))

        processing_values = [p.value for p in ProcessingStatus]
        self.assertEqual(len(processing_values), len(set(processing_values)))
