"""Tests for the event system."""

import json

from apps.core.state_machine.event_bus import event_bus
from apps.core.state_machine.event_store import event_store
from apps.core.state_machine.events import (
    ErrorEvent,
    ProgressEvent,
    StateTransitionEvent,
)

from .test_base import StateMachineTestCase


class EventSystemTests(StateMachineTestCase):
    """Test event system functionality."""

    def test_event_serialization(self):
        """Test event serialization to JSON."""
        event = StateTransitionEvent(
            session_id=str(self.session.id),
            old_state="draft",
            new_state="defining_search",
            metadata={"key": "value"},
        )

        # Test to_dict
        event_dict = event.to_dict()
        self.assertEqual(event_dict["event_type"], "state_transition")
        self.assertEqual(event_dict["old_state"], "draft")
        self.assertEqual(event_dict["new_state"], "defining_search")

        # Test to_json
        event_json = event.to_json()
        parsed = json.loads(event_json)
        self.assertEqual(parsed["session_id"], str(self.session.id))

    def test_event_bus_subscription(self):
        """Test event bus subscription mechanism."""
        received_events = []

        def listener(event):
            received_events.append(event)

        # Subscribe to state transitions
        event_bus.subscribe("state_transition", listener)

        # Emit event
        event = StateTransitionEvent(
            session_id=str(self.session.id),
            old_state="draft",
            new_state="defining_search",
        )
        event_bus.emit(event)

        # Verify listener was called
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0], event)

    def test_event_persistence(self):
        """Test event persistence in cache."""
        event = StateTransitionEvent(
            session_id=str(self.session.id),
            old_state="draft",
            new_state="defining_search",
        )

        # Save event
        event_store.save_event(event)

        # Retrieve event
        retrieved = event_store.get_event(event.event_id)
        self.assertIsNotNone(retrieved)
        assert retrieved is not None
        self.assertEqual(retrieved["event_id"], event.event_id)

        # Retrieve session events
        session_events = event_store.get_session_events(str(self.session.id))
        self.assertGreater(len(session_events), 0)

        # Find our event
        found = False
        for e in session_events:
            if e["event_id"] == event.event_id:
                found = True
                self.assertEqual(e["event_type"], "state_transition")
        self.assertTrue(found, "Event should be in session events")

    def test_progress_event(self):
        """Test progress event creation and serialization."""
        event = ProgressEvent(
            session_id=str(self.session.id),
            component="executing",
            processed_count=25,
            total_count=50,
            current_step="Processing batch 3 of 5",
        )

        event_dict = event.to_dict()
        self.assertEqual(event_dict["event_type"], "progress_update")
        self.assertEqual(event_dict["component"], "executing")
        self.assertEqual(event_dict["processed_count"], 25)
        self.assertEqual(event_dict["total_count"], 50)

    def test_error_event(self):
        """Test error event creation."""
        event = ErrorEvent(
            session_id=str(self.session.id),
            error_type="ValueError",
            error_message="Test error",
            recoverable=True,
        )

        event_dict = event.to_dict()
        self.assertEqual(event_dict["event_type"], "error")
        self.assertEqual(event_dict["error_type"], "ValueError")
        self.assertTrue(event_dict["recoverable"])

    def test_event_bus_clear(self):
        """Test clearing event bus listeners."""
        received = []

        def listener(event):
            received.append(event)

        # Add listeners
        event_bus.subscribe("test_event", listener)
        event_bus.subscribe_all(listener)

        # Clear
        event_bus.clear()

        # Emit event - should not be received
        event = ErrorEvent(
            session_id=str(self.session.id),
            error_type="Test",
            error_message="Should not be received",
        )
        event_bus.emit(event)

        self.assertEqual(len(received), 0)

    def test_get_last_state_transition(self):
        """Test getting the last state transition event."""
        # Create multiple events
        event1 = StateTransitionEvent(
            session_id=str(self.session.id),
            old_state="draft",
            new_state="defining_search",
        )
        event_store.save_event(event1)

        event2 = StateTransitionEvent(
            session_id=str(self.session.id),
            old_state="defining_search",
            new_state="ready_to_execute",
        )
        event_store.save_event(event2)

        # Get last transition
        last = event_store.get_last_state_transition(str(self.session.id))
        self.assertIsNotNone(last)
        assert last is not None
        self.assertEqual(last["new_state"], "ready_to_execute")
