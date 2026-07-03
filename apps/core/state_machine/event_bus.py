"""Event bus for distributing events to listeners."""

import logging
from collections import defaultdict
from typing import Callable, Dict, List

from .events import BaseEvent

logger = logging.getLogger(__name__)


class EventBus:
    """Central event distribution system."""

    def __init__(self):
        # Dictionary mapping event types to list of listeners
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._global_listeners: List[Callable] = []

    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to a specific event type."""
        if not callable(callback):
            raise ValueError(f"Callback must be callable, got {type(callback)}")

        self._listeners[event_type].append(callback)
        logger.debug(f"Subscribed {callback.__name__} to {event_type}")

    def subscribe_all(self, callback: Callable):
        """Subscribe to all events."""
        if not callable(callback):
            raise ValueError(f"Callback must be callable, got {type(callback)}")

        self._global_listeners.append(callback)
        logger.debug(f"Subscribed {callback.__name__} to all events")

    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from a specific event type."""
        if callback in self._listeners[event_type]:
            self._listeners[event_type].remove(callback)
            logger.debug(f"Unsubscribed {callback.__name__} from {event_type}")

    def _send_to_sse_subscribers(self, event: BaseEvent):
        """Send event to SSE subscribers."""
        from apps.core.state_machine.event_subscribers import EventSubscriber

        # Broadcast to session subscribers
        if hasattr(event, "session_id") and event.session_id:
            EventSubscriber.broadcast_to_session(str(event.session_id), event)

            # Log subscription metrics
            count = EventSubscriber.get_subscriber_count(str(event.session_id))
            if count > 0:
                logger.info(
                    f"Sent {event.__class__.__name__} to {count} SSE subscribers"
                )

    def emit(self, event: BaseEvent):
        """Emit an event to all relevant listeners."""
        event_dict = event.to_dict()
        event_type = event_dict.get("event_type", "unknown")

        # Sanitize metadata for transmission
        if hasattr(event, "metadata") and event.metadata:
            # Simple metadata sanitization - ensure JSON serializable
            import json

            try:
                # Test if metadata is JSON serializable, if not, use str representation
                json.dumps(event.metadata)
            except (TypeError, ValueError):
                # Convert non-serializable objects to string representation
                event.metadata = {
                    k: (
                        str(v)
                        if not isinstance(
                            v, (str, int, float, bool, list, dict, type(None))
                        )
                        else v
                    )
                    for k, v in (
                        event.metadata.items()
                        if isinstance(event.metadata, dict)
                        else {}
                    )
                }

        # Send to SSE subscribers (NEW)
        self._send_to_sse_subscribers(event)

        # Notify specific listeners
        for listener in self._listeners[event_type]:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error in event listener {listener.__name__}: {e}")

        # Notify global listeners
        for listener in self._global_listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error in global listener {listener.__name__}: {e}")

        logger.info(f"Emitted {event_type} event for session {event.session_id}")

    def clear(self):
        """Clear all listeners (useful for testing)."""
        self._listeners.clear()
        self._global_listeners.clear()

    def get_listener_count(self, event_type: str | None = None) -> int:
        """Get count of listeners for a specific event type or total."""
        if event_type:
            return len(self._listeners.get(event_type, []))
        return sum(len(listeners) for listeners in self._listeners.values()) + len(
            self._global_listeners
        )


# Global event bus instance
event_bus = EventBus()
