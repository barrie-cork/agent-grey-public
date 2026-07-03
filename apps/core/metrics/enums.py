"""
Enums for Prometheus metric label validation.

Prevents cardinality explosion by restricting label values to known constants.
This ensures type safety and prevents typos that could create unbounded metric series.
"""

from enum import StrEnum


class SearchStatus(StrEnum):
    """
    Valid statuses for search execution metrics.

    Attributes:
        SUCCESS: Search completed successfully with results.
        ERROR: Search failed due to API or system error.
        EMPTY: Search completed but returned zero results.
    """

    SUCCESS = "success"
    ERROR = "error"
    EMPTY = "empty"


class ErrorType(StrEnum):
    """
    Valid error types for search API errors.

    Attributes:
        TIMEOUT: Request timed out.
        RATE_LIMIT: API rate limit exceeded.
        AUTHENTICATION: Authentication failed.
        NETWORK: Network or connection error.
        UNKNOWN: Error type could not be determined.
    """

    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    UNKNOWN = "unknown"


class ReviewDecision(StrEnum):
    """
    Valid review decision types.

    Attributes:
        INCLUDE: Result included in review.
        EXCLUDE: Result excluded from review.
        UNDECIDED: Decision not yet made.
    """

    INCLUDE = "include"
    EXCLUDE = "exclude"
    UNDECIDED = "undecided"


class ProcessingStatus(StrEnum):
    """
    Valid result processing statuses.

    Attributes:
        SUCCESS: Result processed successfully.
        DUPLICATE: Result identified as duplicate.
        ERROR: Processing failed with error.
    """

    SUCCESS = "success"
    DUPLICATE = "duplicate"
    ERROR = "error"
