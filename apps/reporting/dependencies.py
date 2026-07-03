"""
Dependency adapters for the reporting slice.

This module provides concrete implementations of the interfaces
that adapt external app APIs to our internal interfaces.
"""

from django.db.models import Avg, Count, Q, Sum

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_results.models import SimpleReviewDecision
from apps.search_strategy.models import SearchQuery

from .interfaces import (
    IResultsManager,
    IReviewManager,
    IReviewResults,
    ISearchStrategy,
    ISerpExecution,
)


class ReviewManagerAdapter(IReviewManager):
    """Adapter for review manager operations."""

    def get_session(self, session_id):
        """Get session details.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            dict: Session data formatted for template display with keys for
                id, title, status, owner_id, created_at, updated_at, and description.
                Returns empty dict if session not found (backward compatibility).

        Raises:
            SearchSession.DoesNotExist: If session with given ID doesn't exist.

        Note:
            For backward compatibility, this method returns an empty dict
            when session is not found. Callers should check for empty dict
            to handle missing sessions gracefully.
        """
        try:
            session = SearchSession.objects.get(id=session_id)
            return {
                "id": str(session.id),
                "title": session.title,
                "status": session.status,
                "owner_id": str(session.owner.id),
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "description": session.description,
            }
        except SearchSession.DoesNotExist:
            # Return empty dict for backward compatibility
            # Services using this adapter already check for empty dict
            return {}

    def get_session_activities(self, session_id):
        """Get session activity log.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            list: List of activity dictionaries with keys for id, activity_type,
                description, created_at, and user_id. Ordered by created_at descending.
        """
        activities = SessionActivity.objects.filter(session_id=session_id).order_by(
            "-created_at"
        )

        return [
            {
                "id": str(activity.id),
                "activity_type": activity.activity_type,
                "description": activity.description,
                "created_at": activity.created_at,
                "user_id": str(activity.user_id) if activity.user_id else None,
            }
            for activity in activities
        ]

    def get_search_queries(self, session_id):
        """Get search queries for a session.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            list: Empty list - search queries should be retrieved via ISearchStrategy.

        Note:
            This method returns an empty list in ReviewManagerAdapter
            because search queries are managed by the search_strategy app.
            The actual implementation is in SearchStrategyAdapter.
        """
        # Search queries belong to search_strategy app, not review_manager
        return []


