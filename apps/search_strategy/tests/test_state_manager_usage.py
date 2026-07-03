"""
Test cases to verify that SessionStateManager is properly used in search_strategy_service.py
and that automatic trigger mechanism works correctly.

Note: A post_save signal on SearchQuery (check_strategy_completion) auto-transitions
sessions from defining_search to ready_to_execute when a complete strategy with active
queries exists. Tests that need to control transitions must account for this.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase

from apps.review_manager.models import SearchSession
from apps.review_manager.services.state_manager import SessionStateManager
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.search_strategy.services.search_strategy_service import SearchStrategyService
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestSessionStateManagerUsage(TestCase):
    """Test that search_strategy_service properly uses SessionStateManager."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )

        self.service = SearchStrategyService()

    @patch("apps.review_manager.services.state_manager.SessionStateManager")
    def test_prepare_for_execution_uses_state_manager(self, mock_state_manager_class):
        """Test that prepare_for_execution uses SessionStateManager.transition_to()."""
        mock_manager = MagicMock()
        mock_state_manager_class.return_value = mock_manager
        mock_manager.transition_to.return_value = (True, None)

        call_count = [0]

        def fake_refresh(using=None, fields=None):
            call_count[0] += 1
            if call_count[0] == 1:
                self.session.status = "defining_search"
            else:
                self.session.status = "ready_to_execute"

        self.session.refresh_from_db = fake_refresh

        result = self.service.prepare_for_execution(self.session, self.user, None)

        mock_state_manager_class.assert_called_with(self.session)

        calls = mock_manager.transition_to.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0][0], "defining_search")
        self.assertIn("user", calls[0][1])
        self.assertEqual(calls[1][0][0], "ready_to_execute")
        self.assertIn("user", calls[1][1])
        self.assertTrue(result["success"])

    @patch("apps.review_manager.services.state_manager.SessionStateManager")
    def test_prepare_for_execution_handles_transition_errors(
        self, mock_state_manager_class
    ):
        """Test that prepare_for_execution properly handles transition errors."""
        mock_manager = MagicMock()
        mock_state_manager_class.return_value = mock_manager
        mock_manager.transition_to.side_effect = [
            (True, None),
            (False, "Cannot execute: No active queries defined"),
        ]

        def fake_refresh(using=None, fields=None):
            self.session.status = "defining_search"

        self.session.refresh_from_db = fake_refresh

        result = self.service.prepare_for_execution(self.session, self.user, None)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Cannot execute: No active queries defined")

    @patch(
        "apps.review_manager.services.state_manager.SessionStateManager._trigger_automatic_execution"
    )
    def test_prepare_for_execution_transitions_correctly(self, mock_trigger):
        """Test that prepare_for_execution transitions through states correctly."""
        SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test interest"],
            context_terms=["test context"],
            is_complete=True,
        )

        result = self.service.prepare_for_execution(self.session, self.user, None)

        self.assertTrue(result["success"])
        self.session.refresh_from_db()
        self.assertIn(self.session.status, ["ready_to_execute", "executing"])


