"""
Report status management service.

This service provides centralized management of report status transitions
and ensures valid state changes according to business rules.
"""

import logging
from enum import Enum
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from apps.reporting.models import ExportReport

logger = logging.getLogger(__name__)


class ReportStatus(Enum):
    """Enumeration of valid report statuses."""

    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ReportStatusManager:
    """Manage report status transitions and validation."""

    # Define allowed status transitions
    ALLOWED_TRANSITIONS = {
        ReportStatus.PENDING: [ReportStatus.GENERATING, ReportStatus.FAILED],
        ReportStatus.GENERATING: [ReportStatus.COMPLETED, ReportStatus.FAILED],
        ReportStatus.FAILED: [ReportStatus.PENDING],  # Allow retry
        ReportStatus.COMPLETED: [ReportStatus.EXPIRED],  # Can only expire
        ReportStatus.EXPIRED: [],  # Terminal state
    }

    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        """
        Check if a status transition is allowed.

        Args:
            from_status: Current status string
            to_status: Desired status string

        Returns:
            True if transition is allowed, False otherwise
        """
        try:
            from_enum = ReportStatus(from_status)
            to_enum = ReportStatus(to_status)
        except ValueError:
            logger.warning(f"Invalid status value: {from_status} or {to_status}")
            return False

        allowed = cls.ALLOWED_TRANSITIONS.get(from_enum, [])
        return to_enum in allowed

    @classmethod
    def transition(
        cls, report: "ExportReport", new_status: str, error_message=None
    ) -> bool:
        """
        Perform a status transition if allowed.

        Args:
            report: ExportReport instance to update
            new_status: Target status string
            error_message:  error message for failed status

        Returns:
            True if transition was successful, False otherwise
        """
        if not cls.can_transition(report.status, new_status):
            logger.warning(
                f"Invalid transition attempted: {report.status} -> {new_status} "
                f"for report {report.id}"
            )
            return False

        # Update status
        old_status = report.status
        report.status = new_status

        # Handle status-specific updates
        if new_status == ReportStatus.FAILED.value and error_message:
            report.error_message = error_message
        elif new_status == ReportStatus.COMPLETED.value:
            report.completed_at = timezone.now()
            report.progress_percentage = 100
        elif new_status == ReportStatus.GENERATING.value:
            report.progress_percentage = 10
        elif new_status == ReportStatus.EXPIRED.value:
            # Clear file path when expired
            report.file_path = ""

        # Save changes
        fields_to_update = ["status", "progress_percentage"]
        if hasattr(report, "error_message") and error_message:
            fields_to_update.append("error_message")
        if (
            hasattr(report, "completed_at")
            and new_status == ReportStatus.COMPLETED.value
        ):
            fields_to_update.append("completed_at")
        if new_status == ReportStatus.EXPIRED.value:
            fields_to_update.append("file_path")

        report.save(update_fields=fields_to_update)

        logger.info(
            f"Report {report.id} transitioned from {old_status} to {new_status}"
        )

        return True

    @classmethod
    def get_available_transitions(cls, current_status: str):
        """
        Get list of available transitions from current status.

        Args:
            current_status: Current status string

        Returns:
            List of allowed target statuses
        """
        try:
            status_enum = ReportStatus(current_status)
            allowed_enums = cls.ALLOWED_TRANSITIONS.get(status_enum, [])
            return [status.value for status in allowed_enums]
        except ValueError:
            return []

    @classmethod
    def is_terminal_state(cls, status: str) -> bool:
        """
        Check if a status is a terminal state (no transitions allowed).

        Args:
            status: Status string to check

        Returns:
            True if terminal state, False otherwise
        """
        return len(cls.get_available_transitions(status)) == 0

    @classmethod
    def update_progress(cls, report: "ExportReport", progress: int) -> None:
        """
        Update report progress percentage.

        Args:
            report: ExportReport instance
            progress: Progress percentage (0-100)
        """
        if report.status != ReportStatus.GENERATING.value:
            logger.warning(
                f"Attempted to update progress for report {report.id} "
                f"in status {report.status}"
            )
            return

        # Clamp progress between 0 and 100
        progress = max(0, min(100, progress))

        report.progress_percentage = progress
        report.save(update_fields=["progress_percentage"])

    @classmethod
    def mark_as_started(cls, report: "ExportReport") -> bool:
        """
        Mark a report as started (transition to generating).

        Args:
            report: ExportReport instance

        Returns:
            True if successful, False otherwise
        """
        return cls.transition(report, ReportStatus.GENERATING.value)

    @classmethod
    def mark_as_completed(cls, report: "ExportReport") -> bool:
        """
        Mark a report as completed.

        Args:
            report: ExportReport instance

        Returns:
            True if successful, False otherwise
        """
        return cls.transition(report, ReportStatus.COMPLETED.value)

    @classmethod
    def mark_as_failed(cls, report: "ExportReport", error_message: str) -> bool:
        """
        Mark a report as failed with error message.

        Args:
            report: ExportReport instance
            error_message: Description of the failure

        Returns:
            True if successful, False otherwise
        """
        return cls.transition(report, ReportStatus.FAILED.value, error_message)

    @classmethod
    def mark_as_expired(cls, report: "ExportReport") -> bool:
        """
        Mark a report as expired.

        Args:
            report: ExportReport instance

        Returns:
            True if successful, False otherwise
        """
        return cls.transition(report, ReportStatus.EXPIRED.value)

    @classmethod
    def can_retry(cls, report: "ExportReport") -> bool:
        """
        Check if a report can be retried (failed -> pending).

        Args:
            report: ExportReport instance

        Returns:
            True if retry is allowed, False otherwise
        """
        return report.status == ReportStatus.FAILED.value

    @classmethod
    def retry_report(cls, report: "ExportReport") -> bool:
        """
        Reset a failed report to pending for retry.

        Args:
            report: ExportReport instance

        Returns:
            True if successful, False otherwise
        """
        if not cls.can_retry(report):
            return False

        # Clear error message on retry
        report.error_message = ""
        return cls.transition(report, ReportStatus.PENDING.value)
