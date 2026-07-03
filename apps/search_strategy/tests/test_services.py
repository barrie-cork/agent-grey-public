"""Tests for search strategy services."""

from unittest.mock import MagicMock, patch

from django.contrib.messages.storage.session import SessionStorage
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.review_manager.models import SearchSession
from apps.search_strategy.services.search_strategy_service import SearchStrategyService
from apps.core.tests.utils import create_test_user


class SearchStrategyServiceTest(TestCase):
    """Test the SearchStrategyService class."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            owner=self.user, title="Test Session", status="draft"
        )
        self.service = SearchStrategyService()
        self.factory = RequestFactory()

    def tearDown(self):
        """Clean up after tests."""
        SearchSession.objects.all().delete()
        User.objects.all().delete()

    def _create_request(self):
        """Create a mock request with messages framework."""
        request = self.factory.post("/dummy-url/")
        request.user = self.user
        request.session = {}
        request._messages = SessionStorage(request)
        return request

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task")
    def test_initiate_search_execution_with_none_request(self, mock_task):
        """Test initiate_search_execution with None request doesn't crash."""
        # Setup
        mock_task.delay.return_value = MagicMock(id="test-task-id")
        self.session.status = "ready_to_execute"
        self.session.save()

        # Execute
        result = self.service.initiate_search_execution(self.session, self.user, None)

        # Assert
        self.assertTrue(result["success"])
        self.assertEqual(result["task_id"], "test-task-id")
        mock_task.delay.assert_called_once_with(str(self.session.id))

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task")
    def test_initiate_search_execution_with_valid_request(self, mock_task):
        """Test initiate_search_execution with valid request adds message."""
        # Setup
        mock_task.delay.return_value = MagicMock(id="test-task-id")
        self.session.status = "ready_to_execute"
        self.session.save()
        request = self._create_request()

        # Execute
        result = self.service.initiate_search_execution(
            self.session, self.user, request
        )

        # Assert
        self.assertTrue(result["success"])
        self.assertEqual(result["task_id"], "test-task-id")
        mock_task.delay.assert_called_once_with(str(self.session.id))

        # Check that message was added
        messages = list(request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn("Search execution has been initiated", str(messages[0]))

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task")
    def test_initiate_search_execution_handles_exception(self, mock_task):
        """Test initiate_search_execution handles exceptions gracefully."""
        # Setup
        mock_task.delay.side_effect = Exception("Test error")
        self.session.status = "ready_to_execute"
        self.session.save()

        # Execute
        result = self.service.initiate_search_execution(self.session, self.user, None)

        # Assert
        self.assertFalse(result["success"])
        self.assertIn("Test error", result["error"])

    def test_handle_status_transition_with_none_request(self):
        """Test handle_status_transition with None request doesn't crash."""
        # Setup
        self.session.status = "defining_search"
        self.session.save()

        # Execute
        result = self.service.handle_status_transition(self.session, self.user, None)

        # Assert
        self.assertTrue(result)
        # Check that the status was updated
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_to_execute")

    def test_handle_status_transition_with_valid_request(self):
        """Test handle_status_transition with valid request adds message."""
        # Setup
        self.session.status = "defining_search"
        self.session.save()
        request = self._create_request()

        # Execute
        result = self.service.handle_status_transition(self.session, self.user, request)

        # Assert
        self.assertTrue(result)
        # Check that the status was updated
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_to_execute")

        # Check that message was added
        messages = list(request._messages)
        self.assertEqual(len(messages), 1)
        self.assertIn("Search strategy completed", str(messages[0]))

    def test_handle_status_transition_failed_with_none_request(self):
        """Test handle_status_transition failure with None request doesn't crash."""
        # Setup - use a status that can't transition
        self.session.status = (
            "executing"  # Can't transition from executing to ready_to_execute
        )
        self.session.save()

        # Execute
        result = self.service.handle_status_transition(self.session, self.user, None)

        # Assert - should return True but not change status since it's not in draft/defining_search
        self.assertTrue(
            result
        )  # Returns True for states other than draft/defining_search
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "executing")  # Status unchanged

    def test_handle_status_transition_failed_with_valid_request(self):
        """Test handle_status_transition failure with valid request returns False.

        When can_transition_to returns False, the service logs at debug level
        but does not add a user-facing message (the condition is expected when
        a session is already executing or beyond).
        """
        # Setup
        self.session.status = "defining_search"
        self.session.save()
        request = self._create_request()

        # Mock can_transition_to to return False
        with patch.object(self.session, "can_transition_to") as mock_can_transition:
            mock_can_transition.return_value = False

            # Execute
            result = self.service.handle_status_transition(
                self.session, self.user, request
            )

            # Assert
            self.assertFalse(result)
            mock_can_transition.assert_called_once_with("ready_to_execute")

            # No user-facing message is added (debug-level log only)
            messages = list(request._messages)
            self.assertEqual(len(messages), 0)

    def test_prepare_for_execution_success(self):
        """Test prepare_for_execution successfully transitions session."""
        # Setup
        self.session.status = "draft"
        self.session.save()

        # Execute
        result = self.service.prepare_for_execution(self.session, self.user, None)

        # Assert
        self.assertTrue(result["success"])
        # Check that the status was updated
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_to_execute")

    def test_prepare_for_execution_invalid_status(self):
        """Test prepare_for_execution with invalid initial status."""
        # Setup - use a status that's not valid for execution
        self.session.status = "completed"  # Can't execute from completed status
        self.session.save()

        # Execute
        result = self.service.prepare_for_execution(self.session, self.user, None)

        # Assert
        self.assertFalse(result["success"])
        self.assertIn("Cannot execute search from status", result["error"])
