"""
Django admin configuration for feedback models.
"""

import csv

from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html

from .models import UserFeedback


@admin.action(description="Mark selected feedback as resolved")
def mark_as_resolved(modeladmin, request, queryset):
    """Admin action to mark feedback as resolved."""
    updated = queryset.update(status="resolved")
    modeladmin.message_user(request, f"{updated} feedback items marked as resolved.")


@admin.action(description="Mark selected feedback as dismissed")
def mark_as_dismissed(modeladmin, request, queryset):
    """Admin action to mark feedback as dismissed."""
    updated = queryset.update(status="dismissed")
    modeladmin.message_user(request, f"{updated} feedback items marked as dismissed.")


@admin.action(description="Export selected feedback to CSV")
def export_to_csv(modeladmin, request, queryset):
    """Export feedback to CSV file."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="feedback_export.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "ID",
            "Submitted By",
            "Email",
            "Page Path",
            "Page Title",
            "Feedback Type",
            "Subject",
            "Message",
            "Rating",
            "Status",
            "Created At",
            "Browser Info",
        ]
    )

    for feedback in queryset:
        writer.writerow(
            [
                str(feedback.id),
                feedback.submitter_display,
                feedback.email or "",
                feedback.page_path,
                feedback.page_title,
                feedback.get_feedback_type_display(),
                feedback.subject,
                feedback.message,
                feedback.rating or "",
                feedback.get_status_display(),
                feedback.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                str(feedback.browser_info),
            ]
        )

    return response


@admin.register(UserFeedback)
class UserFeedbackAdmin(admin.ModelAdmin):
    """
    Admin interface for UserFeedback model.
    """

    list_display = [
        "id_short",
        "submitter_display",
        "page_title_short",
        "feedback_type",
        "rating",
        "status_colored",
        "is_critical",
        "created_at",
    ]

    list_filter = [
        "status",
        "feedback_type",
        "rating",
        "severity",
        "team_decision",
        "created_at",
        ("user", admin.RelatedOnlyFieldListFilter),
    ]

    search_fields = [
        "subject",
        "message",
        "page_path",
        "page_title",
        "user__username",
        "user__email",
        "email",
    ]

    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
        "browser_info_formatted",
        "submitter_display",
        "is_anonymous",
    ]

    fieldsets = [
        (
            "Feedback Information",
            {
                "fields": [
                    "id",
                    "submitter_display",
                    "user",
                    "email",
                    "is_anonymous",
                ]
            },
        ),
        (
            "Page Context",
            {
                "fields": [
                    "page_path",
                    "page_title",
                ]
            },
        ),
        (
            "Feedback Content",
            {
                "fields": [
                    "feedback_type",
                    "subject",
                    "message",
                    "rating",
                ]
            },
        ),
        (
            "Administrative",
            {
                "fields": [
                    "status",
                    "admin_notes",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Voice Feedback",
            {
                "classes": ["collapse"],
                "fields": (
                    "transcription",
                    "audio_file",
                    "audio_duration_ms",
                    "voice_metadata",
                ),
            },
        ),
        (
            "Screenshot",
            {
                "classes": ["collapse"],
                "fields": ("screenshot",),
            },
        ),
        (
            "Enhanced Details",
            {
                "classes": ["collapse"],
                "fields": (
                    "severity",
                    "expected_behaviour",
                    "actual_behaviour",
                    "frequency",
                    "contact_email",
                ),
            },
        ),
        (
            "Rich Context",
            {
                "classes": ["collapse"],
                "fields": (
                    "screen_category",
                    "interaction_context",
                ),
            },
        ),
        (
            "GitHub Issue",
            {
                "classes": ["collapse"],
                "fields": (
                    "github_issue_url",
                    "github_issue_number",
                    "github_issue_state",
                    "github_issue_resolution",
                    "github_issue_closed_at",
                ),
            },
        ),
        (
            "Triage",
            {
                "classes": ["collapse"],
                "fields": (
                    "team_decision",
                    "team_decision_notes",
                    "team_decision_at",
                ),
            },
        ),
        (
            "Technical Information",
            {
                "fields": [
                    "browser_info_formatted",
                    "created_at",
                    "updated_at",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    actions = [mark_as_resolved, mark_as_dismissed, export_to_csv]

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("user")

    def id_short(self, obj):
        """Show shortened ID for display."""
        return str(obj.id)[:8]

    id_short.short_description = "ID"
    id_short.admin_order_field = "id"

    def page_title_short(self, obj):
        """Show shortened page title."""
        if obj.page_title:
            return obj.page_title[:50] + ("..." if len(obj.page_title) > 50 else "")
        return obj.page_path[:50] + ("..." if len(obj.page_path) > 50 else "")

    page_title_short.short_description = "Page"
    page_title_short.admin_order_field = "page_title"

    def status_colored(self, obj):
        """Show status with color coding."""
        colors = {
            "new": "#dc3545",  # red
            "in_progress": "#ffc107",  # yellow
            "resolved": "#198754",  # green
            "dismissed": "#6c757d",  # gray
        }
        color = colors.get(obj.status, "#000000")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_colored.short_description = "Status"
    status_colored.admin_order_field = "status"

    def is_critical(self, obj):
        """Show if feedback is critical (bug with low rating)."""
        if obj.is_critical:
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">⚠️ Critical</span>'
            )
        return "-"

    is_critical.short_description = "Priority"

    def browser_info_formatted(self, obj):
        """Format browser info for display."""
        if not obj.browser_info:
            return "No technical information available"

        info = obj.browser_info
        formatted = []

        if "user_agent" in info:
            formatted.append(f"<strong>User Agent:</strong> {info['user_agent']}")

        if "ip_address" in info:
            formatted.append(f"<strong>IP Address:</strong> {info['ip_address']}")

        if "screen_resolution" in info and info["screen_resolution"]:
            formatted.append(
                f"<strong>Screen Resolution:</strong> {info['screen_resolution']}"
            )

        if "viewport_size" in info and info["viewport_size"]:
            formatted.append(f"<strong>Viewport:</strong> {info['viewport_size']}")

        if "browser_language" in info:
            formatted.append(f"<strong>Language:</strong> {info['browser_language']}")

        return format_html("<br>".join(formatted))

    browser_info_formatted.short_description = "Technical Information"

    def changelist_view(self, request, extra_context=None):
        """Add extra context to changelist view."""
        extra_context = extra_context or {}

        # Add summary statistics
        total_feedback = self.get_queryset(request).count()
        critical_feedback = (
            self.get_queryset(request)
            .filter(
                feedback_type="bug", rating__lte=2, status__in=["new", "in_progress"]
            )
            .count()
        )

        extra_context["feedback_stats"] = {
            "total": total_feedback,
            "critical": critical_feedback,
        }

        return super().changelist_view(request, extra_context)
