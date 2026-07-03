"""
Internal processing type definitions.
TypedDict definitions for internal data structures and processing logic.
Part of Pydantic to TypedDict migration - Phase 2.
"""

from typing import Any, Dict, List, Literal, TypedDict

# ============================================================================
# Task Processing Types
# ============================================================================


class TaskInfo(TypedDict):
    """Task registration information."""

    task_id: str
    started_at: str  # ISO format timestamp
    celery_task_id: str


class TaskHistoryEntry(TypedDict):
    """Single task history entry."""

    task_id: str
    started_at: str  # ISO format timestamp


class TaskMapping(TypedDict):
    """Task mapping for session tracking."""

    current_task: str
    task_history: List[TaskHistoryEntry]
    last_updated: str  # ISO format timestamp
    completed_at: str | None  # ISO format timestamp


# ============================================================================
# Batch Processing Types
# ============================================================================


class BatchProcessingRequest(TypedDict):
    """Batch processing request structure."""

    session_id: str
    processing_session_id: str
    batch_ids: List[str]
    batch_size: int


class BatchProcessingResult(TypedDict):
    """Batch processing result."""

    batch_id: str
    processed_count: int
    failed_count: int
    error_messages: List[str]


# ============================================================================
# Workflow Types
# ============================================================================

WorkflowStatus = Literal["created", "running", "completed", "failed", "cancelled"]


class WorkflowCreationResult(TypedDict):
    """Workflow creation result."""

    status: Literal["workflow_created", "failed"]
    session_id: str
    processing_session_id: str
    batch_count: int
    workflow_id: str
    error: str
    timestamp: str  # ISO format


class WorkflowProgress(TypedDict):
    """Workflow progress tracking."""

    workflow_id: str
    status: WorkflowStatus
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    progress_percentage: float
    started_at: str  # ISO format
    estimated_completion: str | None  # ISO format


# ============================================================================
# Processing Session Types
# ============================================================================

ProcessingStage = Literal[
    "initializing",
    "fetching",
    "url_normalization",
    "duplicate_detection",
    "metadata_extraction",
    "quality_scoring",
    "finalization",
]


class ProcessingSessionInput(TypedDict):
    """Processing session input validation."""

    session_id: str


class ProcessingResult(TypedDict):
    """Processing task result."""

    status: Literal[
        "started",
        "already_completed",
        "already_processing",
        "no_results",
        "failed",
        "error",
    ]
    session_id: str
    total_results: int
    processed_count: int
    workflow_task_id: str
    message: str
    error: str
    timestamp: str  # ISO format


class ProcessingProgress(TypedDict):
    """Processing progress tracking."""

    session_id: str
    processing_session_id: str
    status: str
    total_raw_results: int
    processed_count: int
    failed_count: int
    progress_percentage: float
    batches_completed: int
    total_batches: int
    started_at: str  # ISO format
    estimated_completion: str  # ISO format
    current_step: ProcessingStage


class ProcessingSessionValidation(TypedDict):
    """Processing session validation results."""

    is_valid: bool
    session_id: str
    current_status: str
    can_process: bool
    error_message: str
    raw_results_count: int
    already_completed: bool
    processing_session_exists: bool


# ============================================================================
# Error Handling Types
# ============================================================================

ErrorSeverity = Literal["low", "medium", "high", "critical"]


class ErrorContext(TypedDict):
    """Error context information."""

    severity: ErrorSeverity
    component: str
    operation: str
    traceback: str | None
    user_message: str
    technical_details: Dict[str, Any]


# ============================================================================
# No Results Response Types
# ============================================================================


class NoResultsResponse(TypedDict):
    """Response for no results cases."""

    status: Literal["no_results"]
    session_id: str
    message: str
    total_results: int
    completed_at: str  # ISO format
    reason: str
    automatic_transition: bool


# ============================================================================
# Cache Types
# ============================================================================


class CacheEntry(TypedDict):
    """Cache entry structure."""

    key: str
    value: Any
    expires_at: str  # ISO format
    created_at: str  # ISO format
    access_count: int
    last_accessed: str  # ISO format


class CacheStats(TypedDict):
    """Cache statistics."""

    total_entries: int
    memory_usage_bytes: int
    hit_rate: float
    miss_rate: float
    eviction_count: int


# ============================================================================
# Configuration Types
# ============================================================================


class ServiceConfig(TypedDict):
    """Service configuration."""

    enabled: bool
    timeout_seconds: int
    retry_attempts: int
    rate_limit: int
    additional_settings: Dict[str, Any]


class SystemConfig(TypedDict):
    """System configuration."""

    environment: Literal["development", "staging", "production"]
    debug_mode: bool
    services: Dict[str, ServiceConfig]
    feature_flags: Dict[str, bool]
