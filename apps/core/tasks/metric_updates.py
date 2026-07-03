"""
Celery tasks for periodic metric updates.

These tasks update gauge metrics that require database queries,
such as current session state distribution and review velocity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from celery import shared_task

from apps.core.metrics.review_metrics import update_review_velocity
from apps.core.metrics.session_metrics import update_session_state_distribution

if TYPE_CHECKING:
    from celery import Task

logger = structlog.get_logger(__name__)


@shared_task(
    name="apps.core.tasks.update_session_metrics",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def update_session_metrics_task(self: Task) -> None:
    """
    Update session-related gauge metrics.

    This task runs every 120 seconds to update:
    - Session state distribution (agent_grey_session_state)

    Scheduled in celery.py beat_schedule.

    Args:
        self (Task): Celery task instance (injected by bind=True).

    Returns:
        None

    Raises:
        Exception: Retried up to 3 times with 60s delay between attempts.

    Example:
        >>> update_session_metrics_task.delay()
        <AsyncResult: task_id>
    """
    try:
        logger.info("session_metrics_update_started")

        update_session_state_distribution()

        logger.info("session_metrics_update_completed")

    except Exception as e:
        logger.error(
            "session_metrics_update_failed",
            error=str(e),
            exc_info=True,
        )
        raise self.retry(exc=e)


@shared_task(
    name="apps.core.tasks.update_review_metrics",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def update_review_metrics_task(self: Task) -> None:
    """
    Update review-related gauge metrics.

    This task runs every 300 seconds (5 minutes) to update:
    - Review velocity (agent_grey_review_velocity_per_hour)

    Scheduled in celery.py beat_schedule.

    Args:
        self (Task): Celery task instance (injected by bind=True).

    Returns:
        None

    Raises:
        Exception: Retried up to 3 times with 60s delay between attempts.

    Example:
        >>> update_review_metrics_task.delay()
        <AsyncResult: task_id>
    """
    try:
        logger.info("review_metrics_update_started")

        update_review_velocity()

        logger.info("review_metrics_update_completed")

    except Exception as e:
        logger.error(
            "review_metrics_update_failed",
            error=str(e),
            exc_info=True,
        )
        raise self.retry(exc=e)
