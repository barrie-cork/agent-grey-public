"""
Constants for the reporting app.

This module contains all constants used across reporting services to avoid magic
numbers and strings in the codebase.
"""


class ExportConstants:
    """Constants for export service."""

    # Content types mapping
    CONTENT_TYPES: dict = {
        "csv": "text/csv",
        "json": "application/json",
        "pdf": "application/pdf",
        "html": "text/html",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }

    # Default content type for unknown formats
    DEFAULT_CONTENT_TYPE: str = "application/octet-stream"

    # File size estimation multipliers
    SIZE_MULTIPLIERS: dict = {
        "csv": 0.7,
        "pdf": 2.0,
        "html": 1.2,
        "xlsx": 1.5,
    }

    # Default size multiplier
    DEFAULT_SIZE_MULTIPLIER: float = 1.0

    # CSV export field names
    STUDY_CSV_FIELDS: list = [
        "id",
        "title",
        "publication_year",
        "document_type",
        "url",
        "has_full_text",
    ]

    QUERY_CSV_FIELDS: list = [
        "id",
        "query_text",
        "population",
        "interest",
        "context",
        "search_engines",
        "total_results",
        "success_rate",
    ]

    # Report expiration time in days
    REPORT_EXPIRATION_DAYS: int = 90

    # Export type names
    EXPORT_TYPE_NAMES: dict = {
        "prisma_flow": "PRISMA Flow Diagram",
        "result_summary": "Search Results Summary Table",
        "search_strategy": "Search Strategy Report",
        "bibliography": "Bibliography",
    }

    # Available formats per export type
    EXPORT_FORMATS: dict = {
        "prisma_flow": ["pdf", "html"],
        "result_summary": ["csv", "html"],
        "search_strategy": ["pdf", "html"],
        "bibliography": ["csv", "html"],
    }


class PerformanceConstants:
    """Constants for performance analytics service."""

    # Time period labels
    TIME_PERIODS: dict = {
        "last_hour": 1,
        "last_24_hours": 24,
        "last_week": 168,
        "last_month": 720,
    }

    # Performance thresholds
    RESPONSE_TIME_THRESHOLDS: dict = {
        "excellent": 1.0,  # < 1 second
        "good": 3.0,  # < 3 seconds
        "acceptable": 5.0,  # < 5 seconds
        "poor": 10.0,  # < 10 seconds
    }

    # Success rate thresholds
    SUCCESS_RATE_THRESHOLDS: dict = {
        "excellent": 0.95,  # >= 95%
        "good": 0.90,  # >= 90%
        "acceptable": 0.80,  # >= 80%
        "poor": 0.70,  # >= 70%
    }

    # Cache TTL (in seconds)
    CACHE_TTL: dict = {
        "real_time": 60,  # 1 minute
        "short_term": 300,  # 5 minutes
        "medium_term": 3600,  # 1 hour
        "long_term": 86400,  # 24 hours
    }

    # Percentage calculation
    PERCENTAGE_MULTIPLIER: int = 100

    # Decimal precision
    DECIMAL_PLACES: dict = {"percentage": 1, "cost": 4, "time": 1, "ratio": 2}

    # Default minimum divisor to avoid division by zero
    MIN_DIVISOR: int = 1

    # Tag names for metrics
    INCLUDE_TAG: str = "Include"
    EXCLUDE_TAG: str = "Exclude"

    # Execution status
    COMPLETED_STATUS: str = "completed"

    # Recommendation thresholds
    SUCCESS_RATE_THRESHOLD: float = 90.0
    PRECISION_THRESHOLD: float = 50.0
    COST_PER_STUDY_THRESHOLD: float = 1.0
    ENGINE_PERFORMANCE_DIFF_THRESHOLD: float = 20.0

    # Priority levels
    PRIORITY_HIGH: str = "high"
    PRIORITY_MEDIUM: str = "medium"
    PRIORITY_LOW: str = "low"

    # Recommendation categories
    RECOMMENDATION_CATEGORIES: list = [
        "execution_reliability",
        "search_precision",
        "cost_optimization",
        "engine_optimization",
    ]

    # Max priority actions to show
    MAX_PRIORITY_ACTIONS: int = 3


