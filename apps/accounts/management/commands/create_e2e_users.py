"""
Management command to create E2E test users for Playwright tests.

This command creates test users and organisation memberships required for
E2E authentication tests. It is idempotent and can be safely run multiple times.

Convention:
    - Username prefix: e2e- (for safe teardown pattern matching)
    - Email domain: @test.local (non-routable)
    - Password: TestPass123! (uniform across all test users)
    - Login form takes email, authenticates via username internally

Usage:
    python manage.py create_e2e_users
"""

from typing import Any

from django.core.management.base import BaseCommand

# Unified E2E test user convention -- single source of truth
E2E_PASSWORD = "TestPass123!"
E2E_ORG_SLUG = "e2e-test-org"
E2E_ORG_NAME = "E2E Test Organisation"

E2E_USERS = [
    {
        "username": "e2e-reviewer1",
        "email": "e2e-reviewer1@test.local",
        "role": "REVIEWER",
        "permissions": {
            "can_create_reviews": False,
            "can_manage_users": False,
            "can_view_all_reviews": False,
            "can_edit_configurations": False,
            "can_export_data": False,
        },
    },
    {
        "username": "e2e-reviewer2",
        "email": "e2e-reviewer2@test.local",
        "role": "REVIEWER",
        "permissions": {
            "can_create_reviews": False,
            "can_manage_users": False,
            "can_view_all_reviews": False,
            "can_edit_configurations": False,
            "can_export_data": False,
        },
    },
    {
        "username": "e2e-admin",
        "email": "e2e-admin@test.local",
        "role": "INFORMATION_SPECIALIST",
        "permissions": {
            "can_create_reviews": True,
            "can_manage_users": True,
            "can_view_all_reviews": True,
            "can_edit_configurations": True,
            "can_export_data": True,
        },
    },
    {
        "username": "e2e-owner",
        "email": "e2e-owner@test.local",
        "role": "LEAD_REVIEWER",
        "permissions": {
            "can_create_reviews": True,
            "can_manage_users": False,
            "can_view_all_reviews": True,
            "can_edit_configurations": False,
            "can_export_data": True,
        },
    },
]


class Command(BaseCommand):
    help = "Create E2E test users for Playwright tests (idempotent)"

    def handle(self, *args: Any, **options: Any) -> None:
        """Create test organisation and users for E2E testing."""
        from django.contrib.auth import get_user_model

        from apps.organisation.models import Organisation, OrganisationMembership

        User = get_user_model()

        self.stdout.write(self.style.WARNING("\n=== Creating E2E Test Users ===\n"))

        # Create test organisation
        org, org_created = Organisation.objects.get_or_create(
            slug=E2E_ORG_SLUG,
            defaults={
                "name": E2E_ORG_NAME,
                "default_review_mode": "DUAL",
                "default_min_reviewers": 2,
                "require_dual_review": True,
                "default_conflict_resolution_method": "CONSENSUS",
            },
        )

        if org_created:
            self.stdout.write(self.style.SUCCESS(f"Created organisation: {org.name}"))
        else:
            self.stdout.write(f"Organisation already exists: {org.name}")

        # Create users and memberships
        for user_data in E2E_USERS:
            username = user_data["username"]
            email = user_data["email"]
            role = user_data["role"]
            permissions = user_data["permissions"]

            # Idempotent: look up by email first (unique constraint),
            # then by username, then create
            try:
                user = User.objects.get(email=email)
                user.username = username
                user.set_password(E2E_PASSWORD)
                user.save()
                self.stdout.write(f"Updated user: {user.username}")
            except User.DoesNotExist:
                try:
                    user = User.objects.get(username=username)
                    user.email = email
                    user.set_password(E2E_PASSWORD)
                    user.save()
                    self.stdout.write(f"Updated user: {user.username}")
                except User.DoesNotExist:
                    user = User.objects.create_user(
                        username=username, email=email, password=E2E_PASSWORD
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f"Created user: {user.username}")
                    )

            # Create or update membership
            membership, membership_created = (
                OrganisationMembership.objects.get_or_create(
                    user=user,
                    organisation=org,
                    defaults={"role": role, "is_active": True, **permissions},
                )
            )

            if membership_created:
                self.stdout.write(f"  -> Added to {org.name} as {membership.role}")
            else:
                membership.role = role
                membership.is_active = True
                for perm_key, perm_value in permissions.items():
                    setattr(membership, perm_key, perm_value)
                membership.save()
                self.stdout.write(f"  -> Already in {org.name} as {membership.role}")

        # Summary
        self.stdout.write(self.style.SUCCESS("\nE2E Test Users Ready\n"))
        self.stdout.write(f"Organisation: {org.name} ({org.slug})")
        self.stdout.write(f"Total members: {org.get_members_count()}")
        self.stdout.write(f"\nTest credentials (password: {E2E_PASSWORD}):")
        for user_data in E2E_USERS:
            self.stdout.write(f"  - {user_data['username']} ({user_data['email']})")
