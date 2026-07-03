"""
TypedDict definitions for reporting API responses.
Created during Pydantic to TypedDict migration - Phase 1.
"""

from typing import Any, Dict, List, Literal, TypedDict

# Report status and format literal types
ReportStatus = Literal["pending", "generating", "completed", "failed"]
ReportFormat = Literal["pdf", "html", "csv"]
ReportType = Literal[
    "prisma_flow",
    "search_strategy",
    "study_characteristics",
    "performance_metrics",
    "custom",
]


# Form input types for validation
class ReportGenerationInput(TypedDict):
    """Type definition for report generation form input validation."""

    format: ReportFormat
    include_prisma_flow: bool
    include_prisma_checklist: bool
    include_metadata: bool


# API response types
class ErrorResponse(TypedDict):
    """Type definition for API error responses."""

    error: str


class ReportGenerationResponse(TypedDict):
    """Type definition for successful report generation API response."""

    report_id: str
    status: str
    title: str
    export_format: str
    created_at: str  # ISO format
    generation_mode: str


class PRISMAFlowDataResponse(TypedDict):
    """Type definition for PRISMA flow diagram data."""

    identification: Dict[str, Any]
    screening: Dict[str, Any]
    eligibility: Dict[str, Any]
    included: Dict[str, Any]
    metadata: Dict[str, Any]


# Alias for backward compatibility
PRISMAFlowData = PRISMAFlowDataResponse


class ReportStatusResponse(TypedDict):
    """Type definition for report status API response."""

    id: str
    status: str
    progress_percentage: int
    title: str
    export_format: str
    created_at: str  # ISO format
    completed_at: str | None  # ISO format
    download_url: str | None
    error_message: str | None


class ReportProgressItem(TypedDict):
    """Type definition for individual report progress item."""

    id: str
    title: str
    report_type: str
    export_format: str
    status: str
    progress_percentage: int
    created_at: str  # ISO format
    download_url: str | None


class ReportProgressResponse(TypedDict):
    """Type definition for report progress API response."""

    reports: List[ReportProgressItem]


# Enhanced PRISMA types
class ExclusionReason(TypedDict):
    """Type definition for exclusion reasons."""

    reason: str
    count: int
    percentage: float
    examples: List[str]


class ReviewPeriod(TypedDict):
    """Type definition for review period information."""

    start_date: str  # ISO date format
    end_date: str  # ISO date format
    duration_days: int
    active_review_days: int


class SearchStrategyReport(TypedDict):
    """Type definition for search strategy reports."""

    session_id: str
    search_approach: str
    databases_searched: List[str]
    search_terms: List[str]
    search_queries: List[str]
    date_ranges: Dict[str, Any]
    language_restrictions: List[str]
    inclusion_criteria: List[str]
    exclusion_criteria: List[str]
    search_validation: Dict[str, Any]


class StudyCharacteristics(TypedDict):
    """Type definition for study characteristics table."""

    session_id: str
    total_studies: int
    study_types: Dict[str, Any]
    publication_years: Dict[str, Any]
    geographical_distribution: Dict[str, Any]
    language_distribution: Dict[str, Any]
    methodology_distribution: Dict[str, Any]
    sample_size_distribution: Dict[str, Any]


class PerformanceMetrics(TypedDict):
    """Type definition for search performance metrics."""

    session_id: str
    search_efficiency: float
    precision_estimate: float
    recall_estimate: float
    time_to_completion: int
    cost_per_relevant_result: float
    search_coverage: float
    duplicate_detection_rate: float


class ReportRequest(TypedDict):
    """Type definition for report generation requests."""

    session_id: str
    report_type: ReportType
    format: ReportFormat
    include_methodology: bool
    include_appendices: bool
    custom_sections: List[str]
    template_id: str | None


class ReportResponse(TypedDict):
    """Type definition for report generation responses."""

    report_id: str
    session_id: str
    report_type: ReportType
    format: ReportFormat
    file_path: str
    file_size_bytes: int
    generated_at: str  # ISO format
    expires_at: str  # ISO format
    download_url: str


class PRISMAChecklist(TypedDict):
    """Type definition for PRISMA checklist compliance."""

    session_id: str
    checklist_items: List[Dict[str, Any]]
    compliance_score: float
    missing_items: List[str]
    recommendations: List[str]
    is_compliant: bool


class ReportTemplate(TypedDict):
    """Type definition for report templates."""

    id: str
    name: str
    description: str
    report_type: ReportType
    template_sections: List[Dict[str, Any]]
    default_format: ReportFormat
    is_system_template: bool
    usage_count: int


class ExportConfiguration(TypedDict):
    """Type definition for data export configuration."""

    session_id: str
    data_types: List[str]
    format: ReportFormat
    include_raw_data: bool
    include_metadata: bool
    date_range_filter: Dict[str, Any] | None
    tag_filter: List[str] | None
    quality_filter: Dict[str, Any] | None


class ReportMetadata(TypedDict):
    """Type definition for report metadata."""

    report_id: str
    title: str
    author: str
    organization: str
    version: str
    generated_date: str  # ISO format
    review_period: ReviewPeriod
    methodology_summary: str
    key_findings: List[str]
    limitations: List[str]


class ReportSchedule(TypedDict):
    """Type definition for scheduled report generation."""

    session_id: str
    report_type: ReportType
    schedule_frequency: str  # 'daily', 'weekly', 'monthly'
    recipients: List[str]
    next_generation: str  # ISO format
    is_active: bool


class ReportGenerationResult(TypedDict):
    """Type definition for report generation task result."""

    report_id: str
    file_name: str
    file_size: int
    status: str


class SearchSourceBreakdown(TypedDict):
    """Per-provider breakdown of search results for audit reporting."""

    provider_key: str
    display_name: str
    queries_executed: int
    total_results: int
    unique_results: int
    included_results: int
    inclusion_rate: float
