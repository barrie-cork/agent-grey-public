"""Tests for the core state machine."""

from apps.core.state_machine import state_machine
from apps.core.state_machine.exceptions import InvalidTransition

from .test_base import StateMachineTestCase


class StateTransitionTests(StateMachineTestCase):
    """Test state transitions."""

    def test_valid_transition(self):
        """Test a valid state transition."""
        # Transition from draft to defining_search
        event = state_machine.transition(
            self.session.id, "defining_search", metadata={"test": True}
        )

        # Verify transition
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "defining_search")
        self.assertEqual(event.old_state, "draft")
        self.assertEqual(event.new_state, "defining_search")

        # Verify event was emitted
        self.assertEventEmitted("state_transition")

    def test_invalid_transition(self):
        """Test that invalid transitions are rejected."""
        # Try invalid transition from draft to completed
        with self.assertRaises(InvalidTransition) as context:
            state_machine.transition(self.session.id, "completed")

        self.assertIn("draft", str(context.exception))
        self.assertIn("completed", str(context.exception))

        # Verify state unchanged
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "draft")

    def test_automated_state_detection(self):
        """Test detection of automated states."""
        automated_states = [
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
        ]
        manual_states = [
            "draft",
            "defining_search",
            "under_review",
            "completed",
            "archived",
        ]

        for state in automated_states:
            self.assertTrue(
                state_machine.is_automated_state(state), f"{state} should be automated"
            )

        for state in manual_states:
            self.assertFalse(
                state_machine.is_automated_state(state), f"{state} should be manual"
            )

    def test_transition_with_user_context(self):
        """Test transition with user context."""
        event = state_machine.transition(
            self.session.id,
            "defining_search",
            user_id=str(self.user.id),
            triggered_by="user",
        )

        self.assertEqual(event.user_id, str(self.user.id))
        self.assertEqual(event.triggered_by, "user")

    def test_force_transition(self):
        """Test force transition for recovery."""
        # Force transition to a normally invalid state
        event = state_machine.force_transition(
            self.session.id, "completed", reason="Test force transition"
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")
        self.assertTrue(event.metadata.get("forced"))

        # Should emit recovery event
        self.assertEventEmitted("recovery")

    def test_session_history(self):
        """Test getting session transition history."""
        # Make several transitions
        state_machine.transition(self.session.id, "defining_search")

        # Set up search queries for the transition
        from apps.search_strategy.models import SearchQuery, SearchStrategy

        strategy = SearchStrategy.objects.create(session=self.session, user=self.user)
        SearchQuery.objects.create(
            strategy=strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            is_active=True,
        )

        state_machine.transition(self.session.id, "ready_to_execute")

        # Get history
        history = state_machine.get_session_history(str(self.session.id))

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["old_state"], "draft")
        self.assertEqual(history[0]["new_state"], "defining_search")
        self.assertEqual(history[1]["old_state"], "defining_search")
        self.assertEqual(history[1]["new_state"], "ready_to_execute")

    def test_progress_emission(self):
        """Test progress event emission."""
        state_machine.emit_progress(
            str(self.session.id),
            "executing",
            50,
            processed_count=25,
            total_count=50,
            current_step="Processing batch 3",
        )

        self.assertEventEmitted("progress_update")
        progress_events = self.get_events_by_type("progress_update")
        self.assertEqual(progress_events[0].processed_count, 25)
        self.assertEqual(progress_events[0].component, "executing")


class StateRegistryTests(StateMachineTestCase):
    """Test state registry functionality."""

    def test_all_states_registered(self):
        """Test that all required states are registered."""
        expected_states = [
            "draft",
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
            "completed",
            "archived",
            "failed",
        ]

        registered_states = state_machine.registry.get_all_states()
        for state in expected_states:
            self.assertIn(state, registered_states)

    def test_transition_matrix(self):
        """Test the transition matrix is correctly defined."""
        # Test some known valid transitions
        self.assertTransitionAllowed("draft", "defining_search")
        self.assertTransitionAllowed("defining_search", "ready_to_execute")
        self.assertTransitionAllowed("executing", "processing_results")
        self.assertTransitionAllowed("completed", "archived")

        # Test some invalid transitions
        self.assertTransitionDenied("draft", "completed")
        self.assertTransitionDenied("archived", "executing")
        self.assertTransitionDenied("completed", "draft")


class TimestampTests(StateMachineTestCase):
    """Test timestamp updates during transitions."""

    def test_started_at_timestamp(self):
        """Test started_at is set when transitioning to executing."""
        # Setup for valid transition
        from apps.search_strategy.models import SearchQuery, SearchStrategy

        strategy = SearchStrategy.objects.create(session=self.session, user=self.user)
        SearchQuery.objects.create(
            strategy=strategy,
            session=self.session,
            query_text="test",
            query_type="general",
            is_active=True,
        )

        # Transition through states
        state_machine.transition(self.session.id, "defining_search")
        state_machine.transition(self.session.id, "ready_to_execute")

        # Verify started_at is null
        self.session.refresh_from_db()
        self.assertIsNone(self.session.started_at)

        # Transition to executing
        state_machine.transition(self.session.id, "executing")

        # Verify started_at is set
        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.started_at)

    def test_completed_at_timestamp(self):
        """Test completed_at is set when transitioning to completed."""
        # Force transition to under_review
        state_machine.force_transition(self.session.id, "under_review", "test")

        # Verify completed_at is null
        self.session.refresh_from_db()
        self.assertIsNone(self.session.completed_at)

        # Transition to completed
        state_machine.transition(self.session.id, "completed")

        # Verify completed_at is set
        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.completed_at)
