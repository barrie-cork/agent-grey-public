"""
Admin interface for core app models.
"""

import json

from django.contrib import admin
from django.utils.html import format_html

from apps.core.models import Configuration


@admin.register(Configuration)
class ConfigurationAdmin(admin.ModelAdmin):
    """Admin interface for Configuration model."""

    list_display = [
        "key",
        "value_preview",
        "description_preview",
        "updated_at",
        "updated_by",
    ]
    list_filter = ["updated_at"]
    search_fields = ["key", "description"]
    readonly_fields = ["updated_at", "updated_by", "formatted_value"]

    fieldsets = (
        (None, {"fields": ("key", "value", "description")}),
        (
            "Metadata",
            {
                "fields": ("updated_at", "updated_by", "formatted_value"),
                "classes": ("collapse",),
            },
        ),
    )

    def value_preview(self, obj):
        """Display a preview of the configuration value."""
        return obj.get_value_preview(max_length=60)

    value_preview.short_description = "Value"

    def description_preview(self, obj):
        """Display a preview of the description."""
        if obj.description:
            preview = obj.description[:80]
            if len(obj.description) > 80:
                preview += "..."
            return preview
        return "-"

    description_preview.short_description = "Description"

    def formatted_value(self, obj):
        """Display formatted JSON value."""
        try:
            formatted = json.dumps(obj.value, indent=2, sort_keys=True)
            return format_html('<pre style="margin: 0;">{}</pre>', formatted)
        except (TypeError, ValueError):
            return str(obj.value)

    formatted_value.short_description = "Formatted Value"

    def save_model(self, request, obj, form, change):
        """Set the updated_by field to the current user."""
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        """Allow adding new configurations."""
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        """Allow changing configurations."""
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Allow deleting configurations."""
        return request.user.is_superuser
