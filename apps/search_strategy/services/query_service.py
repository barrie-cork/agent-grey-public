"""Query service for search strategy app."""

from typing import Optional
from uuid import UUID

from apps.search_strategy.models import SearchQuery, SearchStrategy


class QueryService:
    """Service for query-related operations."""

    @staticmethod
    def get_active_query_count(session_id: UUID) -> int:
        """Get the count of active queries for a session."""
        return SearchQuery.objects.filter(session_id=session_id, is_active=True).count()

    @staticmethod
    def has_search_strategy(session_id: UUID) -> bool:
        """Check if a session has a search strategy."""
        return SearchStrategy.objects.filter(session_id=session_id).exists()

    @staticmethod
    def has_active_queries(session_id: UUID) -> bool:
        """Check if a session has any active queries."""
        return SearchQuery.objects.filter(
            session_id=session_id, is_active=True
        ).exists()

    @staticmethod
    def get_search_strategy(session_id: UUID) -> Optional[SearchStrategy]:
        """Get the search strategy for a session."""
        try:
            return SearchStrategy.objects.get(session__id=session_id)
        except SearchStrategy.DoesNotExist:
            return None
