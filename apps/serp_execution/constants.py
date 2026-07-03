"""
Constants for SERP execution status messages.

This module centralizes all progress status messages used during search execution
and result processing phases.
"""


class ExecutionStatusMessages:
    """
    Constants for SERP execution status messages.

    This class centralises all user-facing progress messages used during the
    search execution workflow. Messages are organised by phase and provide
    consistent feedback to users during the automated transitions between
    states: ready_to_execute → executing → processing_results → ready_for_review.

    The messages follow UK English spelling conventions and are displayed
    in real-time via Server-Sent Events (SSE) to provide granular progress
    updates during potentially long-running operations.
    """

    # ready_to_execute phase messages (displayed in order)
    VALIDATION_COMPLETE = "Validation complete"
    PREPARING_ENVIRONMENT = "Preparing execution environment"
    INITIALIZING_QUERIES = "Initialising search queries"
    STARTING_EXECUTION = "Starting search execution"

    # executing phase messages
    EXECUTING_QUERY = "Executing {domain} ({terms}) type:{file_type}"
    QUERY_COMPLETE = "Completed query {current}/{total}"

    # processing_results phase messages
    PROCESSING_SEARCH_RESULTS = "Processing search results"
    CONDUCTING_DEDUPLICATION = "Conducting cross-query deduplication"
    DENORMALIZING_URLS = "Normalising URLs"
    FINALIZING_RESULTS = "Finalising results"
    READY_FOR_REVIEW = "Ready for review"

    @classmethod
    def get_ready_messages(cls):
        """Get messages for ready_to_execute phase in order."""
        return [
            cls.VALIDATION_COMPLETE,
            cls.PREPARING_ENVIRONMENT,
            cls.INITIALIZING_QUERIES,
            cls.STARTING_EXECUTION,
        ]

    @classmethod
    def get_processing_messages(cls):
        """Get messages for processing phase in order."""
        return [
            cls.PROCESSING_SEARCH_RESULTS,
            cls.DENORMALIZING_URLS,
            cls.CONDUCTING_DEDUPLICATION,
            cls.FINALIZING_RESULTS,
            cls.READY_FOR_REVIEW,
        ]