class ResultsManagerAdapter(IResultsManager):
    """Adapter for results manager operations."""

    def get_processed_results_for_session(self, session_id):
        """Get processed results for a session.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            list: List of processed result dictionaries with keys for id, title,
                url, domain, document_type, is_pdf, and processed_at.
        """
        results = ProcessedResult.objects.filter(session_id=session_id).select_related(
            "raw_result"
        )

        return [
            {
                "id": str(result.id),
                "title": result.title,
                "url": result.url,
                "domain": result.raw_result.display_link if result.raw_result else None,
                "document_type": result.document_type,
                "is_pdf": result.is_pdf,
                "processed_at": result.processed_at,
            }
            for result in results
        ]

    def get_duplicate_statistics(self, session_id):
        """Get duplicate statistics for a session.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            dict: Statistics with keys for total (int), duplicates (int),
                and unique (int) result counts.
        """
        stats = ProcessedResult.objects.filter(session_id=session_id).aggregate(
            total=Count("id"), duplicates=Count("id", filter=Q(is_duplicate=True))
        )

        return {
            "total": stats["total"] or 0,
            "duplicates": stats["duplicates"] or 0,
            "unique": (stats["total"] or 0) - (stats["duplicates"] or 0),
        }

    def get_quality_distribution(self, session_id):
        """Get quality score distribution.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            dict: Quality distribution with keys for distribution (dict with
                high, medium, low, very_low counts) and average (float) score.
        """
        results = ProcessedResult.objects.filter(session__id=session_id)

        distribution = {
            "high": results.filter(processing_quality_score__gte=0.8).count(),
            "medium": results.filter(
                processing_quality_score__gte=0.6, processing_quality_score__lt=0.8
            ).count(),
            "low": results.filter(
                processing_quality_score__gte=0.4, processing_quality_score__lt=0.6
            ).count(),
            "very_low": results.filter(processing_quality_score__lt=0.4).count(),
        }

        avg_quality = results.aggregate(avg=Avg("processing_quality_score"))["avg"] or 0

        return {
            "distribution": distribution,
            "average": float(avg_quality),
        }

    def get_results_by_domain(self, session_id):
        """Get results grouped by domain.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            dict: Domain names mapped to result counts (int), limited to top 10.
        """
        domain_counts = (
            ProcessedResult.objects.filter(session_id=session_id)
            .values("raw_result__domain")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        return {
            item["raw_result__domain"]: item["count"]
            for item in domain_counts
            if item["raw_result__domain"]
        }


class ReviewResultsAdapter(IReviewResults):
    """Adapter for review results operations."""

    def get_review_decisions_for_session(self, session_id):
        """Get all review decisions for a session.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            list: List of review decision dictionaries with keys for id, result_id,
                decision, reason, notes, user_id, and created_at.
        """
        decisions = SimpleReviewDecision.objects.filter(
            result__session_id=session_id
        ).select_related("result", "reviewer")

        return [
            {
                "id": str(decision.id),
                "result_id": str(decision.result_id),
                "decision": decision.decision,
                "reason": decision.exclusion_reason,
                "notes": decision.notes,
                "user_id": str(decision.reviewer_id) if decision.reviewer_id else None,
                "created_at": decision.reviewed_at,
            }
            for decision in decisions
        ]

    def get_inclusion_statistics(self, session_id):
        """Get inclusion/exclusion statistics.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            dict: Statistics with keys for include, exclude, maybe, and total
                counts (all int values).
        """
        stats = (
            SimpleReviewDecision.objects.filter(result__session_id=session_id)
            .values("decision")
            .annotate(count=Count("id"))
        )

        result = {
            "include": 0,
            "exclude": 0,
            "maybe": 0,
            "total": 0,
        }

        for item in stats:
            if item["decision"] in result:
                result[item["decision"]] = item["count"]
            result["total"] += item["count"]

        return result

    def get_exclusion_reasons(self, session_id):
        """Get exclusion reasons with counts.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            list: List of exclusion reason dictionaries with keys for reason,
                count, and percentage. Ordered by count descending.
        """
        reasons = (
            SimpleReviewDecision.objects.filter(
                result__session_id=session_id,
                decision="exclude",
                exclusion_reason__isnull=False,
            )
            .values("exclusion_reason")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        return [
            {
                "reason": item["exclusion_reason"],
                "count": item["count"],
                "percentage": 0,  # Calculate if needed
            }
            for item in reasons
        ]

    def get_review_progress(self, session_id):
        """Get review progress statistics.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            dict: Progress statistics with keys for total_results (int),
                reviewed_results (int), pending_results (int), and
                completion_percentage (float).
        """
        total_results = ProcessedResult.objects.filter(session_id=session_id).count()

        reviewed_results = (
            SimpleReviewDecision.objects.filter(result__session_id=session_id)
            .values("result_id")
            .distinct()
            .count()
        )

        return {
            "total_results": total_results,
            "reviewed_results": reviewed_results,
            "pending_results": total_results - reviewed_results,
            "completion_percentage": (
                (reviewed_results / total_results * 100) if total_results > 0 else 0
            ),
        }


class SearchStrategyAdapter(ISearchStrategy):
    """Adapter for search strategy operations."""

    def get_search_queries(self, session_id):
        """Get search queries with details.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            list: List of search query dictionaries with comprehensive metadata
                including id, query_text, query_type, filters, timestamps, and
                execution statistics. Ordered by created_at.
        """
        queries = SearchQuery.objects.filter(session_id=session_id).order_by(
            "created_at"
        )

        return [
            {
                "id": str(query.id),
                "query_text": query.query_text,
                "query_type": query.query_type,
                "filters": {},
                "created_at": query.created_at,
                "executed_at": None,
                "result_count": query.estimated_results,
                "is_primary": query.execution_order == 1,
                "target_domain": query.target_domain,
                # Additional fields for compatibility
                "population": "",
                "interest": "",
                "context": "",
                "search_engines": ["google"],
                "include_keywords": [],
                "exclude_keywords": [],
                "date_from": None,
                "date_to": None,
                "languages": [],
                "document_types": [],
                "max_results": query.estimated_results,
                "executions_count": (
                    query.executions.count() if hasattr(query, "executions") else 0
                ),
                "total_results": query.estimated_results,
                "avg_results_per_execution": query.estimated_results,
                "success_rate": 100.0,
            }
            for query in queries
        ]

    def get_query_effectiveness(self, session_id):
        """Calculate query effectiveness metrics.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            dict: Effectiveness metrics with keys for total_queries (int),
                executed_queries (int), total_results (int), and
                average_results_per_query (float).
        """
        queries = SearchQuery.objects.filter(session__id=session_id)

        total_queries = queries.count()
        executed_queries = queries.filter(is_active=True).count()
        total_results = queries.aggregate(total=Sum("estimated_results"))["total"] or 0

        return {
            "total_queries": total_queries,
            "executed_queries": executed_queries,
            "total_results": total_results,
            "average_results_per_query": (
                total_results / executed_queries if executed_queries > 0 else 0
            ),
        }

    def get_search_terms(self, session_id):
        """Get all search terms used.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            list: Sorted list of unique search terms (strings) extracted from
                all query texts for the session.
        """
        queries = SearchQuery.objects.filter(session_id=session_id).values_list(
            "query_text", flat=True
        )

        # Extract unique terms (simple implementation)
        terms = set()
        for query in queries:
            terms.update(query.lower().split())

        return sorted(list(terms))

    def get_database_coverage(self, session_id):
        """Get database/source coverage statistics.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            dict: Query types mapped to their usage counts (int).
        """
        queries = (
            SearchQuery.objects.filter(session_id=session_id)
            .values("query_type")
            .annotate(count=Count("id"))
        )

        return {item["query_type"]: item["count"] for item in queries}


# Factory functions for dependency injection
def get_review_manager():
    """Get review manager adapter instance.

    Returns:
        IReviewManager: ReviewManagerAdapter instance for dependency injection.
    """
    return ReviewManagerAdapter()


def get_results_manager():
    """Get results manager adapter instance.

    Returns:
        IResultsManager: ResultsManagerAdapter instance for dependency injection.
    """
    return ResultsManagerAdapter()


def get_review_results():
    """Get review results adapter instance.

    Returns:
        IReviewResults: ReviewResultsAdapter instance for dependency injection.
    """
    return ReviewResultsAdapter()


def get_search_strategy():
    """Get search strategy adapter instance.

    Returns:
        ISearchStrategy: SearchStrategyAdapter instance for dependency injection.
    """
    return SearchStrategyAdapter()


class SerpExecutionAdapter(ISerpExecution):
    """Adapter for SERP execution operations."""

    def get_raw_results_count(self, session_id):
        """Get count of raw search results.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            int: Total count of raw search results for the session.
        """
        # Import locally to avoid circular imports
        from apps.serp_execution.models import RawSearchResult

        return RawSearchResult.objects.filter(
            execution__query__session_id=session_id
        ).count()

    def get_raw_results_for_session(self, session_id):
        """Get raw search results for a session.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            list: List of raw result dictionaries with keys for id, title, url,
                snippet, domain, position, created_at, and execution_id.
        """
        from apps.serp_execution.models import RawSearchResult

        results = RawSearchResult.objects.filter(
            execution__query__session_id=session_id
        ).select_related("execution")

        return [
            {
                "id": str(result.id),
                "title": result.title,
                "url": result.url,
                "snippet": result.snippet,
                "domain": result.domain,
                "position": result.position,
                "created_at": result.created_at,
                "execution_id": str(result.execution.id) if result.execution else None,
            }
            for result in results
        ]

    def get_execution_statistics(self, session_id):
        """Get search execution statistics.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            dict: Execution statistics with keys for total_executions (int),
                successful_executions (int), failed_executions (int), and
                success_rate (float percentage).
        """
        from apps.serp_execution.models import SearchExecution

        executions = SearchExecution.objects.filter(query__session_id=session_id)

        total = executions.count()
        successful = executions.filter(status="completed").count()
        failed = executions.filter(status="failed").count()

        return {
            "total_executions": total,
            "successful_executions": successful,
            "failed_executions": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0,
        }

    def get_results_by_source(self, session_id):
        """Get results grouped by source/API.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            dict: Search engine sources mapped to result counts (int).
        """
        from apps.serp_execution.models import RawSearchResult

        source_counts = (
            RawSearchResult.objects.filter(execution__query__session_id=session_id)
            .values("execution__search_engine")
            .annotate(count=Count("id"))
        )

        return {
            item["execution__search_engine"]: item["count"]
            for item in source_counts
            if item["execution__search_engine"]
        }

    def get_executions_for_session(self, session_id):
        """Get all search executions for a session.

        Args:
            session_id: UUID identifier for the session.

        Returns:
            list: List of execution dictionaries with keys for id, query_text,
                started_at, completed_at, status, results_count, duration_seconds,
                api_source, and error_message. Ordered by started_at.
        """
        from apps.serp_execution.models import SearchExecution

        executions = (
            SearchExecution.objects.filter(query__session_id=session_id)
            .select_related("query")
            .order_by("started_at")
        )

        return [
            {
                "id": str(execution.id),
                "query_text": execution.query.query_text if execution.query else "",
                "started_at": execution.started_at,
                "completed_at": execution.completed_at,
                "status": execution.status,
                "results_count": execution.results_count or 0,
                "duration_seconds": (
                    (execution.completed_at - execution.started_at).total_seconds()
                    if execution.started_at and execution.completed_at
                    else 0
                ),
                "api_source": execution.search_engine,
                "error_message": execution.error_message,
            }
            for execution in executions
        ]


def get_serp_execution():
    """Get SERP execution adapter instance.

    Returns:
        ISerpExecution: SerpExecutionAdapter instance for dependency injection.
    """
    return SerpExecutionAdapter()
