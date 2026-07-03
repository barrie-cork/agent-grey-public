"""
Session workflow metrics instrumentation.

Provides functions to track session state transitions, durations,
and current state distribution across the Agent Grey workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import structlog
from django.db import models
from django.utils import timezone

from apps.core.metrics.registry import (
    session_state_duration_seconds,
    session_state_gauge,
    session_transitions_total,
)

if TYPE_CHECKING:
    from apps.review_manager.models import SearchSession

logger = structlog.get_logger(__name__)


def update_session_state_distribution() -> None:
    """
    Update the session_state_gauge with current session counts by state.

    This should be called:
    - Periodically by monitoring task (every 120s)
    - After each state transition

    Query is optimised with values() to avoid loading full objects.

    Returns:
        None

    Raises:
        Exception: Logged but not raised (fail-safe).

    Example:
        >>> update_session_state_distribution()
        >>> # Updates Prometheus gauge with current session counts
    """
    from apps.review_manager.models import SearchSession

    try:
        # Get count per state
        state_counts = SearchSession.objects.values("status").annotate(
            count=models.Count("id")
        )

        # Update gauge for each state
        for state_data in state_counts:
            state = state_data["status"]
            count = state_data["count"]
            session_state_gauge.labels(state=state).set(count)

        logger.debug(
            "session_state_distribution_updated",
            state_counts={s["status"]: s["count"] for s in state_counts},
        )

    except Exception as e:
        logger.error(
            "session_state_distribution_update_failed",
            error=str(e),
            exc_info=True,
        )


def record_session_transition(
    session: SearchSession,
    from_state: str,
    to_state: str,
    success: bool = True,
    duration_seconds: Optional[float] = None,
) -> None:
    """
    Record a session state transition event.

    This function is called from:
    - SearchSession.save() when status changes
    - Celery tasks after state transitions

    Args:
        session (SearchSession): SearchSession model instance.
        from_state (str): Previous state.
        to_state (str): New state.
        success (bool): Whether transition succeeded. Defaults to True.
        duration_seconds (Optional[float]): Time spent in from_state in seconds.

    Returns:
        None

    Raises:
        Exception: Logged but not raised (fail-safe).

    Example:
        >>> record_session_transition(session, 'executing', 'completed', success=True, duration_seconds=120.5)
    """
    try:
        # Record transition counter
        session_transitions_total.labels(
            from_state=from_state,
            to_state=to_state,
            success="true" if success else "false",
        ).inc()

        # Record duration if provided
        if duration_seconds is not None:
            session_state_duration_seconds.labels(state=from_state).observe(
                duration_seconds
            )

        # Update state distribution
        update_session_state_distribution()

        logger.info(
            "session_transition_recorded",
            session_id=str(session.id),
            from_state=from_state,
            to_state=to_state,
            success=success,
            duration_seconds=duration_seconds,
        )

    except Exception as e:
        logger.error(
            "session_transition_recording_failed",
            session_id=str(session.id),
            from_state=from_state,
            to_state=to_state,
            error=str(e),
            exc_info=True,
        )


def calculate_state_duration(
    session: SearchSession, from_state: str
) -> Optional[float]:
    """
    Calculate how long session spent in a specific state.

    Args:
        session (SearchSession): SearchSession model instance.
        from_state (str): State to calculate duration for.

    Returns:
        Optional[float]: Duration in seconds, or None if cannot be calculated.

    Example:
        >>> duration = calculate_state_duration(session, 'executing')
        >>> print(f"Session was executing for {duration} seconds")
    """
    from apps.review_manager.models import SessionActivity

    try:
        # Find most recent activity for this state
        last_activity = (
            SessionActivity.objects.filter(
                session=session,
                activity_type="state_change",
                metadata__to_state=from_state,
            )
            .order_by("-created_at")
            .first()
        )

        if last_activity:
            duration = (timezone.now() - last_activity.created_at).total_seconds()
            return duration

        # Fallback: use session creation time for 'draft' state
        if from_state == "draft" and session.created_at:
            duration = (timezone.now() - session.created_at).total_seconds()
            return duration

        return None

    except Exception as e:
        logger.warning(
            "state_duration_calculation_failed",
            session_id=str(session.id),
            from_state=from_state,
            error=str(e),
        )
        return None
