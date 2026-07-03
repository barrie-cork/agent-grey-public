"""
TypedDict definitions for Review Results models.
Created during Phase 2 of TypedDict migration - Model Alignment.
Part of VSA-compliant model type system.
"""

from typing import Any, Dict, List, Literal, Optional, TypedDict


class SimpleReviewDecisionData(TypedDict):
    """Serialization of SimpleReviewDecision model."""

    id: str  # UUID as string
    session_id: str  # UUID as string - denormalized field
    result_id: str  # UUID as string
    reviewer_id: Optional[str]  # UUID as string, can be null
    reviewer_username: Optional[str]  # Denormalized, can be null
    decision: Literal["pending", "include", "exclude", "maybe"]
    exclusion_reason: str  # Only when decision is "exclude"
    notes: str
    reviewed_at: str  # ISO format
    updated_at: str  # ISO format


class URLAccessLogData(TypedDict):
    """Serialization of URLAccessLog model."""

    id: str  # UUID as string
    session_id: str  # UUID as string - denormalized field
    result_id: str  # UUID as string
    user_id: Optional[str]  # UUID as string, can be null
    user_username: Optional[str]  # Denormalized, can be null
    accessed_at: str  # ISO format
    access_successful: bool
    failure_reason: str  # Only when access_successful is False


class DecisionStats(TypedDict):
    """Statistics for review decisions."""

    total_decisions: int
    pending_count: int
    include_count: int
    exclude_count: int
    maybe_count: int
    include_percentage: float
    exclude_percentage: float
    maybe_percentage: float
    pending_percentage: float
    total_reviewers: int
    most_common_exclude_reasons: List[Dict[str, Any]]  # [{reason, count}]


class ReviewProgress(TypedDict):
    """Review progress tracking."""

    session_id: str  # UUID as string
    total_results: int
    reviewed_count: int
    pending_count: int
    include_count: int
    exclude_count: int
    maybe_count: int
    progress_percentage: float
    estimated_time_remaining: Optional[int]  # seconds


class URLAccessStats(TypedDict):
    """URL access statistics."""

    session_id: str  # UUID as string
    total_urls: int
    accessed_count: int
    successful_access_count: int
    failed_access_count: int
    success_rate: float
    unique_users: int
    most_common_failure_reasons: List[Dict[str, Any]]  # [{reason, count}]
