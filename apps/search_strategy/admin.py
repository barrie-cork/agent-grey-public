from django.contrib import admin

from .models import SearchQuery, SearchStrategy


@admin.register(SearchStrategy)
class SearchStrategyAdmin(admin.ModelAdmin):
    list_display = ["__str__", "user", "is_complete", "created_at", "updated_at"]
    list_filter = ["is_complete", "created_at"]
    search_fields = [
        "session__title",
        "user__username",
        "population_terms",
        "interest_terms",
        "context_terms",
    ]
    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = (
        ("Session Information", {"fields": ("id", "session", "user")}),
        (
            "PIC Framework",
            {"fields": ("population_terms", "interest_terms", "context_terms")},
        ),
        ("Search Configuration", {"fields": ("search_config",)}),
        ("Status", {"fields": ("is_complete", "validation_errors")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.user = request.user
        super().save_model(request, obj, form, change)


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "query_type",
        "target_domain",
        "is_active",
        "execution_order",
        "created_at",
    ]
    list_filter = ["query_type", "is_active", "created_at"]
    search_fields = ["query_text", "target_domain", "strategy__session__title"]
    readonly_fields = ["id", "created_at"]

    fieldsets = (
        ("Basic Information", {"fields": ("id", "strategy")}),
        ("Query Details", {"fields": ("query_text", "query_type", "target_domain")}),
        (
            "Execution Settings",
            {"fields": ("execution_order", "is_active", "estimated_results")},
        ),
        ("Timestamps", {"fields": ("created_at",)}),
    )

    actions = ["activate_queries", "deactivate_queries"]

    def activate_queries(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} queries")

    activate_queries.short_description = "Activate selected queries"

    def deactivate_queries(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} queries")

    deactivate_queries.short_description = "Deactivate selected queries"
