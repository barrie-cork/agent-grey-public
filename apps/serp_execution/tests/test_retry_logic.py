"""
Tests for SERP execution retry logic.

Tests for retry decision logic and error handling.
"""

from django.test import TestCase

from apps.serp_execution.tasks import _should_retry_execution


class TestRetryLogic(TestCase):
    """Test cases for retry decision logic."""

    def test_should_retry_connection_errors(self):
        """Test that connection errors trigger retry."""
        self.assertTrue(_should_retry_execution(ConnectionError("Connection failed")))
        self.assertTrue(_should_retry_execution(TimeoutError("Request timed out")))
        self.assertTrue(_should_retry_execution(OSError("Network unreachable")))

    def test_should_retry_transient_messages(self):
        """Test that specific error messages trigger retry."""
        self.assertTrue(_should_retry_execution(Exception("Connection reset by peer")))
        self.assertTrue(
            _should_retry_execution(Exception("Service temporarily unavailable"))
        )
        self.assertTrue(_should_retry_execution(Exception("Too many requests")))

    def test_should_not_retry_business_errors(self):
        """Test that business logic errors don't trigger retry."""
        self.assertFalse(_should_retry_execution(ValueError("Invalid input")))
        self.assertFalse(_should_retry_execution(KeyError("Missing key")))
        self.assertFalse(_should_retry_execution(Exception("Invalid session state")))
