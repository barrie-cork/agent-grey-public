"""
Activity-based monitoring service for optimising session monitoring intervals.

This service provides intelligent monitoring intervals based on session states
and recent activity to reduce resource usage while maintaining system responsiveness.
Implements the adaptive batching strategy from the monitoring optimisation PRP.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class SessionActivityDetector:
    """Intelligent activity-based monitoring intervals with adaptive behaviour"""

    # Session state categories for monitoring strategy
    ACTIVE_STATES = ["executing", "processing_results"]
    REVIEW_STATES = ["under_review", "ready_for_review"]
    DORMANT_STATES = ["completed", "archived"]
    SETUP_STATES = ["draft", "defining_search", "ready_to_execute"]

    # Base monitoring intervals in seconds
    MONITORING_INTERVALS: Dict[str, int | None] = {
        # Active processing states need frequent monitoring
        "executing": 30,  # 30 seconds - critical phase
        "processing_results": 30,  # 30 seconds - critical phase
        # Review states need adaptive monitoring based on recent activity
        "ready_for_review": 300,  # 5 minutes - base interval
        "under_review": 300,  # 5 minutes - base interval (adaptive)
        # Dormant states need minimal or no monitoring
        "completed": None,  # No monitoring - dormant state
        "archived": None,  # No monitoring - dormant state
        # Setup states need moderate monitoring
        "draft": 300,  # 5 minutes - initial state
        "defining_search": 300,  # 5 minutes - configuration phase
        "ready_to_execute": 300,  # 5 minutes - pre-execution
    }

    # Adaptive intervals for review sessions based on recent activity
    REVIEW_ACTIVITY_INTERVALS = {
        "recent": 300,  # 5 minutes - active within 2 hours
        "moderate": 1800,  # 30 minutes - active within 24 hours
        "low": 3600,  # 1 hour - low activity
    }

    @classmethod
    def get_monitoring_interval(cls, session, last_activity=None) -> Optional[int]:
        """
        Return monitoring interval in seconds based on session status and activity.

        Args:
            session: SearchSession object or status string
            last_activity: Optional datetime of last activity

        Returns:
            Monitoring interval in seconds, or None for no monitoring
        """
        # Handle both session objects and status strings
        if isinstance(session, str):
            session_status = session
        else:
            session_status = session.status

        # Get base interval for this status
        base_interval = cls.MONITORING_INTERVALS.get(session_status, 300)

        # Dormant states don't need monitoring
        if base_interval is None:
            logger.debug(
                f"Session status '{session_status}' -> no monitoring (dormant)"
            )
            return None

        # Active states use base interval (high frequency)
        if session_status in cls.ACTIVE_STATES:
            logger.debug(
                f"Session status '{session_status}' -> {base_interval}s (active)"
            )
            return base_interval

        # Review states use adaptive intervals based on activity
        if session_status in cls.REVIEW_STATES:
            interval = cls._get_adaptive_review_interval(session, last_activity)
            logger.debug(
                f"Session status '{session_status}' -> {interval}s (adaptive review)"
            )
            return interval

        # Default to base interval for setup states
        logger.debug(f"Session status '{session_status}' -> {base_interval}s (default)")
        return base_interval

    @classmethod
    def _get_adaptive_review_interval(cls, session, last_activity=None) -> int:
        """
        Calculate adaptive monitoring interval for review sessions.

        Args:
            session: SearchSession object
            last_activity: Optional datetime of last activity

        Returns:
            Adaptive monitoring interval in seconds
        """
        if last_activity is None:
            # Query last activity from database if not provided
            last_activity = cls._get_last_activity(session)

        if last_activity is None:
            # No activity recorded, use low-frequency monitoring
            return cls.REVIEW_ACTIVITY_INTERVALS["low"]

        # Calculate time since last activity
        time_since_activity = timezone.now() - last_activity

        # Determine monitoring frequency based on recent activity
        if time_since_activity < timedelta(hours=2):
            return cls.REVIEW_ACTIVITY_INTERVALS["recent"]
        elif time_since_activity < timedelta(days=1):
            return cls.REVIEW_ACTIVITY_INTERVALS["moderate"]
        else:
            return cls.REVIEW_ACTIVITY_INTERVALS["low"]

    @classmethod
    def _get_last_activity(cls, session) -> Optional[timezone.datetime]:
        """
        Get timestamp of last activity for a session.

        Args:
            session: SearchSession object

        Returns:
            Datetime of last activity or None
        """
        try:
            # Import here to avoid circular dependencies
            from apps.review_manager.models import SessionActivity

            # Get most recent activity
            last_activity = (
                SessionActivity.objects.filter(session=session)
                .order_by("-created_at")
                .values_list("created_at", flat=True)
                .first()
            )

            return last_activity

        except Exception as e:
            logger.warning(f"Could not retrieve last activity: {e}")
            return None

    @classmethod
    def should_monitor_session(cls, session, last_activity=None) -> bool:
        """
        Determine if a session should be monitored based on time elapsed.

        Args:
            session: SearchSession object
            last_activity: Optional datetime of last activity

        Returns:
            True if session should be monitored, False otherwise
        """
        session_id = str(session.id)
        cache_key = f"last_monitor:{session_id}"
        last_monitor = cache.get(cache_key)

        # Get monitoring interval (may return None for dormant states)
        interval = cls.get_monitoring_interval(session, last_activity)

        # Don't monitor dormant sessions
        if interval is None:
            logger.debug(
                f"Session {session_id} ({session.status}): no monitoring needed"
            )
            return False

        # Monitor if never monitored before
        if last_monitor is None:
            logger.debug(f"Session {session_id} ({session.status}): first monitor")
            return True

        # Check if interval has elapsed
        elapsed = (timezone.now() - last_monitor).total_seconds()
        should_monitor = elapsed >= interval

        if should_monitor:
            logger.debug(
                f"Session {session_id} ({session.status}): "
                f"elapsed {elapsed:.0f}s >= {interval}s interval"
            )

        return should_monitor

    @classmethod
    def update_last_monitored(cls, session, last_activity=None) -> None:
        """
        Update the last monitored timestamp for a session.

        Args:
            session: SearchSession object
            last_activity: Optional datetime of last activity
        """
        session_id = str(session.id)
        cache_key = f"last_monitor:{session_id}"
        interval = cls.get_monitoring_interval(session, last_activity)

        # Don't cache for dormant sessions
        if interval is None:
            return

        # Set cache timeout to 2x the interval to handle cleanup
        timeout = interval * 2

        cache.set(cache_key, timezone.now(), timeout=timeout)

        logger.debug(
            f"Updated monitoring timestamp for session {session_id} "
            f"(next check in {interval}s)"
        )

    @classmethod
    def get_session_statistics(cls) -> Dict[str, Any]:
        """
        Get statistics about monitoring intervals by session status.

        Returns:
            Dictionary with session status counts and intervals
        """
        stats = {}

        # Add intervals for each status
        for status, interval in cls.MONITORING_INTERVALS.items():
            stats[f"{status}_interval"] = (
                interval if interval is not None else "no_monitoring"
            )

        # Calculate min/max excluding None values
        active_intervals = [
            i for i in cls.MONITORING_INTERVALS.values() if i is not None
        ]

        stats["total_statuses"] = len(cls.MONITORING_INTERVALS)
        stats["active_monitoring_statuses"] = len(active_intervals)
        stats["dormant_statuses"] = len(cls.MONITORING_INTERVALS) - len(
            active_intervals
        )
        stats["min_interval"] = min(active_intervals) if active_intervals else None
        stats["max_interval"] = max(active_intervals) if active_intervals else None

        # Add state categories
        stats["active_states"] = cls.ACTIVE_STATES
        stats["review_states"] = cls.REVIEW_STATES
        stats["dormant_states"] = cls.DORMANT_STATES
        stats["setup_states"] = cls.SETUP_STATES

        return stats

    @classmethod
    def health_check(cls) -> Dict[str, Any]:
        """
        Perform health check on the activity detector.

        Returns:
            Dictionary with health status and metrics
        """
        try:
            # Test cache connectivity
            test_key = "activity_detector_health_check"
            cache.set(test_key, True, timeout=60)
            cache_working = cache.get(test_key) is True
            cache.delete(test_key)

            stats = cls.get_session_statistics()

            return {
                "healthy": cache_working,
                "cache_working": cache_working,
                "total_statuses_configured": stats["total_statuses"],
                "active_monitoring_statuses": stats["active_monitoring_statuses"],
                "dormant_statuses": stats["dormant_statuses"],
                "min_interval_seconds": stats["min_interval"],
                "max_interval_seconds": stats["max_interval"],
                "adaptive_monitoring_enabled": True,
                "timestamp": timezone.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Activity detector health check failed: {e}")

            return {
                "healthy": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": timezone.now().isoformat(),
            }


# Backwards compatibility alias
SimpleSessionActivityDetector = SessionActivityDetector
