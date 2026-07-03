"""
TypedDict definitions for review_results API responses.
Complete migration from Pydantic schemas - Phase 2.
Maintains exact API compatibility while removing Pydantic dependency.
"""

from typing import Any, Dict, List, Literal, TypedDict

# Review decision literal types
ReviewDecision = Literal["pending", "include", "exclude", "maybe"]
ExclusionReason = Literal[
    "not_relevant",
    "not_grey_lit",
    "duplicate",
    "no_access",
    "wrong_document_type",
    "language",
    "wrong_population",
    "wrong_intervention",
    "methodological_quality",
    "other",
]


# API input types
class ReviewDecisionInput(TypedDict):
    """Type definition for review decision API input."""

    result_id: str
    decision: ReviewDecision
    exclusion_reason: str | None
    notes: str | None


class NotesUpdateInput(TypedDict):
    """Type definition for notes update API input."""

    result_id: str
    notes: str


class BulkReviewDecisionInput(TypedDict):
    """Type definition for bulk review decision API input."""

    result_ids: List[str]
    decision: ReviewDecision
    exclusion_reason: str | None
    notes: str | None


# API response types
class ReviewDecisionResponse(TypedDict):
    """Type definition for review decision API response."""

    success: bool
    decision: str
    result_id: str
    message: str


class BulkReviewDecisionResponse(TypedDict):
    """Type definition for bulk review decision API response."""

    success: bool
    decision: str
    processed_count: int
    created: int
    updated: int
    message: str


class NotesResponse(TypedDict):
    """Type definition for notes API response."""

    success: bool
    notes: str


class NotesUpdateResponse(TypedDict):
    """Type definition for notes update API response."""

    success: bool
    message: str


class SessionStatsResponse(TypedDict):
    """Type definition for session stats API response."""

    success: bool
    progress: Dict[str, Any]


class URLAccessResponse(TypedDict):
    """Type definition for URL access tracking API response."""

    success: bool
    message: str
    created: bool


class IncludeFilteredResponse(TypedDict):
    """Type definition for include filtered result API response."""

    success: bool
    message: str
    result_id: str
    old_status: str


# Error response type
class ErrorResponse(TypedDict):
    """Type definition for API error responses."""

    success: bool
    error: str
    details: List[Dict[str, Any]] | None


# ============================================================================
# Extended API Response Types (Complete Pydantic Migration)
# ============================================================================


class DetailedReviewDecisionResponse(TypedDict):
    """Complete review decision response with full audit trail."""

    id: str
    result_id: str
    reviewer_id: str
    decision: ReviewDecision
    exclusion_reason: str | None
    notes: str
    reviewed_at: str  # ISO datetime string
    updated_at: str  # ISO datetime string


class ReviewProgressResponse(TypedDict):
    """Detailed review progress statistics."""

    session_id: str
    total_results: int
    reviewed_count: int
    pending_count: int
    include_count: int
    exclude_count: int
    maybe_count: int
    completion_percentage: float


class ReviewExportRequest(TypedDict):
    """Review data export request parameters."""

    session_id: str
    format_type: Literal["csv", "xlsx", "json"]
    filter_by_decision: ReviewDecision | None


class ReviewExportResponse(TypedDict):
    """Review data export response."""

    success: bool
    download_url: str
    filename: str
    record_count: int
    generated_at: str


# ============================================================================
# Validation Helper Types
# ============================================================================


class ValidationResult(TypedDict):
    """Validation result with errors and warnings."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]


# ============================================================================
# Validation Functions (Replacing Pydantic Validators)
# ============================================================================


def validate_review_decision_input(data: dict) -> ValidationResult:
    """Validate review decision input data."""
    errors = []
    warnings = []

    # Required fields
    if not data.get("result_id"):
        errors.append("Result ID is required")

    decision = data.get("decision")
    if not decision:
        errors.append("Decision is required")
    elif decision not in ["pending", "include", "exclude", "maybe"]:
        errors.append("Decision must be one of: pending, include, exclude, maybe")

    # Exclusion reason validation
    if decision == "exclude" and not data.get("exclusion_reason"):
        errors.append("Exclusion reason is required when excluding a result")

    # Notes length validation
    notes = data.get("notes", "")
    if notes and len(notes) > 1000:
        errors.append("Notes cannot exceed 1000 characters")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_bulk_review_input(data: dict) -> ValidationResult:
    """Validate bulk review decision input data."""
    errors = []
    warnings = []

    # Result IDs validation
    result_ids = data.get("result_ids", [])
    if not result_ids:
        errors.append("At least one result ID is required")
    elif len(result_ids) > 100:
        errors.append("Maximum 100 results can be processed at once")

    # Decision validation
    decision = data.get("decision")
    if not decision:
        errors.append("Decision is required")
    elif decision not in ["pending", "include", "exclude", "maybe"]:
        errors.append("Decision must be one of: pending, include, exclude, maybe")

    # Exclusion reason validation
    if decision == "exclude" and not data.get("exclusion_reason"):
        errors.append("Exclusion reason is required when excluding results")

    # Notes length validation
    notes = data.get("notes", "")
    if notes and len(notes) > 1000:
        errors.append("Notes cannot exceed 1000 characters")

    # Performance warning
    if len(result_ids) > 50:
        warnings.append("Processing large batches may take longer")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_notes_update_input(data: dict) -> ValidationResult:
    """Validate notes update input data."""
    errors = []
    warnings = []

    # Required fields
    if not data.get("result_id"):
        errors.append("Result ID is required")

    # Notes validation
    notes = data.get("notes", "")
    if not notes:
        errors.append("Notes content is required")
    elif len(notes) > 1000:
        errors.append("Notes cannot exceed 1000 characters")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_export_request(data: dict) -> ValidationResult:
    """Validate export request data."""
    errors = []
    warnings = []

    # Required fields
    if not data.get("session_id"):
        errors.append("Session ID is required")

    # Format validation
    format_type = data.get("format_type", "csv")
    if format_type not in ["csv", "xlsx", "json"]:
        errors.append("Format must be one of: csv, xlsx, json")

    # Filter validation
    filter_decision = data.get("filter_by_decision")
    if filter_decision and filter_decision not in [
        "pending",
        "include",
        "exclude",
        "maybe",
    ]:
        errors.append(
            "Filter decision must be one of: pending, include, exclude, maybe"
        )

    return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)
