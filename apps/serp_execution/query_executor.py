"""
Query executor for SERP API calls.

This module contains the SerpQueryExecutor class that handles
API query execution with retry logic and processing.
"""

import logging

from django.utils import timezone

from apps.core.services.serper_client import SerperAPIError

from .recovery import recovery_manager
from .services.mock_serper_client import get_serper_client
from .services.result_processor import ResultProcessor

logger = logging.getLogger(__name__)


class SerpQueryExecutor:
    """
    Handles SERP query execution with retry logic and result processing.

    This class encapsulates the logic for executing search queries,
    handling retries, and processing results.
    """

    def __init__(self, api_client=None, result_processor=None):
        """
        Initialize the executor with services.

        Args:
            api_client: SerperClient instance (creates new if not provided).
            result_processor: ResultProcessor instance (creates new if not provided).
        """
        self.api_client = api_client or get_serper_client()
        self.result_processor = result_processor or ResultProcessor()

    def build_api_parameters(self, query_text, strategy, config):
        """
        Build API parameters from strategy and configuration.

        Args:
            query_text: The search query text string.
            strategy: SearchStrategy instance containing search configuration.
            config: Configuration object with default search settings.

        Returns:
            dict: Dictionary of API parameters including query, num_results,
                language, and optionally location.
        """
        # Get configuration from the strategy (allows overrides)
        location = strategy.search_config.get(
            "location", config.search.default_location
        )

        # Get the requested number of results
        requested_num = strategy.search_config.get(
            "max_results", config.search.default_num_results
        )
        logger.info(
            f"[Issue #91] Strategy max_results: "
            f"{strategy.search_config.get('max_results')}, "
            f"Config default: {config.search.default_num_results}, "
            f"Final requested_num: {requested_num}"
        )

        # Apply buffer strategy for better result accuracy (Issue #13)
        # Request 10% more results to compensate for API variations and deduplication
        # Only apply buffer for requests <= 100 (API limit is 100)
        if requested_num <= 100:
            buffer_multiplier = 1.1  # 10% buffer
            num_with_buffer = int(requested_num * buffer_multiplier)
            # Ensure we don't exceed API limit
            num_with_buffer = min(num_with_buffer, 100)
            logger.info(
                f"[Issue #91] Buffer calculation: {requested_num} * "
                f"{buffer_multiplier} = {requested_num * buffer_multiplier:.1f} "
                f"-> {num_with_buffer}"
            )
            logger.info(
                f"[Issue #75] Applying buffer strategy: requesting "
                f"{num_with_buffer} results (user wants {requested_num})"
            )
        else:
            # For requests > 100, we can't apply buffer due to API limit
            num_with_buffer = requested_num
            logger.info(
                f"[Issue #75] No buffer applied for {requested_num} results "
                f"(exceeds API limit)"
            )

        # Build API parameters with configuration values
        # IMPORTANT: file_types are already included in query_text by SearchStrategy.generate_queries()
        # We MUST NOT pass them separately as that would cause duplicate filetype: operators
        # Example: "search terms filetype:pdf" would become "search terms filetype:pdf filetype:pdf"
        # This causes Google to return zero results
        api_params = {
            "q": query_text,
            "num": num_with_buffer,
            "requested_num": requested_num,  # Store original request for later trimming
            "language": strategy.search_config.get(
                "language", config.search.default_language
            ),
        }

        # Only add location if specified (None means global search)
        if location:
            api_params["location"] = location

        logger.info(
            f"[Issue #75] Built API params: num={num_with_buffer}, "
            f"requested_num={requested_num}, query='{query_text[:100]}...'"
        )
        return api_params

    def execute_with_retry(self, search_query, api_params, execution, retry_func):
        """
        Execute query with retry logic and distributed tracing.

        Args:
            search_query: The search query text string to execute.
            api_params: Dictionary of API parameters for the search call.
            execution: SearchExecution model instance to track the execution.
            retry_func: Celery retry function for handling failures.

        Returns:
            tuple: A tuple of (results, metadata) where results is a dict of
                search results and metadata is a dict of API response metadata.

        Raises:
            SerperAPIError: If API call fails after all retry attempts.
        """
        try:
            # Log the API call details for debugging
            buffer_num = api_params["num"]
            requested_num = api_params.get("requested_num", buffer_num)
            logger.info(
                f"Calling Serper API: query='{search_query[:50]}...', "
                f"buffer_num={buffer_num}, requested_num={requested_num}"
            )

            # Use safe_search to handle circuit breaker gracefully
            results, metadata = self.api_client.safe_search(
                search_query,
                num_results=api_params["num"],
                **{
                    k: v
                    for k, v in api_params.items()
                    if k not in ["q", "num", "requested_num"] and v is not None
                },
            )

            # Check if circuit breaker blocked the request
            if metadata.get("circuit_open"):
                logger.warning(
                    f"Circuit breaker is open for execution {execution.id}, search was blocked"
                )
                return results, metadata

            # Log what we got back from the API
            organic_count = len(results.get("organic", []))
            logger.info(f"API returned {organic_count} organic results")

            # Trim results if buffer was applied and we got more than requested
            if "organic" in results and len(results["organic"]) > requested_num:
                pre_trim_count = len(results["organic"])
                results["organic"] = results["organic"][:requested_num]
                post_trim_count = len(results["organic"])

                # Add buffer tracking to metadata
                metadata["buffer_applied"] = True
                metadata["pre_trim_count"] = pre_trim_count
                metadata["post_trim_count"] = post_trim_count

                logger.info(
                    f"Buffer strategy: Trimmed results from {pre_trim_count} to {post_trim_count} "
                    f"(user requested: {requested_num})"
                )
            else:
                # No trimming needed, log the final count
                logger.info(
                    f"No trimming needed: API returned {organic_count}, "
                    f"user requested {requested_num}"
                )

            return results, metadata

        except SerperAPIError as e:
            logger.error(f"Error in execute_with_retry: {e}", exc_info=True)

            # Check if we should retry
            if recovery_manager.should_retry(e, execution.retry_count):
                # Update retry count
                execution.retry_count += 1
                execution.save(update_fields=["retry_count"])

                # Get retry delay
                delay = recovery_manager.get_retry_delay(e)

                # Retry with delay
                raise retry_func(exc=e, countdown=delay)
            # Can't retry, re-raise the exception
            raise

    def process_api_response(self, results, execution_id, config):
        """
        Process API response into raw results.

        Args:
            results: Dictionary containing API response with organic results.
            execution_id: String ID of the SearchExecution instance.
            config: Configuration object containing processing settings.

        Returns:
            tuple: A tuple of (processed_count, duplicate_count, errors) where
                processed_count is the number of results successfully processed,
                duplicate_count is the number of duplicate results found,
                and errors is a list of processing errors that occurred.
        """
        logger.info(f"Processing API response for execution {execution_id}")

        # Log the response structure
        if results:
            logger.debug(f"API response has keys: {list(results.keys())}")
        else:
            logger.error(f"API response is None or empty for execution {execution_id}")
            return 0, 0, ["API response was empty"]

        # Check for API error response
        if "error" in results or "error_type" in results:
            error_msg = results.get("error", "Unknown API error")
            error_type = results.get("error_type", "unknown")
            logger.error(
                f"Serper API returned error for execution {execution_id}. "
                f"Error: {error_msg}, Type: {error_type}"
            )

            # Provide standardised user-friendly error messages
            # Format: "Error type: Suggested action."
            if "invalid_api_key" in str(error_type).lower():
                return (
                    0,
                    0,
                    [
                        "Authentication failed: Please verify your SERPER_API_KEY configuration."
                    ],
                )
            elif "rate_limit" in str(error_type).lower():
                return (
                    0,
                    0,
                    ["Rate limit exceeded: Please wait before retrying your search."],
                )
            elif "quota" in str(error_type).lower():
                return (
                    0,
                    0,
                    [
                        "API quota exceeded: Please check your Serper account limits or upgrade your plan."
                    ],
                )
            else:
                return (
                    0,
                    0,
                    [
                        f"Search API error: {error_msg}. Please try again or contact support."
                    ],
                )

        organic_results = results.get("organic", [])
        logger.info(
            f"Found {len(organic_results)} organic results in API response for execution {execution_id}"
        )

        if not organic_results:
            logger.warning(
                f"No organic results returned for execution {execution_id}. "
                f"Response keys: {list(results.keys())}"
            )
            # Log any alternative result types present
            for key in ["knowledgeGraph", "answerBox", "topStories", "peopleAlsoAsk"]:
                if key in results and results[key]:
                    logger.info(
                        f"Alternative result type '{key}' present with {len(results[key])} items"
                    )

            # Check if this might be due to an error that wasn't caught above
            if any(key in results for key in ["error", "error_type"]):
                error_details = {
                    k: results.get(k) for k in ["error", "error_type"] if k in results
                }
                logger.error(f"API error details: {error_details}")
                return (
                    0,
                    0,
                    [f"Search failed: {error_details.get('error', 'Unknown error')}"],
                )

            return 0, 0, []

        # Process and store results
        logger.info(f"Starting result processing for {len(organic_results)} results")
        processed_count, duplicate_count, errors = (
            self.result_processor.process_search_results(
                execution_id=execution_id,
                raw_results=organic_results,
                batch_size=config.processing.batch_size,
            )
        )

        logger.info(
            f"Pipeline complete for execution {execution_id}: "
            f"processed={processed_count}, duplicates={duplicate_count}, errors={len(errors)}"
        )

        return processed_count, duplicate_count, errors

    def handle_execution_error(self, execution, error, is_final=False):
        """
        Handle execution errors and update execution status.

        Args:
            execution: SearchExecution model instance to update.
            error: The exception that occurred during execution.
            is_final: Boolean indicating whether this is the final attempt.

        Returns:
            dict: Error response dictionary containing success status (False),
                execution_id, error message, and error_category.
        """
        if is_final:
            execution.status = "failed"
            execution.error_message = str(error)
            execution.completed_at = timezone.now()
            execution.save(update_fields=["status", "error_message", "completed_at"])

        error_category = (
            recovery_manager.get_error_category(str(error))
            if isinstance(error, SerperAPIError)
            else "unknown"
        )

        return {
            "success": False,
            "execution_id": str(execution.id),
            "error": str(error),
            "error_category": error_category,
        }

    def mark_execution_complete(self, execution, processed_count):
        """
        Mark execution as complete and update statistics.

        Args:
            execution: SearchExecution model instance to mark as complete.
            processed_count: Integer number of results successfully processed.

        Returns:
            None: Updates the execution instance in place.
        """
        execution.status = "completed"
        execution.results_count = processed_count
        execution.completed_at = timezone.now()
        execution.save(
            update_fields=[
                "status",
                "results_count",
                "completed_at",
            ]
        )
