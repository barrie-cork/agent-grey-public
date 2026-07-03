"""
TypedDict definitions for search_strategy API responses and internal processing.
Created during Pydantic to TypedDict migration - Phase 2.
Replaces all Pydantic schemas with TypedDict definitions.
"""

from typing import Any, Dict, List, TypedDict

# ============================================================================
# PIC Framework Types
# ============================================================================


class PICFrameworkSchema(TypedDict):
    """Population, Interest, Context framework validation."""

    population: str
    interest: str
    context: str


class CreateQuerySchema(TypedDict):
    """Schema for creating a search query."""

    session_id: str  # UUID as string
    population: str
    interest: str
    context: str
    include_keywords: List[str]
    exclude_keywords: List[str]
    date_from: str | None  # ISO format date
    date_to: str | None  # ISO format date
    languages: List[str]
    document_types: List[str]
    search_engines: List[str]
    max_results: int  # Stored in SearchStrategy.search_config JSONField
    is_primary: bool


class QueryResponseSchema(TypedDict):
    """Schema for query API responses."""

    id: str
    session_id: str
    population: str
    interest: str
    context: str
    generated_query: str
    include_keywords: List[str]
    exclude_keywords: List[str]
    date_from: str | None  # ISO format date
    date_to: str | None  # ISO format date
    is_primary: bool
    created_at: str  # ISO format timestamp
    updated_at: str  # ISO format timestamp


class SearchQueryUpdate(TypedDict):
    """Schema for updating a search query."""

    title: str | None
    population: str | None
    interest: str | None
    context: str | None
    query_string: str | None
    search_engines: List[str] | None
    date_range_start: str | None  # ISO format date
    date_range_end: str | None  # ISO format date
    language_codes: List[str] | None
    excluded_terms: List[str] | None
    max_results: int | None  # Stored in SearchStrategy.search_config JSONField
    notes: str | None
    is_active: bool | None


# ============================================================================
# Validation and Analysis Types
# ============================================================================


class PICValidation(TypedDict):
    """Schema for PIC framework validation results."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]
    suggestions: List[str]


class QueryVariation(TypedDict):
    """Schema for query variations/suggestions."""

    variation_type: str
    title: str
    query_string: str
    rationale: str
    estimated_additional_results: int


class QueryOptimization(TypedDict):
    """Schema for query optimization results."""

    optimized_query: str
    optimization_score: int
    changes_made: List[str]
    potential_impact: str


# ============================================================================
# Template and Statistics Types
# ============================================================================


class SearchStrategyTemplate(TypedDict):
    """Schema for search strategy templates."""

    id: str
    name: str
    description: str
    population_template: str
    interest_template: str
    context_template: str
    query_template: str
    use_count: int
    success_rate: float


class SessionQueryStatistics(TypedDict):
    """Schema for session query statistics."""

    total_queries: int
    active_queries: int
    total_estimated_results: int
    queries_by_engine: Dict[str, int]
    pic_completeness: Dict[str, float]


# ============================================================================
# Query Generation Request Type
# ============================================================================


class QueryGenerationRequest(TypedDict):
    """Schema for validating search strategy update requests."""

    population_terms: List[str]
    interest_terms: List[str]
    context_terms: List[str]
    search_config: Dict[str, Any]


class SearchConfig(TypedDict):
    """Detailed search configuration structure."""

    domains: List[str] | None
    include_general_search: bool
    file_types: List[str]
    search_type: str
    max_results: int  # Stored in SearchStrategy.search_config JSONField
    query_splitting: bool


# ============================================================================
# API Response Types
# ============================================================================


class QueryGenerationResponse(TypedDict):
    """Response for query generation endpoint."""

    success: bool
    query_count: int
    queries: List[QueryResponseSchema]
    validation: PICValidation | None
    suggestions: List[QueryVariation] | None


class SearchStrategyResponse(TypedDict):
    """Response for search strategy endpoints."""

    session_id: str
    strategy: PICFrameworkSchema
    queries: List[QueryResponseSchema]
    statistics: SessionQueryStatistics
    is_complete: bool
    can_execute: bool


class QueryAnalysisResponse(TypedDict):
    """Response for query analysis endpoints."""

    query_id: str
    optimization: QueryOptimization | None
    variations: List[QueryVariation]
    estimated_results: int


# ============================================================================
# Error Response Types
# ============================================================================


class ValidationError(TypedDict):
    """Validation error details."""

    field: str
    message: str
    code: str


class QueryErrorResponse(TypedDict):
    """Error response for query-related endpoints."""

    error: str
    validation_errors: List[ValidationError] | None
    suggestions: List[str] | None


# ============================================================================
# Success Response Types
# ============================================================================


class QueryActionResponse(TypedDict):
    """Response for query action endpoints."""

    success: bool
    action: str
    query_id: str
    message: str
    data: Dict[str, Any] | None


# ============================================================================
# Additional Internal Types
# ============================================================================


class QueryParsedTerms(TypedDict):
    """Parsed query terms structure."""

    population_terms: List[str]
    interest_terms: List[str]
    context_terms: List[str]
    boolean_operators: List[str]
    proximity_operators: List[str]


class QueryMetrics(TypedDict):
    """Query performance metrics."""

    execution_time_ms: int
    results_returned: int
    api_calls_made: int
    rate_limit_remaining: int
    estimated_cost: float
