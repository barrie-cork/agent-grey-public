"""
TypedDict definitions for Review Manager models.
Created during Phase 2 of TypedDict migration - Model Alignment.
Part of VSA-compliant model type system.
"""

from typing import Any, List, Literal, Optional, TypedDict

# JSONField Types


class ActivityMetadataType(TypedDict, total=False):
    """Type for SessionActivity.metadata JSONField.

    Using total=False as metadata fields are optional and vary by activity type.
    """

    old_status: str
    new_status: str
    old_value: Any
    new_value: Any
    user_id: str
    user_name: str
    timestamp: str  # ISO format
    error_message: Optional[str]
    recovery_action: Optional[str]
    transition_reason: Optional[str]


# Model Data Types
class SearchSessionData(TypedDict):
    """Complete serialization of SearchSession model."""

    id: str  # UUID as string
    title: str
    description: str
    status: Literal[
        "draft",
        "defining_search",
        "ready_to_execute",
        "executing",
        "processing_results",
        "ready_for_review",
        "under_review",
        "completed",
        "archived",
    ]
    status_detail: str
    owner_id: str  # UUID as string
    owner_username: str  # Denormalized
    created_at: str  # ISO format
    updated_at: str  # ISO format
    started_at: Optional[str]  # ISO format
    completed_at: Optional[str]  # ISO format
    notes: str
    total_queries: int
    total_results: int
    reviewed_results: int
    included_results: int
    # Computed properties
    progress_percentage: float
    inclusion_rate: float
    is_active: bool
    can_edit: bool
    can_delete: bool
    allowed_transitions: List[str]


class SessionActivityData(TypedDict):
    """Serialization of SessionActivity model."""

    id: str  # UUID as string
    session_id: str  # UUID as string
    session_title: str  # Denormalized
    user_id: Optional[str]  # UUID as string
    user_name: Optional[str]  # Denormalized
    activity_type: str
    description: str
    metadata: ActivityMetadataType
    created_at: str  # ISO format


class SessionStats(TypedDict):
    """Aggregated statistics for a SearchSession."""

    total_queries: int
    completed_queries: int
    pending_queries: int
    total_results: int
    processed_results: int
    reviewed_results: int
    included_results: int
    excluded_results: int
    maybe_results: int
    duplicate_count: int
    unique_results: int
    progress_percentage: float
    inclusion_rate: float
    average_relevance_score: float
    processing_duration_seconds: Optional[float]
    review_duration_seconds: Optional[float]


class SessionSummary(TypedDict):
    """Lightweight session representation for lists."""

    id: str  # UUID as string
    title: str
    status: str
    owner_username: str
    created_at: str  # ISO format
    updated_at: str  # ISO format
    progress_percentage: float
    total_results: int


class SessionStatusCount(TypedDict):
    """Status counts for dashboard."""

    draft: int
    defining_search: int
    ready_to_execute: int
    executing: int
    processing_results: int
    ready_for_review: int
    under_review: int
    completed: int
    archived: int
    total: int
