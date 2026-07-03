"""Base test case for state machine tests."""

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.core.state_machine import state_machine
from apps.core.state_machine.event_bus import event_bus
from apps.review_manager.models import SearchSession
from apps.core.tests.utils import create_test_user

User = get_user_model()


class StateMachineTestCase(TransactionTestCase):
    """Base test case with common setup for state machine tests."""

    def setUp(self):
        """Set up test fixtures."""
        super().setUp()

        # Clear event bus listeners for clean test environment
        event_bus.clear()

        # Re-register default listeners
        state_machine._register_default_listeners()

        # Create test user
        self.user = create_test_user()

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test session for state machine",
            owner=self.user,
            status="draft",
        )

        # Track emitted events for assertions
        self.emitted_events = []
        event_bus.subscribe_all(self._capture_event)

    def _capture_event(self, event):
        """Capture emitted events for testing."""
        self.emitted_events.append(event)

    def assertEventEmitted(self, event_type: str, count: int = 1):
        """Assert that a specific event type was emitted."""
        matching_events = [
            e
            for e in self.emitted_events
            if e.to_dict().get("event_type") == event_type
        ]
        self.assertEqual(
            len(matching_events),
            count,
            f"Expected {count} {event_type} events, got {len(matching_events)}",
        )

    def assertTransitionAllowed(self, from_state: str, to_state: str):
        """Assert that a transition is allowed."""
        self.assertTrue(
            state_machine.can_transition(from_state, to_state),
            f"Transition from {from_state} to {to_state} should be allowed",
        )

    def assertTransitionDenied(self, from_state: str, to_state: str):
        """Assert that a transition is not allowed."""
        self.assertFalse(
            state_machine.can_transition(from_state, to_state),
            f"Transition from {from_state} to {to_state} should be denied",
        )

    def get_events_by_type(self, event_type: str):
        """Get all emitted events of a specific type."""
        return [
            e
            for e in self.emitted_events
            if e.to_dict().get("event_type") == event_type
        ]
