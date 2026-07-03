from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.text import slugify

from .forms import AdminUserCreationForm
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = AdminUserCreationForm

    list_display = ("id", "username", "email", "is_active", "created_at")
    list_filter = ("is_active", "is_staff", "is_superuser", "created_at")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("-created_at",)

    fieldsets = UserAdmin.fieldsets + (
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("id", "created_at", "updated_at")

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
        (
            "Organisation Assignment",
            {
                "fields": (
                    "organisation",
                    "create_new_org",
                    "new_org_name",
                    "default_role",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """Create organisation membership on user creation."""
        super().save_model(request, obj, form, change)

        if not change:  # Only on creation
            from apps.organisation.models import Organisation, OrganisationMembership

            if form.cleaned_data["create_new_org"]:
                # Create new organisation
                org_name = form.cleaned_data["new_org_name"]
                slug = slugify(org_name)

                # Ensure unique slug
                counter = 1
                base_slug = slug
                while Organisation.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1

                organisation = Organisation.objects.create(
                    name=org_name,
                    slug=slug,
                )
            else:
                organisation = form.cleaned_data["organisation"]

            # Create membership
            OrganisationMembership.objects.create(
                user=obj,
                organisation=organisation,
                role=form.cleaned_data["default_role"],
                is_active=True,
            )
