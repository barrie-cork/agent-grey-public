"""
Simple constants for basic review functionality.
"""


class ReviewConstants:
    """Simple constants for basic review functionality."""

    # Export formats
    EXPORT_FORMATS = ["csv", "json"]
    DEFAULT_EXPORT_FORMAT = "csv"

    # Pagination
    RESULTS_PER_PAGE = 25
    MAX_RESULTS_PER_PAGE = 100

    # Export fields
    EXPORT_FIELDS = [
        "title",
        "url",
        "publication_year",
        "document_type",
        "decision",
        "exclusion_reason",
        "notes",
        "reviewer",
        "reviewed_at",
    ]
