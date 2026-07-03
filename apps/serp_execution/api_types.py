"""
TypedDict definitions for serp_execution API responses.
Created during Pydantic to TypedDict migration - Phase 1.
"""

from typing import Any, Dict, List, Literal, NotRequired, TypedDict

# Execution status types
ExecutionStatus = Literal[
    "pending", "running", "completed", "failed", "cancelled", "retrying"
]


# Core data types
class ExecutionData(TypedDict):
    """Type definition for individual execution data."""

    id: str
    query_id: str
    status: ExecutionStatus
    results_count: int
    execution_time: float | None
    started_at: str | None  # ISO format
    completed_at: str | None  # ISO format


class SessionExecutionDataResponse(TypedDict):
    """Type definition for session execution data API response."""

    executions: List[ExecutionData]
    total_count: int
    completed_count: int
    failed_count: int
    pending_count: int


class RawResultsCountResponse(TypedDict):
    """Type definition for raw results count API response."""

    count: int
    session_id: str | None
    execution_id: str | None


class ExecutionStatsResponse(TypedDict):
    """Type definition for execution statistics API response."""

    total_executions: int
    successful_executions: int
    failed_executions: int
    average_duration: float
    total_results: int


# Error responses
class ErrorResponse(TypedDict):
    """Type definition for error responses."""

    error: str
    error_type: str
    details: Dict[str, Any] | None
    status_code: int


# Session progress types
class QueryStatsData(TypedDict):
    """Type definition for query statistics."""

    total_queries: int
    completed_queries: int
    running_queries: int
    failed_queries: int


class SessionProgressResponse(TypedDict):
    """Type definition for session progress API response."""

    session_id: str
    session_status: str
    status: str
    current_step: str
    component: str


class QuickStatusCurrentQuery(TypedDict, total=False):
    """Current query payload for streaming execution feed."""

    execution_id: str
    query_text: str
    status: ExecutionStatus
    current_page: int | None
    total_pages: int | None
    results_so_far: int
    stopped_reason: str | None


class QuickStatusRecentQuery(TypedDict, total=False):
    """Recently completed query payload for streaming execution feed."""

    query_text: str
    results_count: int
    pages_fetched: int | None
    stopped_reason: str | None
    completed_at: str | None


class SessionQuickStatusResponse(TypedDict, total=False):
    """Type definition for session quick status API response."""

    session_id: str
    status: str
    session_status_display: str
    status_detail: str | None
    current_step: str
    processed_count: int
    total_count: int
    total_queries: int
    completed_queries: int
    progress_percentage: float
    total_raw_results: int
    query_stats: QueryStatsData
    metadata: Dict[str, Any]
    current_query: QuickStatusCurrentQuery | None
    recent_queries: List[QuickStatusRecentQuery]
    timestamp: str


# Query progress types
class QueryProgressEntry(TypedDict):
    """Type definition for individual query progress entry."""

    execution_id: str
    query_id: str
    query_text: str
    status: ExecutionStatus
    current_step: str | None
    processing_phase: str | None
    results_count: int
    error_message: str
    is_active: bool
    started_at: str | None  # ISO format
    completed_at: str | None  # ISO format
    duration_seconds: float | None


class QueryProgressResponse(TypedDict):
    """Type definition for query progress API response."""

    session_id: str
    session_status: str
    total_queries: int
    completed_queries: int
    current_query: QueryProgressEntry | None
    queries: List[QueryProgressEntry]
    timestamp: str  # ISO format


# Diagnostic types
class SessionDiagnosticExecutions(TypedDict):
    """Type definition for diagnostic execution data."""

    total: int
    completed: int
    failed: int


class SessionDiagnosticResults(TypedDict):
    """Type definition for diagnostic results data."""

    total: int
    unique: int


class SessionDiagnosticTiming(TypedDict):
    """Type definition for diagnostic timing data."""

    time_in_current_state: float


class SessionDiagnosticHealthChecks(TypedDict):
    """Type definition for diagnostic health checks."""

    has_owner: bool
    has_strategy: bool
    has_queries: bool
    celery_task_id: str | None


class SessionDiagnosticResponse(TypedDict):
    """Type definition for session diagnostic API response."""

    session: Dict[str, Any]  # Session data varies
    executions: SessionDiagnosticExecutions
    results: SessionDiagnosticResults
    timing: SessionDiagnosticTiming
    health_checks: SessionDiagnosticHealthChecks
    warnings: List[str]