class PRISMAConstants:
    """Constants for PRISMA reporting service."""

    # PRISMA flow stages
    FLOW_STAGES: list = ["identification", "screening", "eligibility", "included"]

    # Record sources
    RECORD_SOURCES: list = [
        "database_searches",
        "other_sources",
        "duplicates_removed",
        "records_screened",
        "records_excluded",
        "full_text_assessed",
        "full_text_excluded",
        "results_included",
    ]

    # PRISMA checklist items
    CHECKLIST_SECTIONS: dict = {
        "title": ["title", "summary"],
        "introduction": ["rationale", "objectives"],
        "methods": [
            "protocol",
            "eligibility",
            "sources",
            "search",
            "selection",
            "data_collection",
        ],
        "results": [
            "selection",
            "characteristics",
            "risk_of_bias",
            "results_individual",
            "synthesis",
        ],
        "discussion": ["summary", "limitations", "conclusions"],
    }

    # Standardized exclusion reasons -- derived from canonical SimpleReviewDecision choices
    STANDARD_EXCLUSION_REASONS: dict = {}  # Populated after class definition

    # Tag names
    EXCLUDE_TAG: str = "Exclude"

    # Checklist completion
    MIN_DESCRIPTION_LENGTH: int = 100
    PERCENTAGE_MULTIPLIER: int = 100

    # Batch processing
    BATCH_SIZE: int = 50

    # Status display colors (Bootstrap classes)
    STATUS_COLORS: dict = {
        "pending": "warning",
        "generating": "info",
        "completed": "success",
        "failed": "danger",
        "expired": "secondary",
    }

    # Chart colors for PRISMA visualizations
    CHART_COLORS: dict = {
        "identification": "rgba(13, 110, 253, 0.5)",  # Bootstrap primary
        "screening": "rgba(25, 135, 84, 0.5)",  # Bootstrap success
        "eligibility": "rgba(255, 193, 7, 0.5)",  # Bootstrap warning
        "included": "rgba(220, 53, 69, 0.5)",  # Bootstrap danger
    }

    # Template paths for reports
    TEMPLATES: dict = {
        "full_report": "reporting/exports/full_report.html",
        "prisma_flow": "reporting/exports/prisma_flow.html",
        "results_summary": "reporting/exports/results_summary.html",
        "bibliography": "reporting/exports/bibliography.html",
        "search_strategy": "reporting/exports/search_strategy.html",
    }

    # PRISMA 2020 specific fields
    PRISMA_2020_FIELDS: dict = {
        "identification": [
            "databases",
            "registers",
            "websites",
            "organizations",
            "citation_searching",
        ],
        "screening": ["records_screened", "records_excluded", "reasons_for_exclusion"],
        "included": ["new_studies", "updated_studies", "total_studies"],
    }

    # Report expiration (moved from ExportConstants for consolidation)
    REPORT_EXPIRATION_DAYS: int = 90


class ResultAnalysisConstants:
    """Constants for search result analysis service."""

    # Basic document types we recognize
    DOCUMENT_TYPES: list = ["pdf", "website", "report", "document", "unknown"]

    # Time periods for recency analysis (in years)
    RECENCY_PERIODS: dict = {"recent": 5, "fairly_recent": 10}

    # Domain to country mapping for geographical analysis
    DOMAIN_TO_COUNTRY: dict = {
        ".gov": "United States",
        ".edu": "United States",
        ".uk": "United Kingdom",
        ".ca": "Canada",
        ".au": "Australia",
        ".de": "Germany",
        ".fr": "France",
        ".nl": "Netherlands",
        "europa.eu": "European ",
        "who.int": "International",
    }


class SearchStrategyConstants:
    """Constants for search strategy reporting service."""

    # PIC framework components
    PIC_COMPONENTS: list = ["population", "interest", "context"]

    # Search engine names
    SEARCH_ENGINES: dict = {
        "google": "Google Search",
        "google_scholar": "Google Scholar",
        "bing": "Bing Search",
        "base": "BASE",
        "core": "CORE",
        "oaister": "OAIster",
    }

    # Query effectiveness metrics
    EFFECTIVENESS_METRICS: list = [
        "precision",
        "recall",
        "f1_score",
        "coverage_score",
    ]

    # Report sections
    REPORT_SECTIONS: list = [
        "executive_summary",
        "search_objectives",
        "search_process",
        "search_strings",
        "sources_searched",
        "inclusion_criteria",
        "exclusion_criteria",
        "results_summary",
        "recommendations",
    ]

    # Analysis limits
    TOP_ENGINES_LIMIT: int = 3
