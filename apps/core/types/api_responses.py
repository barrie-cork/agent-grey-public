"""
Centralized TypedDict definitions for API responses.
Organized by domain for easy maintenance.
Part of Pydantic to TypedDict migration - Phase 2.
"""

from typing import Any, Dict, List, Literal, TypedDict

# Status literal types
StatusType = Literal[
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

ProcessingStatus = Literal["pending", "processing", "completed", "failed"]

# ============================================================================
# Core/Monitoring API Response Types
# ============================================================================


class ServiceStatus(TypedDict):
    """Service status in health checks."""

    name: str
    status: str
    message: str
    details: Dict[str, Any]


class HealthStatusResponse(TypedDict):
    """Health check API response."""

    status: str
    timestamp: str
    services: List[ServiceStatus]
    errors: List[str]


class MonitoringMetrics(TypedDict):
    """Monitoring metrics response."""

    celery_tasks: Dict[str, int]
    database_connections: int
    cache_hit_rate: float
    memory_usage_mb: float
    cpu_percent: float


class DebugInfoResponse(TypedDict):
    """Debug endpoint response."""

    environment: str
    debug_mode: bool
    version: str
    settings: Dict[str, Any]


class MetadataResponse(TypedDict):
    """Metadata API response."""

    app_version: str
    api_version: str
    supported_formats: List[str]
    available_endpoints: List[str]


class MetadataStatsResponse(TypedDict):
    """Metadata statistics response."""

    stats: Dict[str, Any]
    last_updated: str


class MetadataModelsResponse(TypedDict):
    """Metadata models response."""

    models: List[str]
    count: int


class MetadataSearchResponse(TypedDict):
    """Metadata search response."""

    query: str
    results: Dict[str, Any]
    total_matches: int


class MetadataHealthResponse(TypedDict):
    """Metadata health check response."""

    status: str
    metadata_available: bool
    last_updated: str | None
    records_count: int
    error: str | None


class RecentActivity(TypedDict):
    """Recent activity item."""

    id: str
    session_title: str
    type_display: str
    user: str
    time_ago: str


class MonitoringAPIResponse(TypedDict):
    """Workflow monitoring API response."""

    system_health: Dict[str, Any]
    workflow_stats: Dict[str, Any]
    recent_activities: List[RecentActivity]
    stuck_sessions_count: int
    timestamp: str


class RecoveryResult(TypedDict):
    """Recovery operation result."""

    success: bool
    message: str
    new_status: str | None
    session_id: str


class BulkRecoveryResult(TypedDict):
    """Bulk recovery operation result."""

    success: bool
    sessions_found: int
    sessions_recovered: int
    message: str
    details: str


class HealthCheckResponse(TypedDict):
    """Health check endpoint response."""

    status: str
    timestamp: str
    components: Dict[str, bool]
    stuck_sessions: int
    issues: List[str] | None


# ============================================================================
# Recovery API Response Types
# ============================================================================


class RecoveryStatusResponse(TypedDict):
    """Recovery operation status."""

    operation: str
    status: Literal["pending", "in_progress", "completed", "failed"]
    affected_sessions: int
    recovered_sessions: int
    errors: List[str]
    started_at: str
    completed_at: str | None


class StuckSessionInfo(TypedDict):
    """Information about stuck session."""

    id: str
    title: str
    status: str
    stuck_duration_minutes: float


class RecoverySystemStatusResponse(TypedDict, total=False):
    """Recovery system status response."""

    status: str
    stuck_sessions_count: int
    stuck_sessions: List[StuckSessionInfo]
    recent_recoveries_24h: int
    alert_thresholds: Dict[str, Any]
    transition_metrics: Dict[str, Any]
    timestamp: str


class SessionRecoveryResponse(TypedDict):
    """Single session recovery response."""

    success: bool
    session_id: str
    original_status: str | None
    new_status: str | None
    message: str
    duration_ms: int


class BulkRecoveryDetail(TypedDict):
    """Bulk recovery detail item."""

    session_id: str
    title: str
    original_status: str
    recovery_success: bool
    new_status: str | None
    error: str | None


class BulkRecoveryResponse(TypedDict):
    """Bulk recovery API response."""

    success: bool
    issues_detected: int
    recoveries_succeeded: int
    recoveries_failed: int
    details: List[BulkRecoveryDetail]


class MaintenanceTaskResponse(TypedDict):
    """Maintenance task trigger response."""

    success: bool
    task_name: str
    task_id: str
    message: str
    status_url: str


class CeleryTaskStatusResponse(TypedDict):
    """Celery task status response."""

    task_id: str
    status: str
    ready: bool
    successful: bool | None
    result: Any | None
    error: str | None


# ============================================================================
# Session Management Types (shared across apps)
# ============================================================================


class SessionStatsData(TypedDict):
    """Session statistics data."""

    total_queries: int
    completed_queries: int
    total_results: int
    errors: int
    retrieved_count: int


class SessionStatusResponse(TypedDict):
    """Session status API response."""

    session_id: str
    status: StatusType
    status_display: str
    progress: int
    redirect_url: str | None
    stats: SessionStatsData
    last_updated: str  # ISO format
    is_complete: bool


# ============================================================================
# Processing and Results Types
# ============================================================================


class ProcessingProgressResponse(TypedDict):
    """Processing progress API response."""

    session_id: str
    status: ProcessingStatus
    total_queries: int
    completed_queries: int
    total_results: int
    processed_results: int
    failed_results: int
    progress_percentage: float
    estimated_time_remaining: int
    current_step: str


class DeduplicationStatsResponse(TypedDict):
    """Deduplication statistics response."""

    total_results: int
    unique_results: int
    duplicates_removed: int
    deduplication_rate: float


# ============================================================================
# Error Response Types
# ============================================================================


class ValidationErrorDetail(TypedDict):
    """Individual validation error detail."""

    field: str
    message: str
    code: str
    value: Any | None


class StandardErrorResponse(TypedDict):
    """Standardized error response structure."""

    error: str
    error_type: str
    message: str
    details: Dict[str, Any] | None
    timestamp: str
    request_id: str | None
    field_errors: List[ValidationErrorDetail] | None


class ErrorResponse(TypedDict):
    """Standard error response."""

    error: str
    message: str
    details: Dict[str, Any] | None
    timestamp: str


class ValidationErrorResponse(TypedDict):
    """Validation error response."""

    error: str
    field_errors: Dict[str, List[str]]
    non_field_errors: List[str]


# ============================================================================
# Pagination Types
# ============================================================================


class PaginationMeta(TypedDict):
    """Pagination metadata."""

    count: int
    next: str | None
    previous: str | None
    page: int
    per_page: int
    total_pages: int


class PaginatedResponse(TypedDict):
    """Base paginated response."""

    results: List[Any]
    meta: PaginationMeta


# ============================================================================
# Success Response Types
# ============================================================================


class SuccessResponse(TypedDict):
    """Generic success response."""

    success: bool
    message: str
    data: Dict[str, Any] | None


class ActionResponse(TypedDict):
    """Response for action endpoints."""

    success: bool
    action: str
    result: Dict[str, Any]
    message: str
