"""
Alert notification logic for different channels.

This module handles sending alerts via various notification channels
including email and Slack webhooks.
"""

import json
import logging
from typing import Any, Dict, List

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


class AlertNotificationService:
    """
    Service for sending alert notifications via configured channels.

    Supports:
    - Email notifications
    - Slack webhook notifications
    - Logging-based notifications
    """

    def send_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        """
        Send alerts via configured channels.

        Args:
            alerts: List of alert dictionaries
        """
        try:
            # Send email alerts
            if getattr(settings, "ALERT_EMAIL_RECIPIENTS", None):
                self._send_email_alerts(alerts)

            # Send Slack alerts
            if getattr(settings, "SLACK_WEBHOOK_URL", None):
                self._send_slack_alerts(alerts)

            # Log all alerts
            for alert in alerts:
                severity = alert.get("severity", "unknown")
                if severity == "critical":
                    logger.critical(f"Alert: {alert['type']} - {alert['message']}")
                elif severity == "high":
                    logger.error(f"Alert: {alert['type']} - {alert['message']}")
                else:
                    logger.warning(f"Alert: {alert['type']} - {alert['message']}")

        except Exception as e:
            logger.error(f"Failed to send alerts: {str(e)}")

    def send_high_failure_alert(self, failure_count: int) -> None:
        """
        Alert when failure rate is high.

        Args:
            failure_count: Number of failures detected
        """
        # Prevent spam - only alert once per hour
        from django.core.cache import cache

        if cache.get("high_failure_alert_sent"):
            return

        cache.set("high_failure_alert_sent", True, timeout=3600)

        try:
            import sentry_sdk

            with sentry_sdk.new_scope() as scope:
                scope.set_extra("failure_count", failure_count)
                scope.set_extra(
                    "api_timeout", getattr(settings, "API_SERPER_TIMEOUT", 30)
                )
                scope.set_extra(
                    "batch_size", getattr(settings, "PROCESSING_BATCH_SIZE", 50)
                )
                sentry_sdk.capture_message(
                    f"High failure rate: {failure_count} sessions/executions failed",
                    level="error",
                )
        except ImportError:
            logger.error(
                f"High failure rate: {failure_count} sessions/executions failed"
            )

    def _send_email_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        """
        Send alerts via email.

        Args:
            alerts: List of alert dictionaries
        """
        try:
            subject = f"[Agent Grey] Workflow Alert - {len(alerts)} issues detected"
            message = self._format_email_message(alerts)

            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                settings.ALERT_EMAIL_RECIPIENTS,
                fail_silently=False,
            )

            logger.info(
                f"Sent email alert to {len(settings.ALERT_EMAIL_RECIPIENTS)} recipients"
            )

        except Exception as e:
            logger.error(f"Failed to send email alerts: {str(e)}")

    def _send_slack_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        """
        Send alerts via Slack webhook.

        Args:
            alerts: List of alert dictionaries
        """
        try:
            import requests

            for alert in alerts:
                # Format Slack message
                color = {
                    "critical": "danger",
                    "high": "warning",
                    "medium": "warning",
                    "low": "good",
                }.get(alert.get("severity", "low"), "warning")

                slack_message = {
                    "text": f"Workflow Alert: {alert['type']}",
                    "attachments": [
                        {
                            "color": color,
                            "title": alert["type"].replace("_", " ").title(),
                            "text": alert["message"],
                            "fields": [
                                {
                                    "title": "Severity",
                                    "value": alert.get("severity", "unknown"),
                                    "short": True,
                                },
                                {
                                    "title": "Time",
                                    "value": alert.get("timestamp", "unknown"),
                                    "short": True,
                                },
                            ],
                            "footer": "Agent Grey Monitoring",
                            "ts": int(timezone.now().timestamp()),
                        }
                    ],
                }

                # Add details if available
                if alert.get("details"):
                    slack_message["attachments"][0]["fields"].append(
                        {
                            "title": "Details",
                            "value": json.dumps(alert["details"], indent=2)[
                                :500
                            ],  # Limit size
                            "short": False,
                        }
                    )

                # Send to Slack
                response = requests.post(
                    settings.SLACK_WEBHOOK_URL, json=slack_message, timeout=5
                )

                if response.status_code != 200:
                    logger.error(f"Slack webhook failed: {response.status_code}")

            logger.info(f"Sent {len(alerts)} alerts to Slack")

        except Exception as e:
            logger.error(f"Failed to send Slack alerts: {str(e)}")

    def _format_email_message(self, alerts: List[Dict[str, Any]]) -> str:
        """
        Format alerts for email.

        Args:
            alerts: List of alert dictionaries

        Returns:
            Formatted email message
        """
        lines = [
            "Workflow System Alerts",
            "=" * 50,
            f"Time: {timezone.now().isoformat()}",
            f"Environment: {getattr(settings, 'ENVIRONMENT', 'unknown')}",
            "",
            f"Total Alerts: {len(alerts)}",
            "",
            "Alert Details:",
            "-" * 30,
        ]

        for i, alert in enumerate(alerts, 1):
            lines.extend(
                [
                    "",
                    f"Alert #{i}",
                    f"Type: {alert['type']}",
                    f"Severity: {alert.get('severity', 'unknown').upper()}",
                    f"Message: {alert['message']}",
                ]
            )

            # Add additional details
            if alert.get("count"):
                lines.append(f"Count: {alert['count']}")
            if alert.get("rate"):
                lines.append(f"Rate: {alert['rate']:.2%}")

            # Add first few details if available
            if alert.get("details") and isinstance(alert["details"], list):
                lines.append("Sample Details:")
                for detail in alert["details"][:3]:
                    lines.append(f"  - {json.dumps(detail, indent=2)}")

            lines.append("-" * 30)

        lines.extend(
            [
                "",
                "Action Required:",
                "Please check the monitoring dashboard for more details.",
                f"Dashboard URL: {getattr(settings, 'SITE_URL', 'http://localhost:8000')}/monitoring/",
                "",
                "This is an automated alert from Agent Grey monitoring system.",
            ]
        )

        return "\n".join(lines)
