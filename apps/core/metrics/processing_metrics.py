"""
Result processing metrics instrumentation.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager

import structlog

from apps.core.metrics.enums import ProcessingStatus
from apps.core.metrics.registry import (
    deduplication_rate,
    processing_duration_seconds,
    results_processed_total,
)

logger = structlog.get_logger(__name__)


@contextmanager
def track_processing_operation(operation_name: str) -> Generator[None, None, None]:
    """
    Track duration of a processing operation.

    Args:
        operation_name (str): Name of operation ('deduplication', 'normalisation', etc.).

    Yields:
        None

    Example:
        >>> with track_processing_operation('deduplication'):
        ...     perform_deduplication(results)
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        processing_duration_seconds.labels(operation=operation_name).observe(duration)
        logger.debug(
            "processing_operation_tracked",
            operation=operation_name,
            duration_seconds=round(duration, 3),
        )


def record_processing_result(status: ProcessingStatus) -> None:
    """
    Record result processing outcome.

    Args:
        status (ProcessingStatus): Processing status enum value.

    Returns:
        None

    Raises:
        Exception: Logged but not raised (fail-safe).

    Example:
        >>> record_processing_result(ProcessingStatus.SUCCESS)
    """
    try:
        results_processed_total.labels(status=status.value).inc()
    except Exception as e:
        logger.error(
            "processing_result_recording_failed",
            status=status,
            error=str(e),
        )


def update_deduplication_rate(total_results: int, unique_results: int) -> None:
    """
    Update deduplication effectiveness metric.

    Args:
        total_results (int): Total results before deduplication.
        unique_results (int): Unique results after deduplication.

    Returns:
        None

    Raises:
        Exception: Logged but not raised (fail-safe).

    Example:
        >>> update_deduplication_rate(total_results=100, unique_results=80)
        >>> # Sets gauge to 20.0 (20% duplicates)
    """
    try:
        if total_results > 0:
            duplicate_percentage = (
                (total_results - unique_results) / total_results
            ) * 100
            deduplication_rate.set(duplicate_percentage)

            logger.info(
                "deduplication_rate_updated",
                total_results=total_results,
                unique_results=unique_results,
                duplicate_percentage=round(duplicate_percentage, 2),
            )
    except Exception as e:
        logger.error(
            "deduplication_rate_update_failed",
            error=str(e),
        )
