"""
Validation module for results_manager app.

This module contains validation functions extracted from tasks to improve
code organization and follow single responsibility principle.
"""

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from apps.review_manager.models import SearchSession

if TYPE_CHECKING:
    from apps.results_manager.models import ProcessingSession

logger = logging.getLogger(__name__)


def validate_session_for_processing(session: SearchSession) -> None:
    """
    Validate session is ready for processing.

    Args:
        session: SearchSession instance to validate

    Raises:
        ValueError: If session is not in correct state or missing required data
    """
    logger.debug(f"Validating session {session.id} for processing")

    # Check session status - allow both processing_results and ready_for_review
    # ready_for_review may happen if processing completed very quickly
    valid_statuses = ["processing_results", "ready_for_review"]
    if session.status not in valid_statuses:
        logger.error(
            f"Session {session.id} validation failed: incorrect status. "
            f"Expected one of {valid_statuses}, Got: {session.status}"
        )
        raise ValueError(
            f"Session not in valid processing status: {session.status}. "
            f"Expected one of: {valid_statuses}"
        )

    # Check for search strategy
    if not hasattr(session, "search_strategy") or not session.search_strategy:
        logger.error(f"Session {session.id} validation failed: missing search strategy")
        raise ValueError(
            "Session missing search strategy. A search strategy must be "
            "defined before processing results."
        )

    # Check if there are raw results to process
    # Results are stored in serp_execution.RawSearchResult model
    from apps.serp_execution.models import RawSearchResult

    raw_results_count = RawSearchResult.objects.filter(
        execution__query__session=session
    ).count()

    # Issue #51 Fix: Allow zero results to proceed so _handle_no_results can process them
    # Zero results is a valid state - it means search found nothing matching criteria
    if raw_results_count == 0:
        logger.warning(
            f"Session {session.id} has zero raw results. "
            f"This is valid - proceeding to handle no results case."
        )
    else:
        logger.info(
            f"Session {session.id} has {raw_results_count} raw results to process"
        )

    logger.info(f"Session {session.id} validation successful")


def validate_session_id(session_id: str) -> None:
    """
    Validate session ID format.

    Args:
        session_id: Session ID string to validate

    Raises:
        ValueError: If session ID is invalid
    """
    if not session_id:
        logger.error("Session ID validation failed: empty session ID")
        raise ValueError("Session ID is required")

    # Proper UUID format validation
    try:
        UUID(session_id)
        logger.debug(f"Session ID {session_id} validation successful")
    except ValueError:
        logger.error(f"Session ID validation failed: invalid UUID format: {session_id}")
        raise ValueError(f"Invalid UUID format: {session_id}")


def get_or_create_processing_record(session: SearchSession) -> "ProcessingSession":
    """
    Get or create processing record for session.

    Args:
        session: SearchSession instance

    Returns:
        ProcessingSession instance
    """
    from .models import ProcessingSession

    record, created = ProcessingSession.objects.get_or_create(
        search_session=session, defaults={"status": "pending"}
    )

    if created:
        # Log new record creation
        logger.info(f"Created new ProcessingSession for session {session.id}")
    else:
        logger.debug(f"Found existing ProcessingSession for session {session.id}")

    return record


def validate_batch_processing_params(
    batch_size: int, start_index: int, total_results: int
) -> None:
    """
    Validate batch processing parameters.

    Args:
        batch_size: Size of batch to process
        start_index: Starting index for batch
        total_results: Total number of results

    Raises:
        ValueError: If parameters are invalid
    """
    logger.debug(
        f"Validating batch params: size={batch_size}, start={start_index}, total={total_results}"
    )

    if batch_size <= 0:
        logger.error(
            f"Batch processing validation failed: invalid batch size: {batch_size}"
        )
        raise ValueError(f"Batch size must be positive, got: {batch_size}")

    if start_index < 0:
        logger.error(
            f"Batch processing validation failed: negative start index: {start_index}"
        )
        raise ValueError(f"Start index must be non-negative, got: {start_index}")

    if total_results < 0:
        logger.error(
            f"Batch processing validation failed: negative total results: {total_results}"
        )
        raise ValueError(f"Total results must be non-negative, got: {total_results}")

    if start_index >= total_results and total_results > 0:
        logger.error(
            f"Batch processing validation failed: start index ({start_index}) >= "
            f"total results ({total_results})"
        )
        raise ValueError(
            f"Start index ({start_index}) must be less than total results ({total_results})"
        )

    logger.debug("Batch processing parameters validation successful")
