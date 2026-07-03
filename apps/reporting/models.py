from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


def report_upload_path(instance, filename):
    """
    Generate upload path for report files organised by session.

    Args:
        instance: ExportReport instance being saved.
        filename: Original filename for the report file.

    Returns:
        str: Path in format 'reports/{session_uuid}/{filename}'.
    """
    return f"reports/{instance.session.id}/{filename}"


class ExportReport(TimeStampedModel):
    """
    Tracks generated reports and exports for PRISMA compliance.
    """

    REPORT_TYPES = [
        ("prisma_flow", "PRISMA Flow Diagram"),
        ("full_report", "Full PRISMA Report"),
        ("included_results", "Included Results List"),
        ("excluded_results", "Excluded Results with Reasons"),
        ("search_strategy", "Search Strategy Documentation"),
        ("data_export", "Raw Data Export"),
        ("offline_backup", "Offline Backup Export"),
        ("irr_report", "Inter-Rater Reliability Report"),
    ]

    EXPORT_FORMATS = [
        ("pdf", "PDF"),
        ("csv", "CSV"),
        ("html", "HTML"),
        ("xlsx", "Excel Spreadsheet"),
    ]

    # Relationships
    session = models.ForeignKey(
        "review_manager.SearchSession",
        on_delete=models.CASCADE,
        related_name="export_reports",
        help_text="The search session this report is for",
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        help_text="User who generated this report",
    )

    # Report details
    report_type = models.CharField(
        max_length=20, choices=REPORT_TYPES, help_text="Type of report"
    )
    export_format = models.CharField(
        max_length=10, choices=EXPORT_FORMATS, help_text="Export file format"
    )

    # File information
    file_name = models.CharField(max_length=255, help_text="Generated file name")
    file_path = models.FileField(
        upload_to=report_upload_path,
        max_length=255,
        help_text="Path to generated file organised by session UUID",
    )
    file_size_bytes = models.BigIntegerField(default=0, help_text="File size in bytes")

    # Report metadata
    title = models.CharField(max_length=255, help_text="Report title")
    description = models.TextField(blank=True, help_text="Report description or notes")

    # Report parameters
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Parameters used to generate report. See ReportParametersType in model_types.py",
    )

    # Statistics included
    total_results = models.IntegerField(default=0, help_text="Total results in report")
    included_results = models.IntegerField(
        default=0, help_text="Number of included results"
    )
    excluded_results = models.IntegerField(
        default=0, help_text="Number of excluded results"
    )
    maybe_results = models.IntegerField(
        default=0, help_text="Number of uncertain/maybe results"
    )

    # Generation status
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("generating", "Generating"),
            ("completed", "Completed"),
            ("failed", "Failed"),
        ],
        default="pending",
        help_text="Report generation status",
    )
    progress_percentage = models.IntegerField(
        default=0, help_text="Progress percentage (0-100)"
    )
    error_message = models.TextField(
        blank=True, help_text="Error message if generation failed"
    )

    # Usage tracking
    download_count = models.IntegerField(
        default=0, help_text="Number of times report was downloaded"
    )

    # Timestamps
    generated_at = models.DateTimeField(
        null=True, blank=True, help_text="When report generation completed"
    )
    completed_at = models.DateTimeField(
        null=True, blank=True, help_text="When report generation completed"
    )
    expires_at = models.DateTimeField(
        null=True, blank=True, help_text="When report file will be deleted"
    )

    class Meta:
        db_table = "export_reports"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "report_type"]),
            models.Index(fields=["generated_by", "-created_at"]),
        ]

    def __str__(self):
        """Return string representation of the export report.

        Returns:
            str: Report title and type display name.
        """
        return f"{self.title} ({self.get_report_type_display()})"

    def get_content_type(self):
        """Get MIME content type for the export format.

        Returns:
            str: MIME content type string for the report's export format.
        """
        from .constants import ExportConstants

        return ExportConstants.CONTENT_TYPES.get(
            self.export_format, ExportConstants.DEFAULT_CONTENT_TYPE
        )
