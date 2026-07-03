"""
Progress tracking utilities and validation for batch processing.

This module provides consistent progress tracking across the results processing pipeline,
ensuring count validation and avoiding the common issues with progress inconsistencies.
"""

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


class ProcessingProgress:
    """Constants for progress milestones in the processing pipeline."""

    # Major milestone percentages
    SEARCH_COMPLETE = 25
    METADATA_EXTRACTION = 50
    DEDUPLICATION_COMPLETE = 90
    PROCESSING_COMPLETE = 100

    # Intermediate milestones
    BATCH_START = 10
    BATCH_PROCESSING = 30
    BATCH_VALIDATION = 70

    @classmethod
    def get_milestone_name(cls, progress: int) -> str:
        """Get human-readable name for progress milestone."""
        milestones = {
            cls.SEARCH_COMPLETE: "Search Complete",
            cls.METADATA_EXTRACTION: "Metadata Extraction",
            cls.DEDUPLICATION_COMPLETE: "Deduplication Complete",
            cls.PROCESSING_COMPLETE: "Processing Complete",
            cls.BATCH_START: "Batch Processing Started",
            cls.BATCH_PROCESSING: "Batch Processing",
            cls.BATCH_VALIDATION: "Batch Validation",
        }
        return milestones.get(progress, f"Processing ({progress}%)")


def ensure_valid_counts(processed: int, total: int) -> Tuple[int, int]:
    """
    Ensure total_count is at least as large as processed_count.

    This prevents logical inconsistencies where processed items exceed total items,
    which can happen during batch processing or when counts are updated asynchronously.

    Args:
        processed: Number of items processed
        total: Total number of items expected

    Returns:
        Tuple of (processed, total) with total guaranteed >= processed
    """
    if processed < 0:
        logger.warning(f"Negative processed count {processed}, setting to 0")
        processed = 0

    if total < 0:
        logger.warning(f"Negative total count {total}, setting to 0")
        total = 0

    if processed > total:
        logger.debug(
            f"Processed count {processed} exceeds total {total}, "
            f"adjusting total to match processed"
        )
        total = processed

    return processed, total


def calculate_progress_percentage(processed: int, total: int) -> int:
    """
    Calculate progress percentage with safe division.

    Args:
        processed: Number of items processed
        total: Total number of items

    Returns:
        Progress percentage (0-100)
    """
    if total <= 0:
        return 0 if processed == 0 else 100

    percentage = min(100, int((processed / total) * 100))
    return max(0, percentage)


def validate_progress_update(
    processed_count: int, total_count: int, overall_progress: int
) -> Dict[str, Any]:
    """
    Validate and normalize progress update data.

    Args:
        processed_count: Number of items processed
        total_count: Total number of items
        overall_progress: Overall progress percentage

    Returns:
        Dictionary with validated progress data
    """
    # Ensure counts are valid
    processed_count, total_count = ensure_valid_counts(processed_count, total_count)

    # Validate overall progress
    if overall_progress < 0:
        logger.warning(f"Negative overall progress {overall_progress}, setting to 0")
        overall_progress = 0
    elif overall_progress > 100:
        logger.warning(f"Overall progress {overall_progress} > 100, capping at 100")
        overall_progress = 100

    # Calculate expected progress based on counts
    expected_progress = calculate_progress_percentage(processed_count, total_count)

    # Log significant discrepancies
    if abs(overall_progress - expected_progress) > 10:
        logger.info(
            f"Progress discrepancy: overall={overall_progress}%, "
            f"expected={expected_progress}% based on {processed_count}/{total_count}"
        )

    return {
        "processed_count": processed_count,
        "total_count": total_count,
        "overall_progress": overall_progress,
        "calculated_progress": expected_progress,
        "is_complete": processed_count >= total_count and total_count > 0,
    }


def get_batch_progress(
    batch_number: int,
    total_batches: int,
    items_in_batch: int,
    items_processed_in_batch: int,
) -> Dict[str, Any]:
    """
    Calculate progress for batch processing operations.

    Args:
        batch_number: Current batch number (1-based)
        total_batches: Total number of batches
        items_in_batch: Number of items in current batch
        items_processed_in_batch: Items processed in current batch

    Returns:
        Dictionary with batch progress information
    """
    if total_batches <= 0:
        return {
            "batch_progress": 0,
            "overall_batch_progress": 0,
            "description": "No batches to process",
        }

    # Calculate batch-level progress
    batch_progress = calculate_progress_percentage(
        items_processed_in_batch, items_in_batch
    )

    # Calculate overall progress across all batches
    completed_batches = max(0, batch_number - 1)
    overall_batch_progress = calculate_progress_percentage(
        completed_batches, total_batches
    )

    # If current batch is complete, include it
    if batch_progress == 100:
        overall_batch_progress = calculate_progress_percentage(
            batch_number, total_batches
        )

    return {
        "batch_number": batch_number,
        "total_batches": total_batches,
        "batch_progress": batch_progress,
        "overall_batch_progress": overall_batch_progress,
        "description": f"Batch {batch_number}/{total_batches} - {batch_progress}% complete",
    }
