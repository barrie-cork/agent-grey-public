"""
Management command to setup E2E testing organisation and user memberships.

Uses the unified E2E convention from create_e2e_users:
    - Username prefix: e2e-
    - Email domain: @test.local
    - Password: TestPass123!

Usage:
    docker-compose exec web python manage.py setup_e2e_org
    docker-compose exec web python manage.py setup_e2e_org --reset
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.core.management.base import BaseCommand

from apps.accounts.management.commands.create_e2e_users import (
    E2E_ORG_NAME,
    E2E_ORG_SLUG,
    E2E_PASSWORD,
)
from apps.organisation.models import Organisation, OrganisationMembership

User = get_user_model()


class Command(BaseCommand):
    """Setup E2E testing organisation and user memberships."""

    help = "Setup E2E testing organisation and user memberships"

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing E2E organisation and recreate",
        )

    def handle(self, *args, **options):
        """Execute the command."""
        if options["reset"]:
            self.stdout.write("Deleting existing E2E organisation...")
            Organisation.objects.filter(slug=E2E_ORG_SLUG).delete()
            self.stdout.write(self.style.WARNING("Deleted"))

        with transaction.atomic():
            org, created = Organisation.objects.get_or_create(
                slug=E2E_ORG_SLUG,
                defaults={
                    "name": E2E_ORG_NAME,
                    "default_review_mode": "DUAL",
                    "default_min_reviewers": 2,
                    "require_dual_review": True,
                    "max_active_reviews": None,
                    "max_users": None,
                },
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created organisation: {org.name}")
                )
            else:
                self.stdout.write(f"Organisation already exists: {org.name}")

            # Create reviewer users using unified convention
            reviewers = [
                ("e2e-reviewer1", "e2e-reviewer1@test.local", "Alice", "Reviewer"),
                ("e2e-reviewer2", "e2e-reviewer2@test.local", "Bob", "Reviewer"),
            ]

            for username, email, first_name, last_name in reviewers:
                try:
                    user = User.objects.get(email=email)
                    self.stdout.write(f"   User already exists: {user.username}")
                except User.DoesNotExist:
                    try:
                        user = User.objects.get(username=username)
                        user.email = email
                        user.save()
                        self.stdout.write(f"   Updated user email: {user.username}")
                    except User.DoesNotExist:
                        user = User.objects.create_user(
                            username=username,
                            email=email,
                            password=E2E_PASSWORD,
                            first_name=first_name,
                            last_name=last_name,
                        )
                        self.stdout.write(
                            self.style.SUCCESS(f"Created user: {user.username}")
                        )

                OrganisationMembership.objects.get_or_create(
                    organisation=org,
                    user=user,
                    defaults={
                        "role": OrganisationMembership.ROLE_REVIEWER,
                        "is_active": True,
                    },
                )

        # Summary
        self.stdout.write(self.style.SUCCESS("\nE2E Organisation Setup Complete"))
        self.stdout.write(f"   Organisation: {org.name} ({org.slug})")
        self.stdout.write(
            f"   Members: {org.memberships.filter(is_active=True).count()}"
        )
        self.stdout.write(f"   Review Mode: {org.default_review_mode}")
