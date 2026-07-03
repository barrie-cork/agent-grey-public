"""Event subscription system for SSE."""

import logging
import queue
import threading
from typing import Dict, Optional

from django.core.cache import cache

from .events import BaseEvent

logger = logging.getLogger(__name__)


class EventSubscriber:
    """
    Subscribe to events for a specific session.
    Used by SSE endpoints to receive real-time updates.
    """

    # Class-level registry of active subscribers
    _subscribers: Dict[str, list] = {}
    _lock = threading.Lock()

    def __init__(self, session_id: str, buffer_size: int = 100):
        self.session_id = session_id
        self.queue = queue.Queue(maxsize=buffer_size)
        self.active = True
        self._register()

    def _register(self):
        """Register this subscriber."""
        with self._lock:
            if self.session_id not in self._subscribers:
                self._subscribers[self.session_id] = []
            self._subscribers[self.session_id].append(self)

        logger.debug(f"Registered subscriber for session {self.session_id}")

    def _unregister(self):
        """Unregister this subscriber."""
        with self._lock:
            if self.session_id in self._subscribers:
                try:
                    self._subscribers[self.session_id].remove(self)
                    if not self._subscribers[self.session_id]:
                        del self._subscribers[self.session_id]
                except ValueError:
                    pass  # Already removed

        logger.debug(f"Unregistered subscriber for session {self.session_id}")

    def send_event(self, event: BaseEvent):
        """Send an event to this subscriber."""
        if not self.active:
            return

        try:
            self.queue.put_nowait(event)
        except queue.Full:
            # Remove oldest event if buffer full
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(event)
            except queue.Empty:
                logger.warning(f"Failed to queue event for session {self.session_id}")

    def get_next_event(self, timeout: int = 30) -> Optional[BaseEvent]:
        """
        Get next event from queue.

        Args:
            timeout: Seconds to wait for event

        Returns:
            Event or None if timeout
        """
        if not self.active:
            return None

        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def cleanup(self):
        """Clean up subscriber."""
        self.active = False
        self._unregister()

        # Clear queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break

    @classmethod
    def broadcast_to_session(cls, session_id: str, event: BaseEvent):
        """
        Broadcast event to all subscribers of a session.

        This is called by the event bus to distribute events.
        """
        with cls._lock:
            subscribers = cls._subscribers.get(session_id, [])

        for subscriber in subscribers:
            subscriber.send_event(event)

        if subscribers:
            logger.debug(
                f"Broadcasted event to {len(subscribers)} subscribers "
                f"for session {session_id}"
            )

    @classmethod
    def get_subscriber_count(cls, session_id: str) -> int:
        """Get number of active subscribers for a session."""
        with cls._lock:
            return len(cls._subscribers.get(session_id, []))


class RetryQueue:
    """
    Queue for retrying failed event deliveries.
    Handles retry logic for failed event deliveries.
    """

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds

    def queue_for_retry(self, session_id: str, event: BaseEvent):
        """Queue an event for retry."""
        cache_key = f"sse:retry:{session_id}"

        # Get existing retry queue
        retry_list = cache.get(cache_key, [])

        # Add new event
        retry_list.append(
            {
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "data": event.to_dict(),
                "retry_count": 0,
            }
        )

        # Save back to cache
        cache.set(cache_key, retry_list, self.ttl)

        logger.info(f"Queued event {event.event_id} for retry")

    def get_retry_events(self, session_id: str) -> list:
        """Get all retry events for a session."""
        cache_key = f"sse:retry:{session_id}"
        return cache.get(cache_key, [])

    def clear_retry_queue(self, session_id: str):
        """Clear retry queue for a session."""
        cache_key = f"sse:retry:{session_id}"
        cache.delete(cache_key)


# Global retry queue
retry_queue = RetryQueue()
