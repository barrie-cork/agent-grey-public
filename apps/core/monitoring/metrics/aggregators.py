"""
Metric aggregation and statistics retrieval.

This module provides functions for aggregating metrics and generating
statistics for monitoring dashboards and reports.
"""

import logging
from typing import Any, Dict

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_transition_stats(time_window_hours: int = 24) -> Dict[str, Any]:
    """
    Get transition statistics for monitoring dashboard.

    Args:
        time_window_hours: Time window for statistics

    Returns:
        Dictionary with transition statistics
    """
    try:
        from apps.review_manager.models import SessionActivity

        # Get recent transitions from database
        cutoff_time = timezone.now() - timezone.timedelta(hours=time_window_hours)

        recent_activities = SessionActivity.objects.filter(
            activity_type="status_changed", created_at__gte=cutoff_time
        ).select_related("session")

        # Calculate statistics
        total_transitions = recent_activities.count()

        # Get counts by transition type
        transition_counts = {}
        for activity in recent_activities:
            if activity.metadata:
                old_status = activity.metadata.get("old_status")
                new_status = activity.metadata.get("new_status")
                if old_status and new_status:
                    key = f"{old_status}_to_{new_status}"
                    transition_counts[key] = transition_counts.get(key, 0) + 1

        # Get cached metrics
        cached_stats = get_cached_stats()

        # Get stuck sessions
        stuck_sessions = count_stuck_sessions()

        # Get recent failures
        recent_failures = cache.get("metrics:transitions:recent_failures", [])

        return {
            "total_transitions": total_transitions,
            "transition_counts": transition_counts,
            "cached_metrics": cached_stats,
            "stuck_sessions": stuck_sessions,
            "recent_failures": recent_failures[-10:],  # Last 10 failures
            "time_window_hours": time_window_hours,
            "timestamp": timezone.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get transition stats: {str(e)}")
        return {"error": str(e), "timestamp": timezone.now().isoformat()}


def get_cached_stats() -> Dict[str, Any]:
    """
    Get all cached statistics.

    Returns:
        Dictionary with cached metrics
    """
    stats = {}

    try:
        # Common transitions to check
        transitions = [
            ("draft", "defining_search"),
            ("defining_search", "ready_to_execute"),
            ("ready_to_execute", "executing"),
            ("executing", "processing_results"),
            ("processing_results", "ready_for_review"),
            ("ready_for_review", "under_review"),
            ("under_review", "completed"),
        ]

        for from_state, to_state in transitions:
            key = f"{from_state}_to_{to_state}"
            agg_key = f"metrics:aggregates:{key}"

            aggregates = cache.get(agg_key)
            if aggregates:
                stats[key] = aggregates

    except Exception as e:
        logger.warning(f"Failed to get cached stats: {str(e)}")

    return stats


def count_stuck_sessions() -> int:
    """
    Count currently stuck sessions.

    Returns:
        Number of stuck sessions
    """
    try:
        from apps.review_manager.models import SearchSession

        threshold = timezone.now() - timezone.timedelta(minutes=30)

        stuck_count = SearchSession.objects.filter(
            Q(status="executing", updated_at__lt=threshold)
            | Q(status="processing_results", updated_at__lt=threshold)
        ).count()

        return stuck_count

    except Exception as e:
        logger.warning(f"Failed to count stuck sessions: {str(e)}")
        return 0


def get_performance_summary() -> Dict[str, Any]:
    """
    Get performance summary for monitoring.

    Returns:
        Performance metrics summary
    """
    try:
        summary = {
            "transition_performance": {},
            "slow_transitions": [],
            "health_indicators": {},
        }

        # Get performance for each transition type
        cached_stats = get_cached_stats()

        for transition, stats in cached_stats.items():
            if stats.get("avg_duration"):
                summary["transition_performance"][transition] = {
                    "avg_duration_ms": stats["avg_duration"],
                    "max_duration_ms": stats.get("max_duration", 0),
                    "min_duration_ms": stats.get("min_duration", 0),
                    "slow_percentage": (
                        stats.get("slow_count", 0) / max(stats.get("count", 1), 1)
                    )
                    * 100,
                }

        # Identify slow transitions
        for transition, perf in summary["transition_performance"].items():
            if perf["avg_duration_ms"] > 1000:
                summary["slow_transitions"].append(
                    {
                        "transition": transition,
                        "avg_duration_ms": perf["avg_duration_ms"],
                    }
                )

        # Calculate health indicators
        total_transitions = sum(s.get("count", 0) for s in cached_stats.values())
        total_failures = sum(s.get("failure_count", 0) for s in cached_stats.values())

        if total_transitions > 0:
            summary["health_indicators"]["overall_success_rate"] = (
                (total_transitions - total_failures) / total_transitions
            ) * 100
        else:
            summary["health_indicators"]["overall_success_rate"] = 100

        summary["health_indicators"]["stuck_sessions"] = count_stuck_sessions()

        return summary

    except Exception as e:
        logger.error(f"Failed to get performance summary: {str(e)}")
        return {"error": str(e), "timestamp": timezone.now().isoformat()}


def send_to_monitoring_service(stats: Dict[str, Any]) -> None:
    """
    Send metrics to external monitoring service.

    Args:
        stats: Metrics to send
    """
    try:
        # This is a placeholder for integration with external monitoring
        # In production, this would send to Datadog, New Relic, etc.

        import time

        import requests
        from django.conf import settings

        if hasattr(settings, "MONITORING_ENDPOINT"):
            requests.post(
                settings.MONITORING_ENDPOINT,
                json={
                    "namespace": "agent_grey.workflow",
                    "metrics": stats,
                    "timestamp": time.time(),
                },
                timeout=5,
            )

    except Exception as e:
        # Don't let monitoring failures break the application
        logger.warning(f"Failed to send metrics to monitoring service: {str(e)}")
