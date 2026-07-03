"""Event persistence layer for audit and recovery."""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from django.core.cache import cache

from .events import BaseEvent

logger = logging.getLogger(__name__)


class EventStore:
    """Store events for audit trail and recovery."""

    def __init__(self, ttl_seconds: int = 86400):  # 24 hours default
        self.ttl = ttl_seconds

    def save_event(self, event: BaseEvent):
        """Save an event to the store."""
        # Create cache keys
        event_key = f"event:{event.event_id}"
        session_key = f"session_events:{event.session_id}"
        type_key = f"event_type:{event.to_dict().get('event_type', 'unknown')}"

        # Save the event
        cache.set(event_key, event.to_json(), self.ttl)

        # Add to session's event list
        event_list = cache.get(session_key, [])
        event_list.append(
            {
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.to_dict().get("event_type", "unknown"),
            }
        )
        cache.set(session_key, event_list, self.ttl)

        # Add to event type list
        type_list = cache.get(type_key, [])
        type_list.append(event.event_id)
        # Keep only last 1000 events per type
        if len(type_list) > 1000:
            type_list = type_list[-1000:]
        cache.set(type_key, type_list, self.ttl)

        logger.debug(f"Saved event {event.event_id} to store")

    def get_event(self, event_id: str) -> Optional[Dict]:
        """Retrieve a specific event."""
        event_json = cache.get(f"event:{event_id}")
        if event_json:
            return json.loads(event_json)
        return None

    def get_session_events(
        self, session_id: str, event_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict]:
        """Get all events for a session, optionally filtered by type."""
        event_list = cache.get(f"session_events:{session_id}", [])

        if event_type:
            event_list = [e for e in event_list if e.get("event_type") == event_type]

        # Apply limit
        if len(event_list) > limit:
            event_list = event_list[-limit:]

        # Retrieve full event details
        events = []
        for event_info in event_list:
            event = self.get_event(event_info["event_id"])
            if event:
                events.append(event)

        return events

    def get_recent_events(
        self, minutes: int = 60, event_type: Optional[str] = None
    ) -> List[Dict]:
        """Get all events from the last N minutes."""
        events = []
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()

        if event_type:
            # Get events by type
            event_ids = cache.get(f"event_type:{event_type}", [])
            for event_id in event_ids[-100:]:  # Check last 100
                event = self.get_event(event_id)
                if event and event.get("timestamp", "") > cutoff:
                    events.append(event)

        return events

    def get_last_state_transition(self, session_id: str) -> Optional[Dict]:
        """Get the most recent state transition event for a session."""
        transitions = self.get_session_events(
            session_id, event_type="state_transition", limit=1
        )
        return transitions[0] if transitions else None

    def clear_session_events(self, session_id: str):
        """Clear all events for a session."""
        event_list = cache.get(f"session_events:{session_id}", [])
        for event_info in event_list:
            cache.delete(f"event:{event_info['event_id']}")
        cache.delete(f"session_events:{session_id}")
        logger.info(f"Cleared all events for session {session_id}")

    def get_error_events(
        self, session_id: str | None = None, limit: int = 10
    ) -> List[Dict]:
        """Get recent error events."""
        if session_id:
            return self.get_session_events(session_id, event_type="error", limit=limit)
        return self.get_recent_events(minutes=60, event_type="error")

    def get_recovery_events(
        self, session_id: str | None = None, limit: int = 10
    ) -> List[Dict]:
        """Get recent recovery events."""
        if session_id:
            return self.get_session_events(
                session_id, event_type="recovery", limit=limit
            )
        return self.get_recent_events(minutes=60, event_type="recovery")


# Global event store instance
event_store = EventStore()
