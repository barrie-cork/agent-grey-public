"""Event definitions for the state machine."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, TypedDict

from django.utils import timezone


class PaginationInfo(TypedDict, total=False):
    """
    Structure for pagination metadata in query execution events.

    Used by QueryProgressEvent to provide detailed pagination information
    about query execution progress, including how many pages were fetched
    and why pagination stopped.

    Attributes:
        pages_fetched: Number of pages successfully retrieved
        stopped_reason: Why pagination stopped (e.g., 'limit_reached', 'no_more_results')
        max_pages: Maximum number of pages configured for pagination
        total_available: Total number of pages available from API (if known)
    """

    pages_fetched: int
    stopped_reason: str
    max_pages: int
    total_available: Optional[int]


@dataclass
class BaseEvent:
    """Base class for all events."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=timezone.now)
    session_id: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class StateTransitionEvent(BaseEvent):
    """Event fired when a state transition occurs."""

    old_state: str | None = None
    new_state: str | None = None
    triggered_by: str = "system"  # 'system', 'user', 'task'
    user_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "event_type": "state_transition",
                "old_state": self.old_state,
                "new_state": self.new_state,
                "triggered_by": self.triggered_by,
                "user_id": self.user_id,
            }
        )
        return data


@dataclass
class ProgressEvent(BaseEvent):
    """Event fired when status is updated."""

    component: str | None = None  # 'executing', 'processing_results', etc.
    processed_count: int = 0
    total_count: int = 0
    current_step: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "event_type": "progress_update",
                "component": self.component,
                "processed_count": self.processed_count,
                "total_count": self.total_count,
                "current_step": self.current_step,
            }
        )
        return data


@dataclass
class ErrorEvent(BaseEvent):
    """Event fired when an error occurs."""

    error_type: str | None = None
    error_message: str | None = None
    stack_trace: Optional[str] = None
    recoverable: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "event_type": "error",
                "error_type": self.error_type,
                "error_message": self.error_message,
                "stack_trace": self.stack_trace,
                "recoverable": self.recoverable,
            }
        )
        return data


@dataclass
class RecoveryEvent(BaseEvent):
    """Event fired when a recovery action is taken."""

    recovery_action: str | None = None
    original_state: str | None = None
    recovered_state: str | None = None
    reason: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "event_type": "recovery",
                "recovery_action": self.recovery_action,
                "original_state": self.original_state,
                "recovered_state": self.recovered_state,
                "reason": self.reason,
            }
        )
        return data


@dataclass
class QueryProgressEvent(BaseEvent):
    """Event emitted during query execution for real-time progress visibility."""

    query_index: int = 0
    total_queries: int = 0
    query_text: str = ""
    status: str = "pending"  # 'pending', 'starting', 'completed', 'failed'
    results_count: int = 0
    target_domain: Optional[str] = None
    # Pagination metadata (see PaginationInfo TypedDict)
    pagination_info: Optional[PaginationInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with progress percentage calculation."""
        data = super().to_dict()

        # Calculate progress percentage
        progress_percent = 0
        if self.total_queries > 0:
            if self.status == "completed":
                progress_percent = int((self.query_index / self.total_queries) * 100)
            else:  # starting
                progress_percent = int(
                    ((self.query_index - 1) / self.total_queries) * 100
                )

        data.update(
            {
                "event_type": "query_progress",
                "query_index": self.query_index,
                "total_queries": self.total_queries,
                "query_text": self.query_text[:100],  # Truncate for safety
                "status": self.status,
                "results_count": self.results_count,
                "target_domain": self.target_domain,
                "progress_percent": progress_percent,
                "pagination_info": self.pagination_info
                or {},  # NEW: include pagination data
            }
        )
        return data
