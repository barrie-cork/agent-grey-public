"""
Constants for the results_manager app.

Simplified constants for essential processing functionality.
"""


class DocumentType:
    """Document type constants for processed results."""

    PDF = "pdf"
    WORD = "word"
    WEBPAGE = "webpage"


class DeduplicationConstants:
    """
    Constants for conservative URL-only deduplication service.

    This system uses URL normalisation and exact URL matching across
    queries to identify duplicates. No title or content similarity
    matching is performed to ensure conservative results.
    """

    EXACT_URL_CONFIDENCE: float = 1.0

    # URL normalisation settings
    TRACKING_PARAMS = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "ref",
        "source",
        "medium",
        "campaign",
    }
    WWW_PREFIX: str = "www."
    DEFAULT_PATH: str = "/"


class TaskConstants:
    """Constants for task orchestration."""

    # Task status values
    STATUS_SKIPPED = "skipped"
    STATUS_FAILED = "failed"
    STATUS_STARTED = "started"
    STATUS_COMPLETED = "completed"
    STATUS_ALREADY_PROCESSING = "already_processing"
    STATUS_ALREADY_COMPLETED = "already_completed"
    STATUS_NO_RESULTS = "no_results"

    # Skip reasons
    REASON_DUPLICATE_TASK = "duplicate_task"
    REASON_RACE_CONDITION = "race_condition"

    # Cache key patterns
    CACHE_KEY_TASK_RUNNING = "task_running_{session_id}"
    CACHE_KEY_SESSION_TASK_MAP = "session_task_map_{session_id}"
    CACHE_KEY_PROCESSING_SESSION = "processing_session_{session_id}"

    # Timeouts (in seconds)
    TASK_REGISTRATION_TIMEOUT = 600  # 10 minutes
    TASK_MAPPING_TIMEOUT = 3600  # 1 hour
    REDIS_LOCK_TIMEOUT = 300  # 5 minutes

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 60  # seconds

    # Processing configuration
    BATCH_SIZE = 50
    MAX_TASK_HISTORY = 10

    # Metadata keys for processing session
    METADATA_TASK_ID = "unique_task_id"
    METADATA_STARTED_BY = "started_by"


class ErrorCategory:
    """Processing error category constants."""

    DUPLICATE = "duplicate"
    FILE_TYPE_MISMATCH = "file_type_mismatch"


class ProcessingConstants:
    """Constants for processing services."""

    # Batch processing
    DEFAULT_BATCH_SIZE: int = 50

    # Percentage calculation
    PERCENTAGE_MULTIPLIER: int = 100

    # Decimal places for rounding
    DECIMAL_PLACES: dict = {
        "percentage": 1,
        "score": 2,
    }

    # Export limits
    SAMPLE_RESULTS_LIMIT: int = 5

    # Statistics defaults
    EMPTY_STATS_DEFAULTS: dict = {
        "total_results": 0,
        "processed_results": 0,
        "duplicates_removed": 0,
        "unique_results": 0,
        "document_types": {},
        "publication_years": {},
        "pdf_count": 0,
    }
