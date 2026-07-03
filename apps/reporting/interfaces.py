"""
Interfaces for cross-app communication in the reporting slice.

This module defines abstract interfaces to prevent direct imports
from other apps, maintaining vertical slice boundaries.
"""

from abc import ABC, abstractmethod


class IReviewManager(ABC):
    """Interface for review manager operations."""

    @abstractmethod
    def get_session(self, session_id):
        """Get session details.

        Args:
            session_id: UUID of the SearchSession to retrieve.

        Returns:
            Dict containing session data with keys: id, title, status,
            owner_id, created_at, updated_at, description.
            Returns empty dict if session not found.
        """

    @abstractmethod
    def get_session_activities(self, session_id):
        """Get session activity log.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            list: Activity dictionaries with keys: id, activity_type,
            description, created_at, user_id. Ordered by most recent first.
        """

    @abstractmethod
    def get_search_queries(self, session_id):
        """Get search queries for a session.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            list: Query dictionaries with search query details.
            May return empty list if queries are managed elsewhere.
        """


class IResultsManager(ABC):
    """Interface for results manager operations."""

    @abstractmethod
    def get_processed_results_for_session(self, session_id):
        """Get processed results for a session.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            list: Processed result dictionaries with keys: id, title, url,
            domain, document_type, is_pdf, processed_at.
        """

    @abstractmethod
    def get_duplicate_statistics(self, session_id):
        """Get duplicate statistics for a session.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            dict: Statistics with integer values for keys: total_duplicates, unique_results,
            duplicates_removed.
        """

    @abstractmethod
    def get_quality_distribution(self, session_id):
        """Get quality score distribution.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            dict: Quality distribution data with quality score ranges and counts,
            plus average_quality_score as float value.
        """

    @abstractmethod
    def get_results_by_domain(self, session_id):
        """Get results grouped by domain.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            dict: Mapping of domain names (str) to result counts (int),
            ordered by count descending.
        """


class IReviewResults(ABC):
    """Interface for review results operations."""

    @abstractmethod
    def get_review_decisions_for_session(self, session_id):
        """Get all review decisions for a session.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            list: Review decision dictionaries with keys: id, result_id,
            decision, reviewer_id, reviewed_at, notes.
        """

    @abstractmethod
    def get_inclusion_statistics(self, session_id):
        """Get inclusion/exclusion statistics.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            dict: Statistics with integer values for keys: total_reviewed, included, excluded,
            pending_review, and inclusion_rate as percentage float.
        """

    @abstractmethod
    def get_exclusion_reasons(self, session_id):
        """Get exclusion reasons with counts.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            list: Dictionaries with keys: reason (str), count (int), percentage (float).
            Ordered by count descending.
        """

    @abstractmethod
    def get_review_progress(self, session_id):
        """Get review progress statistics.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            dict: Progress data with keys: total_results (int), reviewed_count (int),
            remaining_count (int), progress_percentage (float), estimated_completion_time.
        """


class ISearchStrategy(ABC):
    """Interface for search strategy operations."""

    @abstractmethod
    def get_search_queries(self, session_id):
        """Get search queries with details.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            list: Query dictionaries with keys: id, query_text,
            query_type, database, created_at, results_count.
        """

    @abstractmethod
    def get_query_effectiveness(self, session_id):
        """Calculate query effectiveness metrics.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            dict: Effectiveness metrics with keys: total_queries (int), total_results (int),
            average_results_per_query (float), most_effective_query (str),
            least_effective_query (str), duplicate_rate (float).
        """

    @abstractmethod
    def get_search_terms(self, session_id):
        """Get all search terms used.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            list: Unique search terms (str) extracted from all queries,
            ordered alphabetically.
        """

    @abstractmethod
    def get_database_coverage(self, session_id):
        """Get database/source coverage statistics.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            dict: Coverage data with keys: databases_searched (list), results_per_database (dict),
            coverage_percentage (float), missing_databases (list).
        """


class ISerpExecution(ABC):
    """Interface for SERP execution operations."""

    @abstractmethod
    def get_raw_results_count(self, session_id):
        """Get count of raw search results.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            int: Total count of raw search results for the session.
        """

    @abstractmethod
    def get_raw_results_for_session(self, session_id):
        """Get raw search results for a session.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            list: Raw result dictionaries with keys: id, title, url,
            snippet, position, source, retrieved_at.
        """

    @abstractmethod
    def get_execution_statistics(self, session_id):
        """Get search execution statistics.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            dict: Execution statistics with keys: total_executions (int), successful_executions (int),
            failed_executions (int), total_api_calls (int), average_results_per_execution (float),
            total_execution_time (float).
        """

    @abstractmethod
    def get_results_by_source(self, session_id):
        """Get results grouped by source/API.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            dict: Mapping of source names (str) like 'serper', 'google_scholar'
            to result counts (int), ordered by count descending.
        """

    @abstractmethod
    def get_executions_for_session(self, session_id):
        """Get all search executions for a session.

        Args:
            session_id: UUID identifier for the SearchSession.

        Returns:
            list: Execution dictionaries with keys: id, query_id,
            status, started_at, completed_at, results_count,
            error_message (if failed).
        """
