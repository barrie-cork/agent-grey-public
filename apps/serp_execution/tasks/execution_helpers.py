"""
Helper functions for SERP execution tasks.
Extracted to reduce main task function complexity.
"""

import logging
from typing import Any, Callable, Dict

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError

from apps.serp_execution.utils import (
    build_execution_progress_message,
    extract_result_count,
    format_result_count_message,
    parse_query_details,
)

logger = logging.getLogger(__name__)


def _schedule_session_monitoring(session_id: str) -> None:
    """
    Schedule monitoring task to check if session execution is complete.

    Args:
        session_id: Search session ID to monitor
    """
    try:
        from apps.serp_execution.tasks.monitoring import monitor_session_completion_task

        # Schedule monitoring check with 5 second delay
        monitor_session_completion_task.apply_async(
            args=(session_id,),
            countdown=5,  # Check 5 seconds after execution completes
        )
    except (ImportError, ConnectionError, TimeoutError, OSError) as e:
        logger.error(
            f"Failed to schedule monitoring task for session {session_id}: {e}"
        )


def handle_progress_updates(
    session_id: str | None,
    execution: Any,
    phase: str,
    message: str,
    processed_count: int = 0,
    total_count: int = 0,
) -> None:
    """
    Handle progress updates for execution.

    Args:
        session_id: Search session ID
        execution: SearchExecution instance
        phase: Current execution phase
        message: Progress message
        processed_count: Number of items processed
        total_count: Total number of items
    """
    try:
        from apps.review_manager.models import SearchSession

        session = SearchSession.objects.get(id=session_id)
        session.update_status_detail(message)
    except (ObjectDoesNotExist, DatabaseError) as e:
        logger.warning(
            f"Failed to update progress for execution {execution.id if execution else 'unknown'}: {str(e)}"
        )


def execute_search_with_progress(
    executor: Any,
    query: Any,
    execution: Any,
    config: Dict[str, Any],
    progress_service: Any,
    retry_func: Callable,
) -> tuple[Any, Dict[str, Any], Dict[str, Any]]:
    """
    Execute search with integrated progress tracking.

    Args:
        executor: SerpQueryExecutor instance
        query: SearchQuery instance
        execution: SearchExecution instance
        config: Configuration dictionary
        progress_service: QueryProgressService instance (deprecated, kept for compatibility)
        retry_func: Celery retry function

    Returns:
        tuple: (results, metadata, api_params) or raises exception
    """
    from apps.serp_execution.query_executor import SerperAPIError
    from apps.serp_execution.tasks.execution import (
        _execute_search_with_retry,
        _prepare_api_parameters,
    )

    # Get session ID from query
    session_id = str(query.session_id)

    # Prepare API parameters
    api_params = _prepare_api_parameters(query, executor, config)

    # Store parameters
    execution.api_parameters = api_params
    execution.save(update_fields=["api_parameters"])

    # Parse query details for detailed message
    query_details = parse_query_details(query.query_text, api_params)
    progress_message = build_execution_progress_message(query_details, "Executing")

    # Update progress: Querying API with detailed message
    handle_progress_updates(session_id, execution, "querying", progress_message)

    # Execute search with retry logic
    try:
        results, metadata = _execute_search_with_retry(
            executor, query.query_text, api_params, execution, retry_func
        )
    except SerperAPIError as e:
        # Include query details in error message
        error_message = f"Failed {build_execution_progress_message(query_details, 'executing')}: {str(e)[:50]}"

        # Update progress with error
        handle_progress_updates(session_id, execution, "error", error_message)
        # Re-raise for main handler
        raise

    # Extract result count and format message
    result_count = extract_result_count(results)
    result_message = format_result_count_message(result_count)

    # Update progress: Results Retrieved with count
    handle_progress_updates(session_id, execution, "parsing", result_message)

    return results, metadata, api_params


