"""
TypedDict definitions for results_manager API responses and internal processing.
Extended during Pydantic to TypedDict migration - Phase 2.
Replaces all Pydantic schemas with TypedDict definitions.
"""

from typing import Any, Dict, List, Literal, NotRequired, TypedDict

# Processing status literal types
ProcessingStatus = Literal["pending", "processing", "completed", "failed"]
ProcessingStage = Literal[
    "fetching",
    "url_normalization",
    "duplicate_detection",
    "metadata_extraction",
    "quality_scoring",
    "finalization",
]

# Result status types
ProcessingResultStatus = Literal[
    "started",
    "already_completed",
    "already_processing",
    "no_results",
    "failed",
    "error",
]

# Workflow status types
WorkflowCreationStatus = Literal["workflow_created", "failed"]


# API response types
class ProcessingStatusPendingResponse(TypedDict):
    """Type definition for processing status API response when processing hasn't started."""

    status: str
    progress_percentage: int
    message: str


class FilteringStatsData(TypedDict):
    """Type definition for filtering statistics data."""

    raw_results_retrieved: int
    total_processed_records: int
    results_by_status: Dict[str, int]
    success_rate_percent: float
    filter_rate_percent: float
    error_rate_percent: float
    filter_reasons: Dict[str, int]
    error_categories: Dict[str, int]
    accounting_check: Dict[str, Any]


class ProcessingStatusResponse(TypedDict):
    """Type definition for processing status API response with full processing data."""

    status: str
    progress_percentage: int
    current_stage: str
    stage_progress: int
    processed_count: int
    total_raw_results: int
    duplicate_count: int
    unique_count: int
    error_count: int
    estimated_completion: str | None  # ISO format timestamp
    estimated_time_remaining: str | None
    completed_stages: List[str]
    redirect_to_review: bool
    session_status: str
    total_results: int
    filtering_stats: FilteringStatsData


# Error response type
class ErrorResponse(TypedDict):
    """Type definition for API error responses."""

    success: bool
    error: str
    details: List[Dict[str, Any]] | None


# ============================================================================
# Result and Processing Types (from schemas.py)
# ============================================================================


class ProcessedResultSchema(TypedDict):
    """Schema for processed result responses.

    Mirrors get_processed_results() in api.py. Fields match ProcessedResult model
    plus computed is_duplicate property.
    """

    id: str
    title: str
    url: str
    snippet: str
    document_type: str
    is_pdf: bool
    has_full_text: bool
    publication_date: str | None  # ISO format
    is_duplicate: bool


class DeduplicationStatsSchema(TypedDict):
    """Schema for deduplication statistics."""

    total_results: int
    unique_results: int
    duplicates_removed: int
    deduplication_rate: float


class ProcessingStatsSchema(TypedDict):
    """Schema for processing statistics."""

    session_id: str
    total_raw_results: int
    processed_results: int
    failed_results: int
    processing_rate: float
    average_relevance: float
    document_types: Dict[str, int]
    publication_years: Dict[str, int]
    pdf_count: int
    unique_results: int
    duplicates_removed: int


class ExportRequestSchema(TypedDict):
    """Schema for export requests."""

    session_id: str
    format_type: Literal["csv", "json", "excel", "xlsx"]
    include_duplicates: bool
    filters: Dict[str, Any]


class ResultsListRequestSchema(TypedDict):
    """Schema for results list API requests."""

    page: int
    per_page: int
    sort_by: str
    sort_order: Literal["asc", "desc"]
    filters: Dict[str, Any]


class ResultsListResponseSchema(TypedDict):
    """Schema for paginated results list responses."""

    count: int
    next: str | None
    previous: str | None
    results: List[ProcessedResultSchema]
    statistics: ProcessingStatsSchema | None


class ProcessingProgressSchema(TypedDict):
    """Schema for processing progress updates."""

    session_id: str
    status: str
    total_queries: int
    completed_queries: int
    total_results: int
    processed_results: int
    failed_results: int
    progress_percentage: float
    estimated_time_remaining: int
    current_step: str


# ============================================================================
# Processing Session Types (from schemas/processing.py)
# ============================================================================


class ProcessingSessionInput(TypedDict):
    """Schema for process_session_results_task input validation."""

    session_id: str  # UUID as string


class ProcessingResult(TypedDict):
    """Schema for process_session_results_task output structure."""

    status: ProcessingResultStatus
    session_id: str  # UUID as string
    total_results: NotRequired[int]
    processed_count: NotRequired[int]
    workflow_task_id: NotRequired[str]
    message: NotRequired[str]
    error: NotRequired[str]
    timestamp: NotRequired[str]  # ISO format


class BatchProcessingRequest(TypedDict):
    """Schema for batch processing requests."""

    session_id: str  # UUID as string
    processing_session_id: str  # UUID as string
    batch_ids: List[str]
    batch_size: int


class NoResultsResponse(TypedDict):
    """Schema for handling no results cases."""

    session_id: str  # UUID as string
    completed_at: str  # ISO format
    reason: str
    status: NotRequired[Literal["no_results"]]
    message: NotRequired[str]
    total_results: NotRequired[int]
    automatic_transition: NotRequired[bool]


class ProcessingError(TypedDict, total=False):
    """Schema for processing error responses."""

    session_id: str  # UUID as string
    error: str
    error_type: str
    status: NotRequired[Literal["failed", "error"]]
    error_details: NotRequired[Dict[str, Any]]
    timestamp: NotRequired[str]  # ISO format
    retries_attempted: NotRequired[int]
    can_retry: NotRequired[bool]


class WorkflowCreationResult(TypedDict):
    """Schema for workflow creation results."""

    status: WorkflowCreationStatus
    session_id: str  # UUID as string
    processing_session_id: str  # UUID as string
    batch_count: NotRequired[int]
    workflow_id: NotRequired[str]
    error: NotRequired[str]
    timestamp: NotRequired[str]  # ISO format


class ProcessingProgress(TypedDict):
    """Schema for processing progress tracking."""

    session_id: str  # UUID as string
    processing_session_id: str  # UUID as string
    status: str
    total_raw_results: int
    processed_count: int
    failed_count: int
    progress_percentage: float
    batches_completed: int
    total_batches: int
    started_at: str  # ISO format
    estimated_completion: str  # ISO format
    current_step: str


class ProcessingSessionValidation(TypedDict):
    """Schema for processing session validation results."""

    is_valid: bool
    session_id: str  # UUID as string
    current_status: str
    can_process: bool
    error_message: str
    raw_results_count: int
    already_completed: bool
    processing_session_exists: bool


# ============================================================================
# Task Tracking Types (from schemas/task_tracking.py)
# ============================================================================


class TaskInfo(TypedDict):
    """Task registration information."""

    task_id: str
    started_at: str  # ISO format
    celery_task_id: str


class TaskHistoryEntry(TypedDict):
    """Single task history entry."""

    task_id: str
    started_at: str  # ISO format


class TaskMapping(TypedDict):
    """Task mapping for session tracking."""

    current_task: str
    task_history: List[TaskHistoryEntry]
    last_updated: str  # ISO format
    completed_at: str | None  # ISO format
