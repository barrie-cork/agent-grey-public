"""
Admin configuration for the reporting app.

This module provides Django admin interface configuration for report management.
"""

from django.contrib import admin
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString

from .models import ExportReport


@admin.register(ExportReport)
class ExportReportAdmin(admin.ModelAdmin):
    """
    Enhanced admin interface for ExportReport model.

    Provides comprehensive report management capabilities including:
    - Status monitoring
    - Download links
    - Filtering and search
    - Batch operations
    """

    list_display = [
        "title",
        "report_type",
        "export_format",
        "status_badge",
        "session_link",
        "generated_by",
        "file_size_display",
        "download_link",
        "created_at",
    ]

    list_filter = [
        "status",
        "report_type",
        "export_format",
        "created_at",
        "completed_at",
    ]

    search_fields = [
        "title",
        "session__title",
        "generated_by__email",
        "generated_by__username",
    ]

    readonly_fields = [
        "id",
        "created_at",
        "generated_at",
        "completed_at",
        "file_size_bytes",
        "download_count",
        "status_badge",
        "progress_bar",
        "error_display",
    ]

    fieldsets = (
        (
            "Report Information",
            {
                "fields": (
                    "id",
                    "title",
                    "session",
                    "report_type",
                    "export_format",
                    "generated_by",
                )
            },
        ),
        (
            "Generation Details",
            {
                "fields": (
                    "status",
                    "status_badge",
                    "progress_bar",
                    "error_display",
                    "generation_parameters",
                )
            },
        ),
        (
            "File Information",
            {
                "fields": (
                    "file_path",
                    "file_name",
                    "file_size_bytes",
                    "download_count",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "total_results",
                    "included_results",
                    "excluded_results",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "generated_at",
                    "completed_at",
                    "expires_at",
                )
            },
        ),
    )

    def status_badge(self, obj: ExportReport) -> SafeString:
        """Display status as colored badge."""
        colors = {
            "pending": "gray",
            "generating": "blue",
            "completed": "green",
            "failed": "red",
            "expired": "orange",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def progress_bar(self, obj: ExportReport):
        """Display progress as visual bar."""
        if obj.status == "generating":
            return format_html(
                '<div style="width: 200px; background-color: #f0f0f0; '
                'border-radius: 3px; overflow: hidden;">'
                '<div style="width: {}%; background-color: #4CAF50; height: 20px; '
                'text-align: center; color: white; line-height: 20px;">{}%</div></div>',
                obj.progress_percentage or 0,
                obj.progress_percentage or 0,
            )
        return "-"

    progress_bar.short_description = "Progress"

    def error_display(self, obj: ExportReport):
        """Display error message if any."""
        if obj.error_message:
            return format_html(
                '<span style="color: red;" title="{}">{}</span>',
                obj.error_message,
                (
                    obj.error_message[:50] + "..."
                    if len(obj.error_message) > 50
                    else obj.error_message
                ),
            )
        return "-"

    error_display.short_description = "Error"

    def file_size_display(self, obj: ExportReport) -> str:
        """Display file size in human-readable format."""
        if obj.file_size_bytes:
            size = obj.file_size_bytes
            for unit in ["B", "KB", "MB", "GB"]:
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024
        return "-"

    file_size_display.short_description = "File Size"

    def download_link(self, obj: ExportReport):
        """Provide download link for completed reports."""
        if obj.status == "completed" and obj.file_path:
            url = reverse("reporting:download_report", args=[obj.id])
            return format_html('<a href="{}" target="_blank">Download</a>', url)
        return "-"

    download_link.short_description = "Download"

    def session_link(self, obj: ExportReport):
        """Link to the search session."""
        if obj.session:
            url = reverse(
                "admin:review_manager_searchsession_change", args=[obj.session.id]
            )
            return format_html(
                '<a href="{}">{}</a>',
                url,
                (
                    obj.session.title[:30] + "..."
                    if len(obj.session.title) > 30
                    else obj.session.title
                ),
            )
        return "-"

    session_link.short_description = "Session"

    def has_delete_permission(
        self, request: HttpRequest, obj: ExportReport | None = None
    ) -> bool:
        """Only allow deletion of failed or expired reports."""
        if obj and obj.status in ["completed", "generating"]:
            return False
        return super().has_delete_permission(request, obj)

    class Media:
        css = {"all": ("admin/css/reporting_admin.css",)}