# Test API types (for development/testing)
class TestSessionCreateResponse(TypedDict):
    """Type definition for test session creation response."""

    session_id: str
    title: str
    status: str
    created: bool


class TestSessionUpdateResponse(TypedDict):
    """Type definition for test session update response."""

    session_id: str
    status: str
    updated: bool


# Additional API response types from schemas.py
class ExecutionStatusResponse(TypedDict):
    """Type definition for individual execution status response."""

    id: str
    status: ExecutionStatus
    status_display: str
    results_count: int
    current_step: str | None
    error_message: str | None
    duration_seconds: float | None
    can_retry: bool
    created_at: str  # ISO format
    completed_at: str | None  # ISO format


class RawResultResponse(TypedDict):
    """Type definition for raw search result response."""

    id: str
    execution_id: str
    title: str
    url: str
    snippet: str
    position: int
    raw_data: Dict[str, Any]
    source_metadata: Dict[str, Any]
    created_at: str  # ISO format


class RetryExecutionResponse(TypedDict):
    """Type definition for retry execution response."""

    success: bool
    execution_id: str
    message: str
    new_status: str | None


class CancelSessionResponse(TypedDict):
    """Type definition for cancel session response."""

    success: bool
    cancelled_count: int
    failed_cancellations: List[Dict[str, Any]]
    session_status: str
    has_active_executions: bool
    message: str


class DiagnosticTestResponse(TypedDict):
    """Type definition for diagnostic API test response."""

    success: bool
    query: str
    num_requested: int
    response_keys: List[str]
    organic_count: int
    metadata: Dict[str, Any]
    has_organic: bool
    alternative_results: Dict[str, int]
    first_result_structure: Dict[str, Any] | None
    api_status: str
    processing_test: Dict[str, Any] | None


# Task execution result types
class TaskExecutionResult(TypedDict):
    """Type definition for task execution results."""

    success: bool
    session_id: str
    error: NotRequired[str | None]
    error_type: NotRequired[str | None]
    metadata: NotRequired[Dict[str, Any]]
    timestamp: NotRequired[str]


class SessionExecutionResult(TaskExecutionResult):
    """Type definition for session execution task results."""

    queries_count: NotRequired[int]
    status: NotRequired[str]
    execution_ids: NotRequired[List[str]]
    task_id: NotRequired[str | None]


class QueryExecutionResult(TaskExecutionResult):
    """Type definition for query execution task results."""

    query_id: str
    execution_id: str
    results_count: int
    api_response_time: NotRequired[float | None]
    credits_used: NotRequired[int]


class SessionValidationResult(TypedDict):
    """Type definition for session validation results."""

    is_valid: bool
    session_id: str
    current_status: str
    error_message: str | None
    can_execute: bool
    query_count: int


class ExecutionPlan(TypedDict):
    """Type definition for execution plan."""

    session_id: str
    query_ids: List[str]  # List of query UUID strings
    execution_strategy: str  # 'parallel' or 'sequential'
    estimated_duration: int | None  # seconds
    total_queries: int


# Progress tracking types
class ExecutionProgress(TypedDict):
    """Type definition for execution progress responses."""

    session_id: str
    total_executions: int
    completed_executions: int
    failed_executions: int
    running_executions: int
    estimated_completion: str | None  # ISO format


class FailureAnalysis(TypedDict):
    """Type definition for execution failure analysis."""

    execution_id: str
    failure_category: str
    failure_reason: str
    retry_recommended: bool
    suggested_action: str
    similar_failures: int


class RetryStrategy(TypedDict):
    """Type definition for retry strategy recommendations."""

    execution_id: str
    recommended_delay: int
    max_retries: int
    priority_adjustment: int
    parameter_changes: Dict[str, Any]


class SearchCoverage(TypedDict):
    """Type definition for search coverage analysis."""

    session_id: str
    total_queries: int
    executed_queries: int
    coverage_percentage: float
    missing_engines: List[str]
    estimated_missing_results: int


class EnginePerformance(TypedDict):
    """Type definition for search engine performance comparison."""

    engine_name: str
    total_executions: int
    success_rate: float
    average_response_time: float
    average_results_count: int
    reliability_score: float
