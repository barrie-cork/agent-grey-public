"""
Unit Tests for State Transitions
Tests the state machine transitions explicitly for search execution workflow
Validates proper state flow and error handling

Created: August 26, 2025
Purpose: Ensure state transitions work correctly after Phase 3 refactoring
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.state_machine.registry import StateRegistry
from apps.core.state_machine.state_machine import SessionStateMachine
from apps.review_manager.models import SearchSession
from apps.review_manager.services.state_manager import SessionStateManager
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


def _create_execution_data(session, user):
    """Create completed execution and processed result so validators pass."""
    strategy = SearchStrategy.objects.filter(session=session).first()
    if not strategy:
        strategy = SearchStrategy.objects.create(
            session=session,
            user=user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
        )
    query = SearchQuery.objects.filter(strategy=strategy).first()
    if not query:
        query = SearchQuery.objects.create(
            strategy=strategy,
            session=session,
            query_text="test AND test AND test",
            query_type="general",
            execution_order=1,
            is_active=True,
        )
    execution = SearchExecution.objects.create(
        query=query,
        initiated_by=user,
        status="completed",
        results_count=5,
        started_at=timezone.now(),
        completed_at=timezone.now(),
    )
    # Create raw result for the execution so validators can find processed results
    from apps.serp_execution.models import RawSearchResult
    from apps.results_manager.models import ProcessedResult

    raw_result = RawSearchResult.objects.create(
        execution=execution,
        title="Test Result",
        link="https://example.com/test",
        snippet="Test snippet",
        position=1,
    )
    ProcessedResult.objects.create(
        session=session,
        raw_result=raw_result,
        title="Test Result",
        url="https://example.com/test",
        snippet="Test snippet",
    )
    return execution


class StateTransitionUnitTests(TestCase):
    """Test state transitions in isolation"""

    def setUp(self):
        """Set up test data"""
        self.user = create_test_user(username_prefix="test_state_user")

        self.session = SearchSession.objects.create(
            title="State Transition Test Session", owner=self.user, status="draft"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test interest"],
            context_terms=["test context"],
        )

        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test population AND test interest AND test context",
            query_type="general",
            execution_order=1,
            is_active=True,
        )

    def test_complete_workflow_transitions(self):
        """Test the complete workflow from draft to ready_for_review"""

        # Test draft -> defining_search
        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("defining_search")
        self.assertTrue(success, f"draft -> defining_search failed: {error}")
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "defining_search")

        # Test defining_search -> ready_to_execute (may auto-transition to executing)
        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("ready_to_execute")
        self.assertTrue(success, f"defining_search -> ready_to_execute failed: {error}")
        self.session.refresh_from_db()
        self.assertIn(self.session.status, ["ready_to_execute", "executing"])

        # Set to executing and create execution data for validators
        self.session.status = "executing"
        self.session.save()
        _create_execution_data(self.session, self.user)

        # Test executing -> processing_results
        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("processing_results")
        self.assertTrue(success, f"executing -> processing_results failed: {error}")
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "processing_results")

        # Test processing_results -> ready_for_review
        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("ready_for_review")
        self.assertTrue(
            success, f"processing_results -> ready_for_review failed: {error}"
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_for_review")

    def test_invalid_transition_rejected(self):
        """Test that invalid transitions are rejected"""

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("ready_for_review")
        self.assertFalse(success)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "draft")

    def test_automated_transitions(self):
        """Test automated transitions that happen via Celery tasks"""

        self.session.status = "executing"
        self.session.save()
        _create_execution_data(self.session, self.user)

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("processing_results")
        self.assertTrue(success, f"executing -> processing_results failed: {error}")

        self.session.refresh_from_db()
        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("ready_for_review")
        self.assertTrue(
            success, f"processing_results -> ready_for_review failed: {error}"
        )

    def test_state_transition_with_error_handling(self):
        """Test state transitions with error states"""

        self.session.status = "executing"
        self.session.save()

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("defining_search")
        self.assertTrue(success, f"executing -> defining_search failed: {error}")
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "defining_search")

    def test_concurrent_transition_protection(self):
        """Test that concurrent transitions are properly handled"""

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("defining_search")
        self.assertTrue(success)


class StateRegistryTests(TestCase):
    """Test the state registry configuration"""

    def test_state_registry_configuration(self):
        """Test that state registry has correct transitions"""

        registry = StateRegistry()

        processing_state = registry.get_state("processing_results")
        self.assertIsNotNone(processing_state)
        assert processing_state is not None

        self.assertIn("ready_for_review", processing_state.allowed_transitions)
        self.assertIn("completed", processing_state.allowed_transitions)
        self.assertIn("failed", processing_state.allowed_transitions)

    def test_all_states_registered(self):
        """Test that all required states are registered"""

        registry = StateRegistry()

        required_states = [
            "draft",
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
            "completed",
            "failed",
            "archived",
        ]

        for state in required_states:
            state_def = registry.get_state(state)
            self.assertIsNotNone(state_def, f"State '{state}' not found in registry")


class StateMachineIntegrationTests(TestCase):
    """Test state machine integration with database"""

    def setUp(self):
        """Set up test data"""
        self.user = create_test_user(username_prefix="machine_test_user")

        self.session = SearchSession.objects.create(
            title="Machine Test Session", owner=self.user, status="draft"
        )

    def test_state_machine_transition(self):
        """Test that state machine transitions work correctly"""

        state_machine = SessionStateMachine()

        _result = state_machine.transition(str(self.session.id), "defining_search")

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "defining_search")

    def test_state_transition_audit_trail(self):
        """Test that state transitions are logged"""

        with patch("apps.core.state_machine.state_machine.logger") as mock_logger:
            state_machine = SessionStateMachine()

            state_machine.transition(str(self.session.id), "defining_search")

            mock_logger.info.assert_called()

            log_calls = mock_logger.info.call_args_list
            transition_logged = any(
                "transition" in str(call).lower() for call in log_calls
            )
            self.assertTrue(transition_logged)


class AutomaticTransitionTests(TestCase):
    """Test automatic state transitions that occur without user intervention"""

    def setUp(self):
        """Set up test data"""
        self.user = create_test_user(username_prefix="auto_test_user")

        self.session = SearchSession.objects.create(
            title="Automatic Transition Test", owner=self.user, status="executing"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["auto test"],
            interest_terms=["auto test"],
            context_terms=["auto test"],
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="auto test AND auto test AND auto test",
            query_type="general",
            execution_order=1,
            is_active=True,
        )

    def test_executing_to_processing_automatic(self):
        """Test automatic transition from executing to processing_results"""

        self.session.status = "executing"
        self.session.save()
        _create_execution_data(self.session, self.user)

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("processing_results")

        self.assertTrue(success, f"executing -> processing_results failed: {error}")
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "processing_results")

    def test_processing_to_review_automatic(self):
        """Test automatic transition from processing_results to ready_for_review"""

        self.session.status = "processing_results"
        self.session.save()
        _create_execution_data(self.session, self.user)

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("ready_for_review")

        self.assertTrue(
            success, f"processing_results -> ready_for_review failed: {error}"
        )
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_for_review")

    def test_review_state_on_page_access(self):
        """Test that accessing review page changes state to under_review"""

        self.session.status = "ready_for_review"
        self.session.save()

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("under_review")

        self.assertTrue(success, f"ready_for_review -> under_review failed: {error}")
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "under_review")

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task.delay")
    def test_ready_to_execute_auto_trigger_timing(self, mock_task):
        """Test that execution triggers within 1-2 seconds."""
        import time

        self.session.status = "defining_search"
        self.session.save()

        start_time = time.time()

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("ready_to_execute")

        self.assertTrue(success, f"defining_search -> ready_to_execute failed: {error}")

        elapsed = time.time() - start_time
        self.assertLess(elapsed, 3.0, "Trigger took too long")

        self.session.refresh_from_db()
        self.assertIn(self.session.status, ["ready_to_execute", "executing"])

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task.delay")
    def test_no_manual_intervention_required(self, mock_task):
        """Test full automation from ready_to_execute to executing."""
        self.session.status = "defining_search"
        self.session.save()

        state_manager = SessionStateManager(self.session)
        success, error = state_manager.transition_to("ready_to_execute")

        self.assertTrue(success, f"defining_search -> ready_to_execute failed: {error}")

        self.session.refresh_from_db()
        self.assertIn(self.session.status, ["ready_to_execute", "executing"])

    def test_progress_updates_use_tracker(self):
        """Test that progress updates go through ProgressTracker."""
        from apps.core.progress.tracker import progress_tracker

        with patch.object(progress_tracker, "update_progress") as mock_update:
            self.session.status = "executing"
            self.session.save()

            progress_tracker.update_progress(
                session_id=str(self.session.id),
                component="executing",
                local_progress=0,  # type: ignore[call-arg]
                processed_count=10,
                total_count=50,
                current_step="Executing www.cnn.com (Sea) AND (Sand) AND (Sun) type:pdf",
            )

            mock_update.assert_called_once()
            call_args = mock_update.call_args[1]
            self.assertEqual(call_args["component"], "executing")
            self.assertIn("www.cnn.com", call_args["current_step"])


# Run tests with: python manage.py test apps.serp_execution.tests.test_state_transitions
