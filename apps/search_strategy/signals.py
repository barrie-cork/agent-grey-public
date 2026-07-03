"""
Signal handlers for search strategy app.
Handles workflow transitions when search strategies are completed.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.review_manager.signals import session_status_changed
from apps.search_strategy.models import SearchQuery

logger = logging.getLogger(__name__)


def get_session_queries_data(session_id: str):
    """
    Internal API for accessing search query data without exposing models.
    """
    from apps.review_manager.models import SearchSession

    try:
        session = SearchSession.objects.get(id=session_id)
        strategy = session.search_strategy
        queries = strategy.search_queries.filter(is_active=True)
    except (SearchSession.DoesNotExist, AttributeError):
        return []

    return [
        {
            "id": str(query.id),
            "query_text": query.query_text,
            "query_type": query.query_type,
            "target_domain": query.target_domain,
            "execution_order": query.execution_order,
            "created_at": query.created_at.isoformat(),
        }
        for query in queries
    ]


def get_query_count(session_id: str) -> int:
    """Get count of active queries for a session."""
    from apps.review_manager.models import SearchSession

    try:
        session = SearchSession.objects.get(id=session_id)
        strategy = session.search_strategy
        return strategy.search_queries.filter(is_active=True).count()
    except (SearchSession.DoesNotExist, AttributeError):
        return 0


@receiver(
    post_save,
    sender=SearchQuery,
    dispatch_uid="search_strategy.check_strategy_completion",
)
def check_strategy_completion(sender, instance, created, **kwargs):
    """
    Check if all queries for a session are defined and transition to ready_to_execute.

    This signal fires after a SearchQuery is saved and checks if the search
    strategy is complete (has at least one active query with proper PIC fields).
    """
    if not instance.strategy or not instance.session:
        return

    session = instance.session

    # Refresh from DB to avoid stale cached status when multiple queries
    # are saved in sequence (prevents redundant transition signals)
    session.refresh_from_db(fields=["status"])

    # Only process if session is in the right state
    if session.status not in ["draft", "defining_search"]:
        return

    # Get the search strategy for this session
    try:
        strategy = session.search_strategy
    except AttributeError:
        logger.debug(f"Session {session.id} has no search strategy")
        return

    # Check if strategy is complete
    if not strategy.validate_completeness():
        logger.debug(f"Strategy for session {session.id} is not complete")
        return

    # Check if we have at least one active query
    active_queries = strategy.search_queries.filter(is_active=True)

    if not active_queries.exists():
        logger.debug(f"No active queries for strategy {strategy.id}")
        return

    # Check if all active queries have required fields
    for query in active_queries:
        if not query.query_text:
            logger.debug(f"Query {query.id} missing query text")
            return

    # Emit signal to request status transition instead of direct import
    session_status_changed.send(
        sender=SearchQuery,
        session_id=str(session.id),
        requested_status="ready_to_execute",
        reason=f"Search strategy completed with {active_queries.count()} queries",
    )

    logger.info(f"Session {session.id} requested transition to ready_to_execute")


def mark_strategy_complete(session):
    """
    Manually mark a search strategy as complete and ready for execution.

    This can be called from views or management commands to trigger
    the workflow transition.

    Args:
        session: SearchSession instance

    Returns:
        Tuple of (success, error_message)
    """
    # Get the search strategy for this session
    try:
        strategy = session.search_strategy
    except AttributeError:
        return False, "No search strategy defined for this session"

    # Validate strategy completeness
    if not strategy.validate_completeness():
        return False, "Search strategy is not complete"

    # Validate session has queries
    active_queries = strategy.search_queries.filter(is_active=True)

    if not active_queries.exists():
        return False, "No active search queries defined"

    # Validate all queries have required fields
    for query in active_queries:
        if not query.query_text:
            return False, f"Query '{query}' missing query text"

    # Emit signal to request status transition
    session_status_changed.send(
        sender=session.__class__,
        session_id=str(session.id),
        requested_status="ready_to_execute",
        reason=f"Search strategy marked complete with {active_queries.count()} queries",
    )

    return True, None
