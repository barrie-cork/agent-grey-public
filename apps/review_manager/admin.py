from django.contrib import admin, messages

from .models import ReviewInvitation, SearchSession, SessionActivity

# SessionStateManager imported lazily in action methods


@admin.register(SearchSession)
class SearchSessionAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "owner", "created_at", "progress_percentage"]
    list_filter = ["status", "created_at", "owner"]
    search_fields = ["title", "description", "owner__username"]
    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
        "progress_percentage",
        "inclusion_rate",
    ]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("id", "title", "description", "status", "owner")},
        ),
        (
            "Statistics",
            {
                "fields": (
                    "total_queries",
                    "total_results",
                    "reviewed_results",
                    "included_results",
                    "progress_percentage",
                    "inclusion_rate",
                )
            },
        ),
        ("Metadata", {"fields": ("notes",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at", "started_at", "completed_at")},
        ),
    )

    actions = [
        "set_status_draft",
        "set_status_defining_search",
        "set_status_ready_to_execute",
    ]

    def set_status_draft(self, request, queryset):
        # Lazy import to avoid Django initialization timing issues
        from .services.state_manager import SessionStateManager

        updated_count = 0
        failed_count = 0

        for session in queryset:
            state_manager = SessionStateManager(session)
            if state_manager.can_transition_to("draft"):
                try:
                    state_manager.transition_to(
                        "draft", user=request.user, reason="Admin bulk action"
                    )
                    updated_count += 1
                except Exception as e:
                    failed_count += 1
                    messages.warning(
                        request, f"Failed to update session '{session.title}': {str(e)}"
                    )
            else:
                failed_count += 1

        if updated_count > 0:
            self.message_user(
                request, f"Updated {updated_count} sessions to Draft status"
            )
        if failed_count > 0:
            self.message_user(
                request,
                f"{failed_count} sessions could not be updated (check transition rules)",
                level=messages.WARNING,
            )

    set_status_draft.short_description = "Set status to Draft"

    def set_status_defining_search(self, request, queryset):
        # Lazy import to avoid Django initialization timing issues
        from .services.state_manager import SessionStateManager

        updated_count = 0
        failed_count = 0

        for session in queryset:
            state_manager = SessionStateManager(session)
            if state_manager.can_transition_to("defining_search"):
                try:
                    state_manager.transition_to(
                        "defining_search", user=request.user, reason="Admin bulk action"
                    )
                    updated_count += 1
                except Exception as e:
                    failed_count += 1
                    messages.warning(
                        request, f"Failed to update session '{session.title}': {str(e)}"
                    )
            else:
                failed_count += 1

        if updated_count > 0:
            self.message_user(
                request, f"Updated {updated_count} sessions to Defining Search status"
            )
        if failed_count > 0:
            self.message_user(
                request,
                f"{failed_count} sessions could not be updated (check transition rules)",
                level=messages.WARNING,
            )

    set_status_defining_search.short_description = "Set status to Defining Search"

    def set_status_ready_to_execute(self, request, queryset):
        # Lazy import to avoid Django initialization timing issues
        from .services.state_manager import SessionStateManager

        updated_count = 0
        failed_count = 0

        for session in queryset:
            state_manager = SessionStateManager(session)
            if state_manager.can_transition_to("ready_to_execute"):
                try:
                    state_manager.transition_to(
                        "ready_to_execute",
                        user=request.user,
                        reason="Admin bulk action",
                    )
                    updated_count += 1
                except Exception as e:
                    failed_count += 1
                    messages.warning(
                        request, f"Failed to update session '{session.title}': {str(e)}"
                    )
            else:
                failed_count += 1

        if updated_count > 0:
            self.message_user(
                request, f"Updated {updated_count} sessions to Ready to Execute status"
            )
        if failed_count > 0:
            self.message_user(
                request,
                f"{failed_count} sessions could not be updated (check transition rules)",
                level=messages.WARNING,
            )

    set_status_ready_to_execute.short_description = "Set status to Ready to Execute"


@admin.register(ReviewInvitation)
class ReviewInvitationAdmin(admin.ModelAdmin):
    """Admin interface for managing review invitations."""

    list_display = [
        "invitee_email",
        "session",
        "status",
        "inviter",
        "invited_at",
        "expires_at",
    ]
    list_filter = ["status", "invited_at", "expires_at"]
    search_fields = ["invitee_email", "invitee_name", "session__title"]
    readonly_fields = ["id", "token", "invited_at", "responded_at"]
    autocomplete_fields = ["session", "inviter", "invitee"]

    fieldsets = (
        (
            "Invitation Details",
            {
                "fields": (
                    "id",
                    "session",
                    "inviter",
                    "invitee_email",
                    "invitee_name",
                    "invitee",
                )
            },
        ),
        (
            "Status",
            {"fields": ("status", "token", "invited_at", "expires_at", "responded_at")},
        ),
    )

    def has_add_permission(self, request):
        """Disable manual creation of invitations (use API only)."""
        return False


@admin.register(SessionActivity)
class SessionActivityAdmin(admin.ModelAdmin):
    list_display = ["activity_type", "session", "user", "created_at"]
    list_filter = ["activity_type", "created_at"]
    search_fields = ["description", "session__title", "user__username"]
    readonly_fields = ["id", "created_at"]

    fieldsets = (
        (None, {"fields": ("id", "session", "user", "activity_type")}),
        ("Details", {"fields": ("description", "metadata")}),
        ("Timestamp", {"fields": ("created_at",)}),
    )
