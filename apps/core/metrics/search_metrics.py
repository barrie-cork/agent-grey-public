"""
Search execution metrics instrumentation.

Tracks search query performance, API success rates, and result counts.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Optional

import structlog

from apps.core.metrics.enums import ErrorType, SearchStatus
from apps.core.metrics.registry import (
    search_api_errors_total,
    search_duration_seconds,
    search_queries_total,
    search_results_count,
)

if TYPE_CHECKING:
    from apps.search_strategy.models import SearchQuery

logger = structlog.get_logger(__name__)


@contextmanager
def track_search_execution(
    query: SearchQuery, api_provider: str = "serper"
) -> Generator[SearchTracker, None, None]:
    """
    Context manager to track search execution metrics.

    Args:
        query (SearchQuery): SearchQuery model instance.
        api_provider (str): API provider name. Defaults to 'serper'.

    Yields:
        SearchTracker: Tracker object with record_results() method.

    Raises:
        Exception: Re-raised after recording error metrics.

    Example:
        >>> with track_search_execution(query_obj) as tracker:
        ...     results = perform_search(query_obj)
        ...     tracker.record_results(len(results), status='success')
    """
    start_time = time.time()
    tracker = SearchTracker(query, api_provider, start_time)

    try:
        yield tracker
    except Exception as e:
        # Record error
        duration = time.time() - start_time
        tracker.record_error(str(e), duration)
        raise
    finally:
        # Ensure duration is always recorded
        if not tracker._recorded:
            duration = time.time() - start_time
            tracker.record_results(0, status=SearchStatus.ERROR, duration=duration)


class SearchTracker:
    """
    Helper class for tracking search execution within context manager.

    Attributes:
        query (SearchQuery): SearchQuery model instance being tracked.
        api_provider (str): API provider name (e.g., 'serper').
        start_time (float): Unix timestamp when search started.
        _recorded (bool): Flag to prevent double-recording metrics.
    """

    def __init__(
        self, query: SearchQuery, api_provider: str, start_time: float
    ) -> None:
        """
        Initialize search tracker.

        Args:
            query (SearchQuery): SearchQuery model instance.
            api_provider (str): API provider name.
            start_time (float): Unix timestamp when search started.
        """
        self.query = query
        self.api_provider = api_provider
        self.start_time = start_time
        self._recorded = False

    def record_results(
        self,
        result_count: int,
        status: SearchStatus = SearchStatus.SUCCESS,
        duration: Optional[float] = None,
    ) -> None:
        """
        Record successful search execution.

        Args:
            result_count (int): Number of results returned.
            status (SearchStatus): Execution status enum. Defaults to SearchStatus.SUCCESS.
            duration (Optional[float]): Override duration in seconds.

        Returns:
            None

        Example:
            >>> tracker.record_results(10, status=SearchStatus.SUCCESS)
        """
        if self._recorded:
            return

        duration = duration or (time.time() - self.start_time)

        # Record query counter
        search_queries_total.labels(
            status=status.value if hasattr(status, "value") else status,
            api_provider=self.api_provider,
        ).inc()

        # Record duration histogram
        search_duration_seconds.labels(api_provider=self.api_provider).observe(duration)

        # Record result count histogram
        search_results_count.labels(api_provider=self.api_provider).observe(
            result_count
        )

        self._recorded = True

        logger.info(
            "search_execution_tracked",
            query_id=str(self.query.id),
            api_provider=self.api_provider,
            status=status,
            result_count=result_count,
            duration_seconds=round(duration, 3),
        )

    def record_error(
        self, error_message: str, duration: Optional[float] = None
    ) -> None:
        """
        Record failed search execution.

        Args:
            error_message (str): Error description.
            duration (Optional[float]): Override duration in seconds.

        Returns:
            None

        Example:
            >>> tracker.record_error("Timeout after 30s")
        """
        if self._recorded:
            return

        duration = duration or (time.time() - self.start_time)

        # Determine error type from error message
        error_type = ErrorType.UNKNOWN
        error_lower = error_message.lower()
        if "timeout" in error_lower:
            error_type = ErrorType.TIMEOUT
        elif "rate" in error_lower or "limit" in error_lower:
            error_type = ErrorType.RATE_LIMIT
        elif "auth" in error_lower or "key" in error_lower:
            error_type = ErrorType.AUTHENTICATION
        elif "connection" in error_lower or "network" in error_lower:
            error_type = ErrorType.NETWORK

        # Record error counter
        search_api_errors_total.labels(
            api_provider=self.api_provider, error_type=error_type.value
        ).inc()

        # Record failed query
        search_queries_total.labels(
            status=SearchStatus.ERROR.value, api_provider=self.api_provider
        ).inc()

        # Record duration
        search_duration_seconds.labels(api_provider=self.api_provider).observe(duration)

        self._recorded = True

        logger.error(
            "search_execution_error_tracked",
            query_id=str(self.query.id),
            api_provider=self.api_provider,
            error_type=error_type,
            error_message=error_message[:200],
            duration_seconds=round(duration, 3),
        )
