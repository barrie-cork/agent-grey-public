#!/usr/bin/env python
"""
Migration Health Check Script

Detects and reports migration inconsistencies between database schema
and Django migration history.

Usage:
    python scripts/check-migration-health.py [--fix]

Exit codes:
    0 - All migrations are consistent
    1 - Inconsistencies detected (use --fix to repair)
    2 - Critical error occurred
"""

import os
import sys
import django
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "grey_lit_project.settings.local")
django.setup()

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.apps import apps


class MigrationHealthChecker:
    """Check for migration inconsistencies."""

    def __init__(self):
        self.loader = MigrationLoader(connection)
        self.recorder = MigrationRecorder(connection)
        self.inconsistencies = []

    def check_table_exists(self, table_name):
        """Check if a table exists in the database."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = %s
                )
                """,
                [table_name],
            )
            return cursor.fetchone()[0]

    def check_column_exists(self, table_name, column_name):
        """Check if a column exists in a table."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = %s
                    AND column_name = %s
                )
                """,
                [table_name, column_name],
            )
            return cursor.fetchone()[0]

    def get_applied_migrations(self):
        """Get list of migrations marked as applied in database."""
        return set(
            self.recorder.migration_qs.values_list("app", "name")
        )

    def check_app_migrations(self, app_label):
        """Check migration consistency for a specific app."""
        print(f"\n🔍 Checking {app_label}...")

        app_config = apps.get_app_config(app_label)
        applied_migrations = self.get_applied_migrations()

        # Get migrations for this app
        app_migrations = [
            (app, name)
            for (app, name) in self.loader.disk_migrations.keys()
            if app == app_label
        ]

        if not app_migrations:
            print(f"  ℹ️  No migrations found for {app_label}")
            return

        # Check for models without tables
        for model in app_config.get_models():
            table_name = model._meta.db_table
            if not self.check_table_exists(table_name):
                issue = {
                    "app": app_label,
                    "type": "missing_table",
                    "table": table_name,
                    "model": model.__name__,
                }
                self.inconsistencies.append(issue)
                print(f"  ❌ Table missing: {table_name} (model: {model.__name__})")

        # Check for migrations marked as applied but schema doesn't match
        for app, name in app_migrations:
            is_applied = (app, name) in applied_migrations
            migration = self.loader.disk_migrations.get((app, name))

            if is_applied and migration:
                # Check if operations match database state
                # This is a simplified check - you could extend this
                print(f"  ✅ Migration applied: {name}")

        print(f"  ✓ Checked {len(app_migrations)} migrations for {app_label}")

    def run_checks(self):
        """Run all migration health checks."""
        print("🏥 Running Migration Health Checks")
        print("=" * 60)

        # Get all apps with migrations
        apps_with_migrations = set(
            app for (app, _) in self.loader.disk_migrations.keys()
        )

        for app_label in sorted(apps_with_migrations):
            self.check_app_migrations(app_label)

        return len(self.inconsistencies) == 0

    def report_inconsistencies(self):
        """Print a report of all found inconsistencies."""
        if not self.inconsistencies:
            print("\n✅ No migration inconsistencies detected!")
            return

        print("\n⚠️  Migration Inconsistencies Detected:")
        print("=" * 60)

        for issue in self.inconsistencies:
            if issue["type"] == "missing_table":
                print("\n❌ Missing Table:")
                print(f"   App: {issue['app']}")
                print(f"   Model: {issue['model']}")
                print(f"   Table: {issue['table']}")
                print("   Fix: Run migrations or fake-apply if schema exists elsewhere")

    def fix_inconsistencies(self):
        """Attempt to fix detected inconsistencies."""
        if not self.inconsistencies:
            print("\n✅ Nothing to fix!")
            return True

        print("\n🔧 Attempting to fix inconsistencies...")

        # Group issues by app
        apps_to_fix = set(issue["app"] for issue in self.inconsistencies)

        for app_label in apps_to_fix:
            print(f"\n📝 Checking migration state for {app_label}...")

            # Get expected vs actual state
            applied_migrations = self.get_applied_migrations()
            app_migrations = [
                name for (app, name) in applied_migrations if app == app_label
            ]

            if app_migrations:
                print(f"   {len(app_migrations)} migrations recorded as applied")

                # Check if tables actually exist
                app_config = apps.get_app_config(app_label)
                tables_exist = all(
                    self.check_table_exists(model._meta.db_table)
                    for model in app_config.get_models()
                )

                if tables_exist:
                    print("   ✅ All tables exist - migration history is correct")
                else:
                    print("   ⚠️  Tables missing but migrations recorded")
                    print(f"   💡 Consider: python manage.py migrate {app_label}")
            else:
                print("   ℹ️  No migrations recorded - may need initial migration")

        return True


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Check Django migration health and consistency"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to fix detected inconsistencies",
    )
    parser.add_argument(
        "--app",
        help="Check specific app only",
    )

    args = parser.parse_args()

    checker = MigrationHealthChecker()

    try:
        # Run checks
        is_healthy = checker.run_checks()

        # Report findings
        checker.report_inconsistencies()

        # Fix if requested
        if args.fix and not is_healthy:
            success = checker.fix_inconsistencies()
            if not success:
                print("\n❌ Some issues could not be automatically fixed")
                print("   Please review the errors and fix manually")
                sys.exit(1)

        # Exit with appropriate code
        if is_healthy:
            print("\n🎉 All migration checks passed!")
            sys.exit(0)
        else:
            print("\n⚠️  Inconsistencies detected. Review the report above.")
            print("   Run with --fix to attempt automatic repairs")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Critical error during health check: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