class TestAutomaticTriggerMechanism(TransactionTestCase):
    """Test the automatic trigger mechanism when reaching ready_to_execute state.

    Uses TransactionTestCase because _trigger_automatic_execution uses
    transaction.on_commit() which only fires after real commits.

    Note: SearchQuery post_save signal auto-transitions defining_search to
    ready_to_execute when a complete strategy exists. Tests that need to
    manually control transitions create queries with is_active=False.
    """

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
        )

        # Create query as inactive to prevent the auto-transition signal
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            is_active=False,
        )

    def _activate_query(self):
        """Activate the query without triggering auto-transition signal."""
        SearchQuery.objects.filter(pk=self.query.pk).update(is_active=True)

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task")
    @patch("apps.core.progress.tracker.ProgressTracker")
    def test_automatic_trigger_fires_on_ready_to_execute(
        self, mock_tracker_class, mock_task
    ):
        """Test that _trigger_automatic_execution is called when reaching ready_to_execute."""
        mock_tracker = MagicMock()
        mock_tracker_class.return_value = mock_tracker
        mock_task.delay.return_value = MagicMock(id="task-123")

        # Activate query without signal (use .update() to bypass post_save)
        self._activate_query()

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("ready_to_execute")

        self.assertTrue(success, f"Transition failed: {error}")

        # Assert progress tracker was used
        mock_tracker_class.assert_called_once()

        # Assert progress updates were sent with correct component
        update_calls = mock_tracker.update_progress.call_args_list
        self.assertGreater(len(update_calls), 0)
        for c in update_calls:
            self.assertEqual(c[1]["component"], "ready_to_execute")

        # Assert task was triggered
        mock_task.delay.assert_called_once_with(str(self.session.id))

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task")
    @patch("apps.core.progress.tracker.ProgressTracker")
    def test_automatic_trigger_progress_messages(self, mock_tracker_class, mock_task):
        """Test that automatic trigger sends correct progress messages."""
        mock_tracker = MagicMock()
        mock_tracker_class.return_value = mock_tracker
        mock_task.delay.return_value = MagicMock(id="task-123")

        self._activate_query()

        state_manager = SessionStateManager(self.session)
        success, _ = state_manager.transition_to("ready_to_execute")

        self.assertTrue(success)

        update_calls = mock_tracker.update_progress.call_args_list
        self.assertEqual(len(update_calls), 4)

        for c in update_calls:
            self.assertEqual(c[1]["component"], "ready_to_execute")

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task")
    def test_automatic_trigger_failure_handling(self, mock_task):
        """Test that automatic trigger failures don't fail the transition."""
        mock_task.delay.side_effect = Exception("Task system unavailable")

        self._activate_query()

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("ready_to_execute")

        self.assertTrue(
            success, f"Transition should succeed even if trigger fails: {error}"
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_to_execute")

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task")
    @patch("apps.core.progress.tracker.ProgressTracker")
    def test_automatic_trigger_timing(self, mock_tracker_class, mock_task):
        """Test that automatic trigger fires execution task after progress updates."""
        mock_tracker = MagicMock()
        mock_tracker_class.return_value = mock_tracker
        mock_task.delay.return_value = MagicMock(id="task-123")

        self._activate_query()

        state_manager = SessionStateManager(self.session)
        success, _ = state_manager.transition_to("ready_to_execute")

        self.assertTrue(success)
        mock_task.delay.assert_called_once_with(str(self.session.id))
        self.assertEqual(mock_tracker.update_progress.call_count, 4)


class TestIntegrationFlow(TransactionTestCase):
    """Test the full flow from defining_search through automatic execution."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )

        self.service = SearchStrategyService()

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task")
    @patch("apps.core.progress.tracker.ProgressTracker")
    def test_full_automatic_flow(self, mock_tracker_class, mock_task):
        """Test the full flow: defining_search -> ready_to_execute with automatic trigger.

        The check_strategy_completion signal auto-transitions sessions to
        ready_to_execute when a complete strategy with active queries is saved.
        When prepare_for_execution uses SessionStateManager.transition_to(),
        the automatic trigger fires and starts the execution task.

        This test creates queries as inactive to prevent the signal, then
        manually drives the transition through SessionStateManager.
        """
        mock_tracker = MagicMock()
        mock_tracker_class.return_value = mock_tracker
        mock_task.delay.return_value = MagicMock(id="task-123")

        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
        )

        # Create inactive query to avoid signal auto-transition
        query = SearchQuery.objects.create(
            strategy=strategy,
            session=self.session,
            query_text="test query",
            is_active=False,
        )

        # Activate without triggering signal
        SearchQuery.objects.filter(pk=query.pk).update(is_active=True)

        # Session should still be at defining_search
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "defining_search")

        # Use SessionStateManager directly (like prepare_for_execution would)
        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("ready_to_execute")
        self.assertTrue(success, f"Transition failed: {error}")

        # Assert task was triggered automatically
        mock_task.delay.assert_called_once_with(str(self.session.id))

        # Check session activity logs
        from apps.review_manager.models import SessionActivity

        activities = SessionActivity.objects.filter(
            session=self.session, activity_type="auto_execution"
        )

        self.assertEqual(activities.count(), 1)
        activity = activities.first()
        self.assertTrue(activity.metadata.get("automatic"))
        self.assertEqual(
            activity.metadata.get("triggered_from"), "ready_to_execute_transition"
        )
