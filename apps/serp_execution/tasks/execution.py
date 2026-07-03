"""
Execution tasks for SERP queries.
Decomposed from the original tasks.py for better maintainability.
"""

import logging
from typing import Any, Callable

from celery import shared_task
from django.core.mail import mail_admins
from django.utils import timezone

from apps.serp_execution.models import SearchExecution
from apps.serp_execution.query_executor import SerperAPIError, SerpQueryExecutor

logger = logging.getLogger(__name__)


def _retrieve_execution_and_query(execution_id: str, query_id: str):
    """
    Retrieve and validate execution and query objects.

    Args:
        execution_id: ID of the SearchExecution
        query_id: ID of the SearchQuery

    Returns:
        tuple: (SearchExecution, SearchQuery) objects

    Raises:
        SearchExecution.DoesNotExist: If execution not found
        SearchQuery.DoesNotExist: If query not found
    """
    from apps.search_strategy.models import SearchQuery

    execution = SearchExecution.objects.select_related("query").get(id=execution_id)
    query = SearchQuery.objects.get(id=query_id)

    logger.info(f"Retrieved execution {execution_id} and query {query_id}")
    return execution, query


def _update_execution_start(execution: "SearchExecution", task_id: str) -> None:
    """
    Update execution status to running.

    Args:
        execution: SearchExecution instance
        task_id: Celery task ID
    """
    execution.status = "running"
    execution.started_at = timezone.now()
    execution.celery_task_id = task_id
    execution.save(update_fields=["status", "started_at", "celery_task_id"])

    logger.info(f"Updated execution {execution.id} to running status")


def _prepare_api_parameters(query: Any, executor: "SerpQueryExecutor", config: dict):
    """
    Prepare API parameters for the search.

    Args:
        query: SearchQuery instance
        executor: SerpQueryExecutor instance
        config: Configuration dictionary

    Returns:
        dict: API parameters dictionary
    """
    search_query = query.query_text
    api_params = executor.build_api_parameters(search_query, query.strategy, config)

    logger.debug(f"Built API parameters for query {query.id}: {api_params}")
    return api_params


def _execute_search_with_retry(
    executor: "SerpQueryExecutor",
    search_query: str,
    api_params: dict,
    execution: "SearchExecution",
    retry_func: Callable,
):
    """
    Execute search with retry logic.

    Args:
        executor: SerpQueryExecutor instance
        search_query: Search query text
        api_params: API parameters
        execution: SearchExecution instance
        retry_func: Celery retry function

    Returns:
        tuple: (results, metadata) dictionaries

    Raises:
        SerperAPIError: If API call fails after retries
    """
    try:
        results, metadata = executor.execute_with_retry(
            search_query, api_params, execution, retry_func
        )
        return results, metadata
    except SerperAPIError as e:
        logger.error(f"API error for execution {execution.id}: {str(e)}")
        raise


def _process_api_results(execution: "SearchExecution", results: dict, api_params: dict):
    """
    Process and validate API results.

    Args:
        execution: SearchExecution instance
        results: API results dictionary
        api_params: API parameters used

    Returns:
        dict: Dictionary with result counts (api_result_count, requested_num)
    """
    # Store the actual API result count (Issue #13)
    api_result_count = len(results.get("organic", []))
    execution.api_result_count = api_result_count
    execution.save(update_fields=["api_result_count"])

    # Log if API returned fewer results than requested
    requested_num = api_params.get("requested_num", api_params["num"])
    if api_result_count < requested_num:
        logger.warning(
            f"API returned fewer results than requested for execution {execution.id}: "
            f"{api_result_count} < {requested_num}"
        )

    return {"api_result_count": api_result_count, "requested_num": requested_num}


def _handle_execution_success(
    execution: "SearchExecution",
    executor: "SerpQueryExecutor",
    results: dict,
    config: dict,
):
    """
    Handle successful execution completion.

    Args:
        execution: SearchExecution instance
        executor: SerpQueryExecutor instance
        results: API results
        config: Configuration dictionary

    Returns:
        dict: Success result dictionary with keys (success, execution_id,
              results_count, duplicates_count, errors)
    """
    # Process API response
    processed_count, duplicate_count, errors = executor.process_api_response(
        results, execution.id, config
    )

    # Mark execution as complete
    executor.mark_execution_complete(execution, processed_count)

    logger.info(
        f"Successfully executed query for execution {execution.id}: "
        f"{processed_count} results, {duplicate_count} duplicates"
    )

    return {
        "success": True,
        "execution_id": str(execution.id),
        "results_count": processed_count,
        "duplicates_count": duplicate_count,
        "errors": errors,
    }


