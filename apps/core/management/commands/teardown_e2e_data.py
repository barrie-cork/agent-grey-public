"""
Management command to tear down all E2E test data.

Deletes all data created by E2E test infrastructure (create_e2e_users,
setup_e2e_session) using safe pattern matching. Idempotent -- safe to
run multiple times.

Deletion order (respects FK dependencies, including PROTECT FKs):
    1. Null out current_configuration on E2E sessions (breaks circular PROTECT)
    2. Delete ReviewConfiguration records for E2E sessions
    3. Delete SearchSessions with 'E2E' in title OR owned by e2e- users
       (cascades to strategy, queries, executions, raw results, processed
       results, decisions, conflicts, invitations, completions)
    4. Organisation memberships for e2e- users
    5. Organisations (e2e-test-org slug OR slug starting with e2e-)
    6. Users with e2e- username prefix

Usage:
    # Dry run (show what would be deleted)
    docker-compose exec -T web python manage.py teardown_e2e_data --dry-run

    # Actual teardown
    docker-compose exec -T web python manage.py teardown_e2e_data
"""

from typing import Any

from django.core.management.base import BaseCommand
from django.db import models, transaction

from apps.accounts.management.commands.create_e2e_users import E2E_ORG_SLUG


class Command(BaseCommand):
    help = "Delete all E2E test data (users, sessions, organisation)"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\n=== DRY RUN: Teardown E2E Data ===\n")
            )
        else:
            self.stdout.write(self.style.WARNING("\n=== Teardown E2E Data ===\n"))

        counts = self._collect_counts()
        self._report_counts(counts)

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDry run complete. No data was deleted.\n")
            )
            return

        if all(v == 0 for v in counts.values()):
            self.stdout.write(
                self.style.SUCCESS("\nNo E2E data found. Nothing to delete.\n")
            )
            return

        self._delete_all()
        self.stdout.write(self.style.SUCCESS("\nE2E data teardown complete.\n"))

    def _collect_counts(self) -> dict[str, int]:
        """Count E2E records that would be deleted."""
        from django.contrib.auth import get_user_model

        from apps.organisation.models import Organisation, OrganisationMembership
        from apps.review_manager.models import SearchSession

        User = get_user_model()

        sessions = SearchSession.objects.filter(
            models.Q(title__icontains="e2e")
            | models.Q(owner__username__startswith="e2e-")
        )
        users = User.objects.filter(username__startswith="e2e-")
        memberships = OrganisationMembership.objects.filter(
            user__username__startswith="e2e-"
        )
        orgs = Organisation.objects.filter(
            models.Q(slug=E2E_ORG_SLUG) | models.Q(slug__startswith="e2e-")
        )

        return {
            "sessions": sessions.count(),
            "users": users.count(),
            "memberships": memberships.count(),
            "organisations": orgs.count(),
        }

    def _report_counts(self, counts: dict[str, int]) -> None:
        """Display what will be deleted."""
        self.stdout.write(f"  Sessions (E2E title or e2e- owner): {counts['sessions']}")
        self.stdout.write(f"  Users (username starts 'e2e-'):   {counts['users']}")
        self.stdout.write(
            f"  Memberships (e2e- users):         {counts['memberships']}"
        )
        self.stdout.write(
            f"  Organisations (slug={E2E_ORG_SLUG}): {counts['organisations']}"
        )

    @transaction.atomic
    def _delete_all(self) -> None:
        """Delete all E2E data in FK-safe order."""
        from django.contrib.auth import get_user_model

        from apps.organisation.models import Organisation, OrganisationMembership
        from apps.review_manager.models import ReviewConfiguration, SearchSession

        User = get_user_model()

        e2e_sessions = SearchSession.objects.filter(
            models.Q(title__icontains="e2e")
            | models.Q(owner__username__startswith="e2e-")
        )

        # 1. Break circular PROTECT: null out current_configuration FK
        e2e_sessions.update(current_configuration=None)
        self.stdout.write("  Cleared current_configuration on E2E sessions")

        # 2. Delete ReviewConfiguration records (was PROTECT-blocking session deletion)
        deleted_configs = ReviewConfiguration.objects.filter(
            session__in=e2e_sessions
        ).delete()
        self.stdout.write(
            f"  Deleted configurations: {deleted_configs[0]} objects total"
        )

        # 3. Delete sessions (cascade handles related objects)
        deleted_sessions = e2e_sessions.delete()
        self.stdout.write(f"  Deleted sessions: {deleted_sessions[0]} objects total")

        # 4. Delete memberships (before users and orgs)
        deleted_memberships = OrganisationMembership.objects.filter(
            user__username__startswith="e2e-"
        ).delete()
        self.stdout.write(
            f"  Deleted memberships: {deleted_memberships[0]} objects total"
        )

        # 5. Delete organisations (E2E org + personal orgs of e2e- users)
        deleted_orgs = Organisation.objects.filter(
            models.Q(slug=E2E_ORG_SLUG) | models.Q(slug__startswith="e2e-")
        ).delete()
        self.stdout.write(f"  Deleted organisations: {deleted_orgs[0]} objects total")

        # 6. Delete users (after sessions and orgs are gone)
        deleted_users = User.objects.filter(username__startswith="e2e-").delete()
        self.stdout.write(f"  Deleted users: {deleted_users[0]} objects total")
