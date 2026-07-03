"""Django admin configuration for organisation app."""

from django.contrib import admin

from .models import Organisation, OrganisationInvitation, OrganisationMembership


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    """Admin interface for Organisation model."""

    list_display = [
        "name",
        "slug",
        "default_min_reviewers",
        "require_dual_review",
        "max_active_reviews",
        "max_users",
        "created_at",
    ]
    list_filter = ["default_min_reviewers", "require_dual_review", "created_at"]
    search_fields = ["name", "slug"]
    readonly_fields = ["id", "created_at", "updated_at"]
    prepopulated_fields = {"slug": ("name",)}

    fieldsets = (
        ("Basic Information", {"fields": ("id", "name", "slug")}),
        (
            "Organisation Defaults",
            {
                "fields": (
                    "default_min_reviewers",
                    "require_dual_review",
                    "default_conflict_resolution_method",
                )
            },
        ),
        (
            "Quotas",
            {
                "fields": ("max_active_reviews", "max_users"),
                "description": "Leave blank for unlimited",
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def has_module_permission(self, request):
        """Only Information Specialists and superusers can access organisation admin."""
        if request.user.is_superuser:
            return True

        from apps.accounts.permissions import Permissions

        org = getattr(request, "organisation", None)
        return request.user.has_perm(Permissions.MANAGE_ORGANISATION, org)

    def has_view_permission(self, request, obj=None):
        """Control view access to organisations."""
        if request.user.is_superuser:
            return True

        from apps.accounts.permissions import Permissions

        org = getattr(request, "organisation", None)
        if not request.user.has_perm(Permissions.MANAGE_ORGANISATION, org):
            return False

        # For list view, allow access
        if obj is None:
            return True

        # For detail view, ensure user's org matches object
        return hasattr(request, "organisation") and request.organisation == obj

    def has_change_permission(self, request, obj=None):
        """Control edit access to organisations."""
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        """Control delete access to organisations."""
        return self.has_view_permission(request, obj)

    def get_queryset(self, request):
        """Filter queryset to show only user's organisation (except superusers)."""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs

        # Information Specialists see only their organisation
        if hasattr(request, "organisation") and request.organisation:
            return qs.filter(id=request.organisation.id)

        # No organisation = no access
        return qs.none()


@admin.register(OrganisationMembership)
class OrganisationMembershipAdmin(admin.ModelAdmin):
    """Admin interface for OrganisationMembership model."""

    list_display = [
        "user",
        "organisation",
        "role",
        "is_active",
        "joined_at",
    ]
    list_filter = ["role", "is_active", "joined_at"]
    search_fields = ["user__email", "user__username", "organisation__name"]
    readonly_fields = ["id", "joined_at"]
    autocomplete_fields = ["user", "organisation"]

    fieldsets = (
        ("Membership", {"fields": ("id", "organisation", "user", "role", "is_active")}),
        (
            "Permissions",
            {
                "fields": (
                    "can_create_reviews",
                    "can_manage_users",
                    "can_view_all_reviews",
                    "can_edit_configurations",
                    "can_export_data",
                ),
                "description": "Permissions are auto-set based on role but can be overridden",
            },
        ),
        ("Metadata", {"fields": ("joined_at",), "classes": ("collapse",)}),
    )

    def has_module_permission(self, request):
        """Only Information Specialists and superusers can access membership admin."""
        if request.user.is_superuser:
            return True

        from apps.accounts.permissions import Permissions

        org = getattr(request, "organisation", None)
        return request.user.has_perm(Permissions.MANAGE_ORGANISATION, org)

    def get_queryset(self, request):
        """Filter queryset to show only memberships from user's organisation."""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs

        # Information Specialists see only their organisation's memberships
        if hasattr(request, "organisation") and request.organisation:
            return qs.filter(organisation=request.organisation)

        return qs.none()


@admin.register(OrganisationInvitation)
class OrganisationInvitationAdmin(admin.ModelAdmin):
    """Admin interface for OrganisationInvitation model."""

    list_display = [
        "email",
        "organisation",
        "role",
        "status",
        "created_at",
        "expires_at",
    ]
    list_filter = ["status", "role", "created_at"]
    search_fields = ["email", "name", "organisation__name"]
    readonly_fields = ["id", "token", "created_at", "accepted_at"]
    autocomplete_fields = ["organisation", "invited_by"]

    fieldsets = (
        (
            "Invitation Details",
            {"fields": ("id", "organisation", "invited_by", "email", "name", "role")},
        ),
        (
            "Status",
            {"fields": ("status", "token", "created_at", "expires_at", "accepted_at")},
        ),
    )

    def has_add_permission(self, request):
        """Disable manual invitation creation via admin (use API instead)."""
        return False
