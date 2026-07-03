"""
Helper functions for SerperClient to reduce file size.
Extracted rate limiting, retry logic, and error handling utilities.
"""

import logging
from typing import Tuple

import pybreaker
import requests

from .rate_limiter import get_rate_limiter
from .serper_exceptions import (
    SerperConnectionError,
    SerperRateLimitError,
    SerperTimeoutError,
)

logger = logging.getLogger(__name__)


def enforce_rate_limit(max_wait: float = 30.0) -> bool:
    """
    Enforce rate limiting for Serper API calls.

    Args:
        max_wait: Maximum time to wait for rate limit

    Returns:
        bool: True if can proceed, False if rate limited

    Raises:
        SerperRateLimitError: If rate limit exceeded and cannot wait
    """
    rate_limiter = get_rate_limiter()
    if not rate_limiter.wait_if_needed("serper_api", max_wait=max_wait):
        raise SerperRateLimitError("Rate limit exceeded, unable to proceed")
    return True


def handle_safe_search_error(
    error: Exception, query: str, processor
) -> Tuple[list, dict]:
    """
    Handle errors in safe_search method with graceful fallback.

    Args:
        error: The exception that occurred
        query: The search query that failed
        processor: SerperProcessor instance for creating error responses

    Returns:
        Tuple of (results, metadata) with error information
    """
    if isinstance(error, pybreaker.CircuitBreakerError):
        logger.warning(f"Circuit breaker open for Serper API. Query skipped: {query}")
        return processor.create_error_response(
            "circuit_breaker_open", "Search service temporarily unavailable"
        )
    elif isinstance(error, requests.exceptions.Timeout):
        logger.error(f"Timeout searching for: {query}")
        return processor.create_error_response("timeout", "Search request timed out")
    else:
        logger.error(f"Search error for '{query}': {error}")
        return processor.create_error_response("general_error", str(error))


def log_request_details(
    query: str, api_params: dict, requested_num: int, http_client_url: str
) -> None:
    """
    Log detailed request information for debugging.

    Args:
        query: Search query string
        api_params: Parameters being sent to API
        requested_num: Number of results requested
        http_client_url: Base URL of HTTP client
    """
    # Log request details for Issue #91 and #108 debugging
    logger.info(f"Executing Serper search: {query[:50]}...")
    logger.info(f"[Issue #91] Request URL: {http_client_url}")
    logger.info(f"[Issue #91] API params being sent: {api_params}")
    logger.info(f"[Issue #91] Internal tracking - requested_num: {requested_num}")

    # CRITICAL logging for Issue #108
    logger.warning(
        f"[Issue #108] EXACT QUERY BEING SENT TO SERPER API: '{api_params.get('q', '')}'"
    )
    logger.warning(f"[Issue #108] REQUESTED NUM: {api_params.get('num', 0)}")


def handle_api_exceptions(error: Exception, query: str) -> None:
    """
    Handle and re-raise API exceptions with appropriate logging.

    Args:
        error: The exception to handle
        query: The query that caused the error

    Raises:
        SerperTimeoutError: For timeout errors
        SerperConnectionError: For connection errors
        SerperAPIError: For other API errors
        Or re-raises the original exception
    """
    from .serper_exceptions import SerperAPIError, SerperAuthError, SerperQuotaError

    if isinstance(error, requests.exceptions.Timeout):
        logger.error(f"Timeout executing query: {query}")
        raise SerperTimeoutError("Request timed out")
    elif isinstance(error, requests.exceptions.ConnectionError):
        logger.error(f"Connection error executing query: {query}")
        raise SerperConnectionError("Connection error")
    elif isinstance(
        error, (SerperRateLimitError, SerperAuthError, SerperQuotaError, SerperAPIError)
    ):
        # Re-raise specific Serper exceptions without wrapping
        raise
    else:
        logger.error(f"Unexpected error executing query: {query}, Error: {str(error)}")
        raise SerperAPIError(f"Unexpected error: {str(error)}")


def validate_response_with_logging(validator, data: dict, logger) -> None:
    """
    Validate API response structure and log any issues.

    Args:
        validator: SerperValidator instance
        data: Response data to validate
        logger: Logger instance

    Raises:
        SerperResponseError: If response structure is invalid
    """
    from .serper_exceptions import SerperResponseError

    is_valid, error_msg, warnings = validator.validate_response_structure(data)
    if not is_valid:
        logger.error(f"Invalid response structure: {error_msg}")
        raise SerperResponseError(f"Invalid API response structure: {error_msg}")

    # Log any warnings
    for warning in warnings:
        logger.warning(f"Response validation warning: {warning}")
