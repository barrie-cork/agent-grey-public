"""Unified progress tracking system."""

import logging
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.utils import timezone

from apps.core.state_machine.event_bus import event_bus
from apps.core.state_machine.events import ProgressEvent

logger = logging.getLogger(__name__)


class ProgressTracker:
    """
    Single source of truth for all progress calculations.
    Replaces 4 different conflicting progress formulas.
    """

    # Valid component names (no percentages)
    VALID_COMPONENTS = [
        "defining_search",
        "ready_to_execute",
        "executing",
        "processing_results",
        "deduplication",
        "finalization",
        "ready_for_review",
        "under_review",
        "completed",
    ]

    def __init__(self):
        self.cache_ttl = 3600  # 1 hour

    def update_progress(
        self,
        session_id: str,
        component: str,
        processed_count: int = 0,
        total_count: int = 0,
        current_step: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update status for a session component.
        NO PERCENTAGE CALCULATIONS.

        Args:
            session_id: Session UUID
            component: Component name (e.g., 'executing', 'processing_results')
            processed_count: Number of items processed
            total_count: Total number of items
            current_step: Human-readable current step
            metadata: Additional metadata
        """
        # Validate component name
        if component not in self.VALID_COMPONENTS:
            logger.warning(f"Unknown component: {component}")

        # Store status in cache (NO progress field)
        self._store_status(
            session_id, component, processed_count, total_count, current_step
        )

        # Create and emit status event (NO progress field)
        event = ProgressEvent(
            session_id=session_id,
            component=component,
            processed_count=processed_count,
            total_count=total_count,
            current_step=current_step,
            metadata=metadata or {},
        )

        event_bus.emit(event)

        logger.info(
            f"Status updated for session {session_id}: "
            f"{component} - {current_step} "
            f"({processed_count}/{total_count})"
        )

    def _store_status(
        self,
        session_id: str,
        component: str,
        processed: int,
        total: int,
        current_step: str,
    ):
        """Store status in cache for recovery."""
        cache_key = f"progress:{session_id}"

        status_data = cache.get(cache_key, {})
        status_data[component] = {
            "processed": processed,
            "total": total,
            "current_step": current_step,
            "timestamp": timezone.now().isoformat(),
        }

        cache.set(cache_key, status_data, self.cache_ttl)

    def get_progress(self, session_id: str) -> Dict[str, Any]:
        """
        Get current status for a session.
        NO PERCENTAGES.

        Returns:
            Dictionary with status information
        """
        cache_key = f"progress:{session_id}"
        status_data = cache.get(cache_key, {})

        # Get latest component status
        if status_data:
            components = list(status_data.keys())
            if components:
                # Use the most recent component
                latest_component = max(
                    components, key=lambda c: status_data[c].get("timestamp", "")
                )
                return {
                    "status": "active",
                    "component": latest_component,
                    "current_step": status_data[latest_component].get(
                        "current_step", ""
                    ),
                    "processed_count": status_data[latest_component].get(
                        "processed", 0
                    ),
                    "total_count": status_data[latest_component].get("total", 0),
                    "components": status_data,
                }

        return {
            "status": "unknown",
            "component": "",
            "current_step": "",
            "processed_count": 0,
            "total_count": 0,
            "components": {},
        }

    def reset_progress(self, session_id: str):
        """Reset all status for a session."""
        cache_key = f"progress:{session_id}"
        cache.delete(cache_key)

        logger.info(f"Reset status for session {session_id}")


# Global progress tracker instance
progress_tracker = ProgressTracker()
