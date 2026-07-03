"""
Task deduplication service for managing concurrent task execution.

This service handles the registration and tracking of tasks to prevent
duplicate processing of the same session.
"""

import logging
import uuid
from typing import Optional, TypedDict

from celery import current_task
from django.utils import timezone

from apps.core.cache_utils import (
    safe_cache_add,
    safe_cache_delete,
    safe_cache_get,
    safe_cache_set,
)

logger = logging.getLogger(__name__)


class TaskRegistration(TypedDict):
    """Type-safe task registration result."""

    success: bool
    task_id: str
    reason: str | None
    existing_task: dict | None


class TaskDeduplicationService:
    """
    Handles task deduplication logic for session processing.

    This service ensures that only one task processes a session at a time,
    preventing race conditions and duplicate processing.
    """

    DEFAULT_TIMEOUT = 600  # 10 minutes
    MAPPING_TIMEOUT = 3600  # 1 hour
    MAX_HISTORY_SIZE = 10

    def __init__(self, session_id: str):
        """
        Initialize the deduplication service.

        Args:
            session_id: The session ID to manage deduplication for
        """
        self.session_id = str(session_id)
        self.task_id = str(uuid.uuid4())
        self.running_key = f"task_running_{self.session_id}"
        self.mapping_key = f"session_task_map_{self.session_id}"

    def check_and_register(self, timeout: int | None = None) -> TaskRegistration:
        """
        Check for duplicates and register if unique.

        Args:
            timeout: Optional timeout override (defaults to DEFAULT_TIMEOUT)

        Returns:
            TaskRegistration result indicating success or failure
        """
        timeout = timeout or self.DEFAULT_TIMEOUT

        # Check if task is already running
        existing_task = self._check_existing_task()
        if existing_task:
            logger.info(
                f"Task already running for session {self.session_id}. "
                f"Existing task: {existing_task}"
            )
            result: TaskRegistration = {
                "success": False,
                "task_id": self.task_id,
                "reason": "duplicate_task",
                "existing_task": existing_task,
            }
            return result

        # Try to register this task
        if not self._register_task(timeout):
            # Another task started between check and registration
            logger.warning(f"Race condition detected for session {self.session_id}")
            result = {
                "success": False,
                "task_id": self.task_id,
                "reason": "race_condition",
                "existing_task": None,
            }
            return result

        # Create/update task mapping for debugging
        self._update_task_mapping()

        result = {
            "success": True,
            "task_id": self.task_id,
            "reason": None,
            "existing_task": None,
        }
        return result

    def _check_existing_task(self) -> Optional[dict]:
        """Check if a task is already running for this session."""
        return safe_cache_get(self.running_key)

    def _register_task(self, timeout: int) -> bool:
        """
        Register this task as running.

        Args:
            timeout: How long to keep the registration

        Returns:
            True if successfully registered, False if another task is running
        """
        task_info = {
            "task_id": self.task_id,
            "started_at": timezone.now().isoformat(),
            "celery_task_id": current_task.request.id if current_task else None,
        }

        # Use cache.add() - only succeeds if key doesn't exist
        success = safe_cache_add(self.running_key, task_info, timeout)

        if success:
            logger.info(
                f"Registered task {self.task_id} as running for session {self.session_id}"
            )
        else:
            logger.warning(
                f"Could not register task {self.task_id} - another task is running"
            )

        return success

    def _update_task_mapping(self):
        """Update the task mapping for debugging and monitoring."""
        # Get existing mapping or create new one
        existing_mapping = safe_cache_get(self.mapping_key) or {
            "current_task": None,
            "task_history": [],
            "last_updated": None,
        }

        # Update with new task
        existing_mapping["current_task"] = self.task_id
        existing_mapping["task_history"].append(
            {"task_id": self.task_id, "started_at": timezone.now().isoformat()}
        )
        existing_mapping["last_updated"] = timezone.now().isoformat()

        # Keep only last N tasks in history
        if len(existing_mapping["task_history"]) > self.MAX_HISTORY_SIZE:
            existing_mapping["task_history"] = existing_mapping["task_history"][
                -self.MAX_HISTORY_SIZE :
            ]

        # Store mapping
        safe_cache_set(self.mapping_key, existing_mapping, timeout=self.MAPPING_TIMEOUT)

        logger.info(
            f"Task mapping for session {self.session_id}: "
            f"Current task: {self.task_id}, "
            f"History count: {len(existing_mapping.get('task_history', []))}"
        )

    def cleanup(self):
        """Clean up task registration when task completes."""
        # Only delete if this task owns the key
        existing = safe_cache_get(self.running_key)
        if existing and existing.get("task_id") == self.task_id:
            safe_cache_delete(self.running_key)
            logger.info(
                f"Unregistered task {self.task_id} for session {self.session_id}"
            )

        # Clear current task from mapping
        self._clear_task_mapping()

    def _clear_task_mapping(self):
        """Clear the current task from the mapping."""
        mapping = safe_cache_get(self.mapping_key)
        if mapping and mapping.get("current_task") == self.task_id:
            mapping["current_task"] = None
            mapping["completed_at"] = timezone.now().isoformat()
            safe_cache_set(self.mapping_key, mapping, timeout=self.MAPPING_TIMEOUT)
            logger.info(f"Cleared task {self.task_id} from session mapping")

    def get_task_history(self) -> list:
        """
        Get the task history for this session.

        Returns:
            List of task history entries
        """
        mapping = safe_cache_get(self.mapping_key) or {}
        return mapping.get("task_history", [])
