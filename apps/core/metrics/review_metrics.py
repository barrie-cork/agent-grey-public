"""
Review decision metrics instrumentation.
"""

from __future__ import annotations

import structlog

from apps.core.metrics.enums import ReviewDecision
from apps.core.metrics.registry import review_decisions_total, review_velocity_per_hour

logger = structlog.get_logger(__name__)


def record_review_decision(decision_type: ReviewDecision) -> None:
    """
    Record a review decision.

    Args:
        decision_type (ReviewDecision): Review decision enum value.

    Returns:
        None

    Raises:
        Exception: Logged but not raised (fail-safe).

    Example:
        >>> record_review_decision(ReviewDecision.INCLUDE)
    """
    try:
        review_decisions_total.labels(decision=decision_type.value).inc()

        logger.info(
            "review_decision_recorded",
            decision=decision_type,
        )
    except Exception as e:
        logger.error(
            "review_decision_recording_failed",
            decision=decision_type,
            error=str(e),
        )


def update_review_velocity() -> None:
    """
    Calculate and update review velocity (decisions per hour).

    This should be called periodically by monitoring task.

    Returns:
        None

    Raises:
        Exception: Logged but not raised (fail-safe).

    Example:
        >>> update_review_velocity()
        >>> # Updates Prometheus gauge with decisions per hour
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.review_results.models import SimpleReviewDecision

    try:
        # Calculate decisions in last hour
        one_hour_ago = timezone.now() - timedelta(hours=1)
        decisions_last_hour = SimpleReviewDecision.objects.filter(
            reviewed_at__gte=one_hour_ago
        ).count()

        review_velocity_per_hour.set(decisions_last_hour)

        logger.debug(
            "review_velocity_updated",
            decisions_per_hour=decisions_last_hour,
        )
    except Exception as e:
        logger.error(
            "review_velocity_update_failed",
            error=str(e),
        )
