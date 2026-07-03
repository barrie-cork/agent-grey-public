"""
Email notification service for report generation.

Provides email notifications when reports are ready for download.
"""

import logging

from django.urls import reverse

from apps.core.services.base_email_service import BaseEmailNotificationService
from apps.reporting.models import ExportReport

logger = logging.getLogger(__name__)


class ReportEmailService(BaseEmailNotificationService):
    """Service for sending report-related email notifications."""

    SERVICE_NAME = "ReportEmailService"
    SERVICE_VERSION = "1.0.0"

    def health_check(self) -> bool:
        """Check if service is healthy."""
        try:
            ExportReport.objects.count()
            return True
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def send_report_ready_notification(self, report: ExportReport) -> bool:
        """Send notification when a report is ready for download."""
        with self._measure_performance("send_report_ready_notification"):
            try:
                user = report.generated_by
                if not user or not user.email:
                    logger.warning(
                        f"Report {report.id} has no associated user or email"
                    )
                    return False

                download_path = reverse("reporting:download_report", args=[report.id])
                download_url = f"{self._get_base_url()}{download_path}"

                session_url = f"{self._get_base_url()}/sessions/{report.session_id}/"

                file_size_display = self._format_file_size(report.file_size_bytes)

                context = {
                    "user_name": user.get_full_name() or user.username,
                    "report_title": report.title,
                    "report_type": report.get_report_type_display(),
                    "export_format": report.get_export_format_display(),
                    "session_title": report.session.title,
                    "download_url": download_url,
                    "session_url": session_url,
                    "file_size": file_size_display,
                    "expires_at": report.expires_at,
                }

                return self._send_email(
                    subject=f"Report Ready: {report.title}",
                    html_template="emails/reporting/report_ready.html",
                    context=context,
                    recipient_list=[user.email],
                )

            except Exception as e:
                self._handle_error(
                    e,
                    operation="send_report_ready_notification",
                    context={"report_id": str(report.id)},
                )
                return False

    @staticmethod
    def _format_file_size(size_bytes: int) -> str:
        """Format file size in human-readable form."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
