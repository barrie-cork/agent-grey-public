"""
Helper functions for SERP execution tasks.
Shared utilities used across monitoring and execution tasks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.core.mail import send_mail

if TYPE_CHECKING:
    from apps.review_manager.models import SearchSession
    from apps.serp_execution.models import SearchExecution

logger = logging.getLogger(__name__)


def _should_retry_execution(exception: Exception) -> bool:
    """
    Determine if an execution error should trigger a retry.

    Args:
        exception: The exception that occurred

    Returns:
        bool: True if the task should be retried
    """
    # Retry on transient network/connection errors
    retryable_errors = (
        ConnectionError,
        TimeoutError,
        OSError,  # Can include network-related OS errors
    )

    # Check if it's a retryable error type
    if isinstance(exception, retryable_errors):
        return True

    # Check for specific error messages that indicate transient issues
    error_message = str(exception).lower()
    transient_indicators = [
        "connection reset",
        "connection refused",
        "timeout",
        "temporarily unavailable",
        "too many requests",  # Rate limiting
        "service unavailable",
    ]

    return any(indicator in error_message for indicator in transient_indicators)


def _send_execution_notification(execution: "SearchExecution", message: str) -> None:
    """
    Send notification about execution issue.

    Args:
        execution: SearchExecution instance
        message: Notification message
    """
    from django.conf import settings
    from django.core.mail import send_mail

    if execution.initiated_by and execution.initiated_by.email:
        subject = f"Agent Grey - Search Execution Alert - {execution.query.strategy.session.title}"

        full_message = f"""
        {message}

        Execution Details:
        - Query: {execution.query.query_text[:100]}...
        - Status: {execution.status}
        - Attempts: {execution.retry_count + 1}
        - Error: {execution.error_message}

        You can view more details in the execution status page.
        """

        try:
            send_mail(
                subject,
                full_message,
                settings.DEFAULT_FROM_EMAIL,
                [execution.initiated_by.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send notification email: {str(e)}")


def _send_session_notification(
    session: "SearchSession",
    message: str,
    subject_prefix: str = "Search Session Update",
) -> bool:
    """
    Send notification about session status.

    Args:
        session: SearchSession instance
        message: Notification message
        subject_prefix: Prefix for the email subject

    Returns:
        True if notification sent successfully, False otherwise
    """
    try:
        if not session.owner.email:
            logger.warning(
                f"Cannot send notification - no email for user {session.owner.id}"
            )
            return False

        subject = f"{subject_prefix}: {session.title}"

        # Send email notification
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[session.owner.email],
            fail_silently=True,
        )

        logger.info(
            f"Sent notification for session {session.id} to {session.owner.email}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to send notification for session {session.id}: {str(e)}")
        return False


def format_progress_message(
    completed: int, total: int, failed: Optional[int] = None
) -> str:
    """
    Format a progress message for display.

    Args:
        completed: Number of completed items
        total: Total number of items
        failed: Optional number of failed items

    Returns:
        Formatted progress message
    """
    percentage = (completed / total * 100) if total > 0 else 0

    message = f"{completed}/{total} ({percentage:.1f}%)"

    if failed is not None and failed > 0:
        message += f" - {failed} failed"

    return message


def calculate_estimated_completion_time(
    completed: int, total: int, elapsed_seconds: float
) -> Optional[float]:
    """
    Calculate estimated time to completion.

    Args:
        completed: Number of completed items
        total: Total number of items
        elapsed_seconds: Seconds elapsed so far

    Returns:
        Estimated seconds to completion, or None if cannot calculate
    """
    if completed == 0 or completed >= total:
        return None

    rate = completed / elapsed_seconds
    remaining = total - completed

    return remaining / rate


def should_send_alert(
    failed_count: int, total_count: int, threshold_percentage: float = 0.5
) -> bool:
    """
    Determine if an alert should be sent based on failure rate.

    Args:
        failed_count: Number of failures
        total_count: Total number of items
        threshold_percentage: Threshold percentage for alerting

    Returns:
        True if alert should be sent
    """
    if total_count == 0:
        return False

    failure_rate = failed_count / total_count
    return failure_rate >= threshold_percentage