def _handle_execution_error(
    execution_id: str, error: Exception, retry_request: Any, max_retries: int
) -> None:
    """
    Handle execution errors and update status.

    Args:
        execution_id: ID of the SearchExecution
        error: Exception that occurred
        retry_request: Celery retry request object
        max_retries: Maximum number of retries
    """
    try:
        execution = SearchExecution.objects.get(id=execution_id)

        if retry_request.retries >= max_retries:
            execution.status = "failed"
            execution.error_message = f"Max retries exceeded: {str(error)}"
            execution.completed_at = timezone.now()
            execution.save(update_fields=["status", "error_message", "completed_at"])
            logger.error(
                f"Execution {execution_id} failed after max retries: {str(error)}"
            )
        else:
            execution.retry_count = retry_request.retries
            execution.save(update_fields=["retry_count"])
            logger.info(f"Execution {execution_id} retry {retry_request.retries}")

    except SearchExecution.DoesNotExist:
        logger.error(
            f"Could not update status for execution {execution_id} - execution not found. "
            f"Original error: {str(error)}. Retry attempt: {retry_request.retries}"
        )

        # Track critical error
        mail_admins(
            subject=f"Critical: Lost SearchExecution {execution_id}",
            message=f"SearchExecution {execution_id} was not found when trying to update "
            f"its status after error: {str(error)}",
            fail_silently=True,
        )


@shared_task(bind=True, max_retries=3)
def perform_serp_query_task(self, execution_id: str, query_id: str):
    """
    Perform a single SERP query execution with progress tracking.

    This task executes a search query using the Serper API and processes the results.

    Args:
        execution_id: ID of the SearchExecution
        query_id: ID of the SearchQuery

    Returns:
        dict: Dictionary with execution results including keys (success, execution_id,
              results_count, duplicates_count, errors) or (success, error, execution_id)
    """
    from .execution_helpers import (
        execute_search_with_progress,
        handle_complete_execution_error,
        initialize_execution_context,
        process_and_store_results,
    )

    progress_service, execution = None, None

    try:
        # Initialize and execute search
        execution, query, progress_service, executor, config = (
            initialize_execution_context(execution_id, query_id, self.request.id)
        )
        results, metadata, api_params = execute_search_with_progress(
            executor, query, execution, config, progress_service, self.retry
        )
        return process_and_store_results(
            executor, execution, results, api_params, config, progress_service
        )

    except SerperAPIError as e:
        # Handle API-specific errors
        return executor.handle_execution_error(execution, e, is_final=True)

    except Exception as e:
        # Handle all other exceptions
        error_result = handle_complete_execution_error(
            execution_id, e, self.request, self.max_retries, progress_service, execution
        )
        if error_result:
            return error_result
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3)
def retry_failed_execution_task(self, execution_id: str) -> dict[str, Any]:
    """
    Retry a failed SearchExecution.

    Looks up the execution, resets its status, and delegates to
    perform_serp_query_task for the actual re-execution.

    Args:
        execution_id: ID of the SearchExecution to retry
    """
    try:
        execution = SearchExecution.objects.select_related("query").get(id=execution_id)
    except SearchExecution.DoesNotExist:
        logger.error(f"Retry failed: execution {execution_id} not found")
        return {
            "success": False,
            "error": "Execution not found",
            "execution_id": execution_id,
        }

    if not execution.can_retry():
        logger.warning(
            f"Execution {execution_id} cannot be retried (status={execution.status})"
        )
        return {
            "success": False,
            "error": "Execution cannot be retried",
            "execution_id": execution_id,
        }

    # Reset execution for retry
    execution.status = "pending"
    execution.error_message = ""
    execution.started_at = None
    execution.completed_at = None
    execution.save(
        update_fields=["status", "error_message", "started_at", "completed_at"]
    )

    logger.info(f"Retrying execution {execution_id} for query {execution.query_id}")

    # Delegate to the main execution task (direct call is intentional for synchronous retry)
    return perform_serp_query_task(str(execution.id), str(execution.query_id))  # type: ignore[call-arg]