def process_and_store_results(
    executor: Any,
    execution: Any,
    results: Dict[str, Any],
    api_params: Dict[str, Any],
    config: Dict[str, Any],
    progress_service: Any,
) -> Dict[str, Any]:
    """
    Process API results and store them with progress tracking.

    Args:
        executor: SerpQueryExecutor instance
        execution: SearchExecution instance
        results: API results dictionary
        api_params: API parameters used
        config: Configuration dictionary
        progress_service: QueryProgressService instance

    Returns:
        dict: Result dictionary with success status and counts
    """
    from apps.serp_execution.tasks.execution import (
        _handle_execution_success,
        _process_api_results,
    )

    # Process API results
    result_counts = _process_api_results(execution, results, api_params)

    # Get session ID from execution
    session_id = str(execution.query.session_id) if execution.query else None

    # Update progress: Conducting deduplication
    handle_progress_updates(
        session_id,
        execution,
        "deduplication",
        "Conducting deduplication",
        processed_count=result_counts.get("api_result_count", 0),
        total_count=result_counts.get("requested_num", 0),
    )

    # Update progress: Denormalizing URLs
    handle_progress_updates(session_id, execution, "finalization", "Denormalizing URLs")

    # Handle successful execution
    result = _handle_execution_success(execution, executor, results, config)

    # Final progress update - Ready for review
    handle_progress_updates(
        session_id, execution, "ready_for_review", "Ready for review"
    )

    # Schedule monitoring task to check session completion
    # This ensures automatic state transitions when all executions complete
    if session_id:
        from django.db import transaction

        transaction.on_commit(lambda: _schedule_session_monitoring(session_id))
        logger.info(
            f"Scheduled monitoring check for session {session_id} after execution completion"
        )

    return result


def handle_execution_error_with_progress(
    execution_id: str,
    error: Exception,
    session_id: str | None = None,
    execution: Any = None,
) -> None:
    """
    Handle execution errors with optional progress update.

    Args:
        execution_id: ID of the SearchExecution
        error: Exception that occurred
        session_id: Optional session ID
        execution: Optional SearchExecution instance
    """
    # Try to update progress with error
    if session_id:
        try:
            handle_progress_updates(
                session_id,
                execution or type("obj", (object,), {"id": execution_id})(),
                "error",
                f"Execution failed: {str(error)[:100]}",
            )
        except (ConnectionError, TimeoutError, OSError):
            pass  # Silently fail if progress update fails

        # Schedule monitoring to check if session should transition despite failure
        from django.db import transaction

        transaction.on_commit(lambda: _schedule_session_monitoring(session_id))
        logger.info(
            f"Scheduled monitoring check for session {session_id} after execution failure"
        )


def handle_complete_execution_error(
    execution_id: str,
    error: Exception,
    request: Any,
    max_retries: int,
    progress_service: Any = None,
    execution: Any = None,
):
    """
    Complete error handling including progress update and retry logic.

    Args:
        execution_id: ID of the SearchExecution
        error: Exception that occurred
        request: Celery request object
        max_retries: Maximum number of retries
        progress_service: Optional QueryProgressService instance
        execution: Optional SearchExecution instance

    Returns:
        dict: Error response for DoesNotExist, None otherwise
    """
    from apps.serp_execution.models import SearchExecution
    from apps.serp_execution.tasks.execution import _handle_execution_error

    logger.error(f"Error in SERP query execution: {str(error)}")

    # Handle SearchExecution.DoesNotExist specially
    if isinstance(error, SearchExecution.DoesNotExist):
        logger.error(f"SearchExecution {execution_id} not found")
        return {
            "success": False,
            "error": "Execution not found",
            "execution_id": execution_id,
        }

    # Handle other exceptions with progress update
    session_id = (
        str(execution.query.session_id) if execution and execution.query else None
    )
    handle_execution_error_with_progress(execution_id, error, session_id, execution)

    # Update execution status and handle retry
    _handle_execution_error(execution_id, error, request, max_retries)

    return None  # Indicates retry should be raised


def initialize_execution_context(
    execution_id: str, query_id: str, task_id: str
) -> tuple[Any, Any, Any, Any, Dict[str, Any]]:
    """
    Initialize execution context and set up progress tracking.

    Args:
        execution_id: ID of the SearchExecution
        query_id: ID of the SearchQuery
        task_id: Celery task ID

    Returns:
        tuple: (execution, query, progress_service, executor, config)
    """
    from apps.core.config import get_config
    from apps.serp_execution.query_executor import SerpQueryExecutor
    from apps.serp_execution.services.query_progress_service import QueryProgressService
    from apps.serp_execution.tasks.execution import (
        _retrieve_execution_and_query,
        _update_execution_start,
    )

    logger.info(f"Starting SERP query execution for execution {execution_id}")

    # Initialize progress service
    from uuid import UUID as _UUID

    progress_service = QueryProgressService(_UUID(execution_id))

    # Retrieve execution and query
    execution, query = _retrieve_execution_and_query(execution_id, query_id)

    # Update execution status
    _update_execution_start(execution, task_id)

    # Get session ID for progress tracking
    session_id = str(query.session_id) if query else str(execution.query.session_id)

    # Progress: Initializing with specific query
    handle_progress_updates(
        session_id, execution, "ready_to_execute", "Initializing search queries"
    )

    # Initialize executor and config
    executor = SerpQueryExecutor()
    config = get_config()

    return execution, query, progress_service, executor, config
