"""
Django management command to fix migration state issues.

This command handles the specific case where the status_detail column
already exists in the database but the migration hasn't been marked as applied.

Usage:
    python manage.py fix_migration_state [--dry-run]
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = "Fix migration state for status_detail column that already exists"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        self.stdout.write(
            self.style.SUCCESS("Checking migration state for status_detail column...")
        )

        # Check if the column exists in the database
        column_exists = self._check_column_exists()

        # Check if the migration is recorded as applied
        migration_applied = self._check_migration_applied()

        self.stdout.write(f"Column exists in database: {column_exists}")
        self.stdout.write(f"Migration recorded as applied: {migration_applied}")

        if column_exists and not migration_applied:
            self.stdout.write(
                self.style.WARNING(
                    "Column exists but migration not recorded. This will cause migration conflicts."
                )
            )

            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        "DRY RUN: Would mark migration 0010_searchsession_status_detail as applied"
                    )
                )
            else:
                self._fake_apply_migration()
                self.stdout.write(
                    self.style.SUCCESS(
                        "Successfully marked migration 0010_searchsession_status_detail as applied"
                    )
                )
        elif not column_exists and migration_applied:
            self.stdout.write(
                self.style.ERROR(
                    "Migration recorded as applied but column does not exist! "
                    "You may need to revert and reapply the migration."
                )
            )
        elif column_exists and migration_applied:
            self.stdout.write(
                self.style.SUCCESS("Migration state is consistent. No action needed.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Column does not exist and migration not applied. "
                    "Normal migration can proceed."
                )
            )

    def _check_column_exists(self):
        """Check if status_detail column exists in the database"""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'review_manager_searchsession' 
                AND column_name = 'status_detail'
            """
            )
            return cursor.fetchone() is not None

    def _check_migration_applied(self):
        """Check if the migration is recorded as applied"""
        recorder = MigrationRecorder(connection)
        applied_migrations = recorder.applied_migrations()

        return (
            "review_manager",
            "0010_searchsession_status_detail",
        ) in applied_migrations

    def _fake_apply_migration(self):
        """Mark the migration as applied without running it"""
        recorder = MigrationRecorder(connection)
        recorder.record_applied("review_manager", "0010_searchsession_status_detail")

        self.stdout.write(
            "Migration 0010_searchsession_status_detail marked as applied in django_migrations table"
        )
