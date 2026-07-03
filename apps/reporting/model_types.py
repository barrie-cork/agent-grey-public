"""
TypedDict definitions for Reporting models.
Created during Phase 2 of TypedDict migration - Model Alignment.
Part of VSA-compliant model type system.
"""

from typing import Dict, List, Literal, Optional, TypedDict


# JSONField Type
class ReportParametersType(TypedDict, total=False):
    """Type for ExportReport.parameters JSONField.

    Using total=False as parameters vary by report type.
    """

    include_duplicates: bool
    include_excluded: bool
    include_maybe: bool
    include_metadata: bool
    include_reviewer_notes: bool
    include_tags: bool
    date_range_start: Optional[str]  # ISO format
    date_range_end: Optional[str]  # ISO format
    reviewer_filter: Optional[List[str]]  # Reviewer IDs
    tag_filter: Optional[List[str]]  # Tag IDs
    confidence_threshold: Optional[float]
    sort_by: Optional[str]
    sort_order: Optional[Literal["asc", "desc"]]
    custom_fields: Optional[List[str]]


# Model Data Types
class ExportReportData(TypedDict):
    """Serialization of ExportReport model."""

    id: str  # UUID as string
    session_id: str  # UUID as string
    session_title: str  # Denormalized
    generated_by_id: Optional[str]  # UUID as string
    generated_by_username: Optional[str]  # Denormalized
    report_type: Literal[
        "prisma_flow",
        "full_report",
        "included_results",
        "excluded_results",
        "search_strategy",
        "data_export",
    ]
    export_format: Literal["pdf", "csv", "json", "xlsx"]
    file_name: str
    file_path: str
    file_url: str  # Generated download URL
    file_size_bytes: int
    file_size_display: str  # Human-readable (e.g., "2.3 MB")
    title: str
    description: str
    parameters: ReportParametersType
    total_results: int
    included_results: int
    excluded_results: int
    maybe_results: int
    status: Literal["pending", "generating", "completed", "failed"]
    progress_percentage: int
    error_message: str
    created_at: str  # ISO format
    updated_at: str  # ISO format
    expires_at: Optional[str]  # ISO format for temporary files


class ReportSummary(TypedDict):
    """Lightweight report representation for lists."""

    id: str  # UUID as string
    title: str
    report_type: str
    export_format: str
    file_size_display: str
    status: str
    created_at: str  # ISO format
    download_url: str


class ReportStats(TypedDict):
    """Statistics for report generation."""

    total_reports: int
    reports_by_type: Dict[str, int]
    reports_by_format: Dict[str, int]
    total_size_bytes: int
    average_size_bytes: float
    average_generation_time: float  # seconds
    failed_reports: int
    success_rate: float


class ReportGenerationRequest(TypedDict):
    """Request structure for report generation."""

    session_id: str  # UUID as string
    report_type: str
    export_format: str
    title: Optional[str]
    description: Optional[str]
    parameters: ReportParametersType
    user_id: str  # UUID as string


class PRISMAFlowData(TypedDict):
    """Data structure for PRISMA flow diagram."""

    identification_count: int
    screening_count: int
    eligibility_count: int
    included_count: int
    excluded_reasons: Dict[str, int]  # reason: count
    duplicate_count: int
    database_sources: List[Dict[str, int]]  # [{name, count}]
    other_sources: List[Dict[str, int]]  # [{name, count}]
