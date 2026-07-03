"""
Alert rule definitions and threshold management.

This module defines the rules and thresholds for different types of alerts
in the workflow monitoring system.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class AlertRules:
    """
    Alert rule definitions and threshold checks.

    Manages configurable thresholds for different alert types and provides
    methods to check conditions against these thresholds.
    """

    def __init__(self):
        """Initialize alert rules with default thresholds."""
        self.alert_thresholds = {
            "stuck_sessions": 5,  # Alert if >5 sessions stuck
            "error_rate": 0.10,  # Alert if error rate >10%
            "processing_time": 300,  # Alert if avg processing >5 minutes
            "failed_transitions": 10,  # Alert if >10 failed transitions in 1 hour
            "slow_transition_rate": 0.20,  # Alert if >20% transitions are slow
        }

    def check_stuck_sessions(self) -> Optional[Dict[str, Any]]:
        """
        Check for stuck sessions.

        Returns:
            Alert dict if threshold exceeded, None otherwise
        """
        try:
            from apps.review_manager.models import SearchSession

            threshold = timezone.now() - timedelta(minutes=30)

            stuck_sessions = SearchSession.objects.filter(
                Q(status="executing", updated_at__lt=threshold)
                | Q(status="processing_results", updated_at__lt=threshold)
            ).select_related("owner")

            stuck_count = stuck_sessions.count()

            if stuck_count > self.alert_thresholds["stuck_sessions"]:
                # Get details for alert
                session_details = []
                for session in stuck_sessions[:10]:  # Limit to first 10
                    time_stuck = timezone.now() - session.updated_at
                    session_details.append(
                        {
                            "id": str(session.id),
                            "title": session.title,
                            "status": session.status,
                            "owner": (
                                session.owner.email if session.owner else "Unknown"
                            ),
                            "stuck_duration": str(time_stuck),
                        }
                    )

                return {
                    "type": "stuck_sessions",
                    "severity": "high",
                    "message": (
                        f"{stuck_count} sessions are stuck "
                        f"(threshold: {self.alert_thresholds['stuck_sessions']})"
                    ),
                    "count": stuck_count,
                    "details": session_details,
                    "timestamp": timezone.now().isoformat(),
                }

            return None

        except Exception as e:
            logger.error(f"Error checking stuck sessions: {str(e)}")
            return None

    def check_error_rate(self, metrics_collector) -> Optional[Dict[str, Any]]:
        """
        Check system error rate.

        Args:
            metrics_collector: TransitionMetrics instance for getting statistics

        Returns:
            Alert dict if threshold exceeded, None otherwise
        """
        try:
            stats = metrics_collector.get_transition_stats(time_window_hours=1)
            cached_metrics = stats.get("cached_metrics", {})

            total_transitions = 0
            total_failures = 0

            for metric in cached_metrics.values():
                total_transitions += metric.get("count", 0)
                total_failures += metric.get("failure_count", 0)

            if total_transitions > 0:
                error_rate = total_failures / total_transitions

                if error_rate > self.alert_thresholds["error_rate"]:
                    return {
                        "type": "high_error_rate",
                        "severity": "critical",
                        "message": (
                            f"Error rate is {error_rate:.1%} "
                            f"(threshold: {self.alert_thresholds['error_rate']:.0%})"
                        ),
                        "rate": error_rate,
                        "total_transitions": total_transitions,
                        "total_failures": total_failures,
                        "timestamp": timezone.now().isoformat(),
                    }

            return None

        except Exception as e:
            logger.error(f"Error checking error rate: {str(e)}")
            return None

    def check_processing_time(self) -> Optional[Dict[str, Any]]:
        """
        Check average processing time.

        Returns:
            Alert dict if threshold exceeded, None otherwise
        """
        try:
            from apps.results_manager.models import ProcessingSession

            # Check recent processing sessions
            recent_sessions = ProcessingSession.objects.filter(
                status="completed",
                completed_at__isnull=False,
                created_at__gte=timezone.now() - timedelta(hours=1),
            )

            if recent_sessions.exists():
                total_time = 0
                count = 0

                for session in recent_sessions:
                    if session.completed_at and session.created_at:
                        duration = (
                            session.completed_at - session.created_at
                        ).total_seconds()
                        total_time += duration
                        count += 1

                if count > 0:
                    avg_time = total_time / count

                    if avg_time > self.alert_thresholds["processing_time"]:
                        return {
                            "type": "slow_processing",
                            "severity": "medium",
                            "message": (
                                f"Average processing time is {avg_time:.1f}s "
                                f"(threshold: {self.alert_thresholds['processing_time']}s)"
                            ),
                            "avg_processing_time": avg_time,
                            "sessions_checked": count,
                            "timestamp": timezone.now().isoformat(),
                        }

            return None

        except Exception as e:
            logger.error(f"Error checking processing time: {str(e)}")
            return None

    def check_transition_failures(self) -> Optional[Dict[str, Any]]:
        """
        Check for high transition failure rate.

        Returns:
            Alert dict if threshold exceeded, None otherwise
        """
        try:
            from apps.review_manager.models import SessionActivity

            # Check recent transition failures
            one_hour_ago = timezone.now() - timedelta(hours=1)

            failed_transitions = SessionActivity.objects.filter(
                activity_type="transition_failed", created_at__gte=one_hour_ago
            ).count()

            if failed_transitions > self.alert_thresholds["failed_transitions"]:
                # Get failure details
                recent_failures = SessionActivity.objects.filter(
                    activity_type="transition_failed", created_at__gte=one_hour_ago
                ).order_by("-created_at")[:5]

                failure_details = []
                for failure in recent_failures:
                    failure_details.append(
                        {
                            "session_id": str(failure.session_id),
                            "error": (
                                failure.metadata.get("error", "Unknown")
                                if failure.metadata
                                else "Unknown"
                            ),
                            "timestamp": failure.created_at.isoformat(),
                        }
                    )

                return {
                    "type": "high_failure_rate",
                    "severity": "high",
                    "message": (
                        f"{failed_transitions} transition failures in last hour "
                        f"(threshold: {self.alert_thresholds['failed_transitions']})"
                    ),
                    "failure_count": failed_transitions,
                    "recent_failures": failure_details,
                    "timestamp": timezone.now().isoformat(),
                }

            return None

        except Exception as e:
            logger.error(f"Error checking transition failures: {str(e)}")
            return None

    def update_threshold(self, alert_type: str, new_value: Any) -> bool:
        """
        Update an alert threshold.

        Args:
            alert_type: Type of alert
            new_value: New threshold value

        Returns:
            True if updated successfully
        """
        if alert_type in self.alert_thresholds:
            self.alert_thresholds[alert_type] = new_value
            logger.info(f"Updated {alert_type} threshold to {new_value}")
            return True

        logger.warning(f"Unknown alert type: {alert_type}")
        return False

    def get_configuration(self) -> Dict[str, Any]:
        """
        Get current alert rule configuration.

        Returns:
            Dictionary with alert thresholds
        """
        return {"thresholds": self.alert_thresholds.copy()}
