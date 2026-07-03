"""
Alert handling and management logic.

This module provides the main alert manager that coordinates rule checking,
alert suppression, and notification delivery.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .notifications import AlertNotificationService
from .rules import AlertRules

logger = logging.getLogger(__name__)


class WorkflowAlertManager:
    """
    Manage alerts for workflow issues.

    Features:
    - Coordinated alert checking using AlertRules
    - Alert suppression to prevent spam
    - Multi-channel notification delivery
    - Alert history tracking
    - Monitoring health checks
    """

    def __init__(self):
        """Initialize alert manager with rules and notification service."""
        self.alert_rules = AlertRules()
        self.notification_service = AlertNotificationService()

        # Alert suppression settings
        self.suppression_window = timedelta(
            hours=1
        )  # Don't repeat alerts within 1 hour
        self.alert_history = {}

        # Initialize metrics collector
        from apps.core.monitoring.metrics import TransitionMetrics

        self.metrics = TransitionMetrics()

    def check_and_alert(self) -> Dict[str, Any]:
        """
        Check system health and send alerts if needed.

        Returns:
            Dictionary with check results and alerts sent
        """
        alerts = []
        check_results = {
            "timestamp": timezone.now().isoformat(),
            "checks_performed": [],
            "alerts_triggered": [],
            "alerts_suppressed": [],
        }

        # Check stuck sessions
        stuck_alert = self.alert_rules.check_stuck_sessions()
        if stuck_alert:
            if self._should_send_alert("stuck_sessions", stuck_alert):
                alerts.append(stuck_alert)
                check_results["alerts_triggered"].append("stuck_sessions")
            else:
                check_results["alerts_suppressed"].append("stuck_sessions")
        check_results["checks_performed"].append("stuck_sessions")

        # Check error rate
        error_alert = self.alert_rules.check_error_rate(self.metrics)
        if error_alert:
            if self._should_send_alert("error_rate", error_alert):
                alerts.append(error_alert)
                check_results["alerts_triggered"].append("error_rate")
            else:
                check_results["alerts_suppressed"].append("error_rate")
        check_results["checks_performed"].append("error_rate")

        # Check processing time
        processing_alert = self.alert_rules.check_processing_time()
        if processing_alert:
            if self._should_send_alert("processing_time", processing_alert):
                alerts.append(processing_alert)
                check_results["alerts_triggered"].append("processing_time")
            else:
                check_results["alerts_suppressed"].append("processing_time")
        check_results["checks_performed"].append("processing_time")

        # Check transition failures
        transition_alert = self.alert_rules.check_transition_failures()
        if transition_alert:
            if self._should_send_alert("transition_failures", transition_alert):
                alerts.append(transition_alert)
                check_results["alerts_triggered"].append("transition_failures")
            else:
                check_results["alerts_suppressed"].append("transition_failures")
        check_results["checks_performed"].append("transition_failures")

        # Send alerts
        if alerts:
            self.notification_service.send_alerts(alerts)
            check_results["alerts_sent"] = len(alerts)
        else:
            check_results["alerts_sent"] = 0

        return check_results

    def send_high_failure_alert(self, failure_count: int) -> None:
        """
        Alert when failure rate is high.

        Args:
            failure_count: Number of failures detected
        """
        self.notification_service.send_high_failure_alert(failure_count)

    def _should_send_alert(self, alert_type: str, alert_data: Dict[str, Any]) -> bool:
        """
        Check if alert should be sent based on suppression rules.

        Args:
            alert_type: Type of alert
            alert_data: Alert data

        Returns:
            True if alert should be sent
        """
        now = timezone.now()

        # Check alert history
        if alert_type in self.alert_history:
            last_alert_time = self.alert_history[alert_type]
            if now - last_alert_time < self.suppression_window:
                logger.info(f"Suppressing {alert_type} alert (sent {last_alert_time})")
                return False

        # Update alert history
        self.alert_history[alert_type] = now
        return True

    @staticmethod
    def check_monitoring_health() -> bool:
        """
        Check if monitoring is healthy.

        Returns:
            True if monitoring is healthy, False otherwise
        """
        last_run = cache.get("monitor_metrics", {}).get("last_run")
        if not last_run:
            return False

        try:
            last_run_time = datetime.fromisoformat(last_run)
            time_since = (timezone.now() - last_run_time).seconds

            # Alert if monitor hasn't run in 2 minutes
            if time_since > 120:
                try:
                    import sentry_sdk

                    sentry_sdk.capture_message(
                        f"Monitoring task not running! Last run: {time_since}s ago",
                        level="error",
                    )
                except ImportError:
                    logger.error(
                        f"Monitoring task not running! Last run: {time_since}s ago"
                    )
                return False
        except Exception as e:
            logger.error(f"Error checking monitoring health: {e}")
            return False

        return True

    def get_alert_configuration(self) -> Dict[str, Any]:
        """
        Get current alert configuration.

        Returns:
            Dictionary with alert configuration
        """
        return {
            "thresholds": self.alert_rules.alert_thresholds,
            "suppression_window_minutes": self.suppression_window.total_seconds() / 60,
            "email_recipients": getattr(settings, "ALERT_EMAIL_RECIPIENTS", []),
            "slack_enabled": bool(getattr(settings, "SLACK_WEBHOOK_URL", None)),
            "alert_history": {k: v.isoformat() for k, v in self.alert_history.items()},
        }

    def update_threshold(self, alert_type: str, new_value: Any) -> bool:
        """
        Update an alert threshold.

        Args:
            alert_type: Type of alert
            new_value: New threshold value

        Returns:
            True if updated successfully
        """
        return self.alert_rules.update_threshold(alert_type, new_value)
