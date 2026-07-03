"""
TypedDict definitions for Results Manager model JSONFields.
Created during Phase 2 of TypedDict migration - Model Alignment.
"""

from typing import List, Optional, TypedDict


class ProcessingConfigType(TypedDict):
    """Type definition for ProcessingSession.processing_config JSONField.

    Configuration parameters for result processing.
    """

    batch_size: int  # Number of results per batch
    enable_deduplication: bool  # Whether to deduplicate
    similarity_threshold: float  # Threshold for duplicate detection (0.0-1.0)
    extract_metadata: bool  # Whether to extract additional metadata
    language_detection: bool  # Whether to detect language
    quality_scoring: bool  # Whether to calculate quality scores
    max_retries: int  # Maximum retry attempts for failed items


class ErrorDetailsType(TypedDict):
    """Type definition for ProcessingSession.error_details JSONField.

    Detailed error tracking information.
    """

    error_type: str  # Type of error (e.g., "ValidationError", "APIError")
    error_message: str  # Human-readable error message
    error_code: Optional[str]  # Error code if applicable
    stack_trace: Optional[str]  # Stack trace for debugging
    failed_items: List[str]  # IDs of failed items
    timestamp: str  # ISO format timestamp
    retry_available: bool  # Whether retry is possible


class AuthorListType(TypedDict):
    """Type definition for ProcessedResult.authors JSONField.

    Structured author information.
    """

    authors: List[str]  # Simple list of author names
    # Could be extended to:
    # authors: List[AuthorType] where AuthorType has name, affiliation, etc.
