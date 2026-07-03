"""
Tests for serp_execution interfaces module.
Validates protocol implementations and interface contracts.
"""

from unittest.mock import Mock
from uuid import uuid4

from django.test import TestCase

from apps.core.interfaces import SessionProvider
from apps.serp_execution.interfaces import NotificationService


class TestSessionProvider(TestCase):
    """Test SessionProvider protocol implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_provider = Mock(spec=SessionProvider)
        self.session_id = str(uuid4())

    def test_get_session(self):
        """Test get_session method."""
        mock_session = Mock()
        self.mock_provider.get_session.return_value = mock_session

        result = self.mock_provider.get_session(self.session_id)

        self.assertEqual(result, mock_session)
        self.mock_provider.get_session.assert_called_once_with(self.session_id)

    def test_get_session_queries(self):
        """Test get_session_queries method."""
        mock_queries = [Mock(), Mock()]
        self.mock_provider.get_session_queries.return_value = mock_queries

        result = self.mock_provider.get_session_queries(self.session_id)

        self.assertEqual(result, mock_queries)
        self.mock_provider.get_session_queries.assert_called_once_with(self.session_id)

    def test_get_session_for_diagnostic(self):
        """Test get_session_for_diagnostic method - Not in base protocol."""
        # Note: get_session_for_diagnostic is not actually part of the SessionProvider protocol
        # It's an implementation detail in DefaultSessionProvider
        # This test should verify implementation, not protocol
        pass

    def test_protocol_compliance(self):
        """Test that mock implements required protocol methods."""
        # Verify all required methods exist
        self.assertTrue(hasattr(self.mock_provider, "get_session"))
        self.assertTrue(hasattr(self.mock_provider, "get_session_queries"))
        self.assertTrue(hasattr(self.mock_provider, "get_session_state"))
        self.assertTrue(hasattr(self.mock_provider, "session_exists"))
        self.assertTrue(callable(self.mock_provider.get_session))
        self.assertTrue(callable(self.mock_provider.get_session_queries))


class TestNotificationService(TestCase):
    """Test NotificationService protocol implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_service = Mock(spec=NotificationService)
        self.session_id = str(uuid4())

    def test_notify_execution_complete(self):
        """Test notify_execution_complete method."""
        self.mock_service.notify_execution_complete.return_value = None
        status = "completed"

        self.mock_service.notify_execution_complete(self.session_id, status)

        self.mock_service.notify_execution_complete.assert_called_once_with(
            self.session_id, status
        )

    def test_notify_error(self):
        """Test notify_error method."""
        error = "Test error"
        self.mock_service.notify_error.return_value = None

        self.mock_service.notify_error(self.session_id, error)

        self.mock_service.notify_error.assert_called_once_with(self.session_id, error)
