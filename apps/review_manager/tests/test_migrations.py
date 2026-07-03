"""
Tests for review_manager migrations.

These tests ensure migrations are idempotent, safe, and handle edge cases correctly.
Focus on migration 0013 which removes the tags column with full idempotency.
"""

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase


class Migration0013IdempotencyTest(TransactionTestCase):
    """
    Test migration 0013 idempotency and safety.

    Uses TransactionTestCase to allow schema modifications during tests.
    Each test method runs in isolation with a fresh database schema.
    """

    # Specify the app and migration to test
    migrate_from = "0012_increase_status_detail_length"
    migrate_to = "0013_remove_searchsession_tags"

    def setUp(self):
        """Set up test environment."""
        # Ensure we start from a clean state
        super().setUp()

    def tearDown(self):
        """Restore all migrations to latest after each test."""
        call_command("migrate", verbosity=0)
        super().tearDown()

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        """
        Check if a column exists in the specified table.

        Args:
            table_name: Name of the database table
            column_name: Name of the column to check

        Returns:
            True if column exists, False otherwise
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name=%s AND column_name=%s
                """,
                [table_name, column_name],
            )
            return cursor.fetchone() is not None

    def test_migration_0013_runs_successfully(self):
        """
        Test that migration 0013 runs without errors.

        This is the basic smoke test - ensures the migration
        can execute successfully in a standard scenario.
        """
        # Run migrations up to but not including 0013
        call_command(
            "migrate",
            "review_manager",
            "0012_increase_status_detail_length",
            verbosity=0,
        )

        # Verify starting state (column may or may not exist depending on database state)
        _column_exists_before = self._column_exists("search_sessions", "tags")

        # Run migration 0013
        call_command(
            "migrate", "review_manager", "0013_remove_searchsession_tags", verbosity=0
        )

        # Verify column is removed (regardless of whether it existed before)
        column_exists_after = self._column_exists("search_sessions", "tags")
        self.assertFalse(
            column_exists_after, "Tags column should not exist after migration 0013"
        )

    def test_migration_0013_is_idempotent(self):
        """
        Test that migration 0013 can run multiple times without errors.

        Idempotency is critical for:
        - CI/CD pipelines that may run migrations multiple times
        - Development databases in various states
        - Rollback/forward migration cycles
        """
        # Run migrations up to 0013
        call_command(
            "migrate", "review_manager", "0013_remove_searchsession_tags", verbosity=0
        )

        # Verify column doesn't exist
        self.assertFalse(
            self._column_exists("search_sessions", "tags"),
            "Tags column should not exist after first run",
        )

        # Run migration again by rolling back and re-applying
        # This simulates a scenario where the migration runs multiple times
        call_command(
            "migrate",
            "review_manager",
            "0012_increase_status_detail_length",
            verbosity=0,
        )
        call_command(
            "migrate", "review_manager", "0013_remove_searchsession_tags", verbosity=0
        )

        # Verify column still doesn't exist and no errors occurred
        self.assertFalse(
            self._column_exists("search_sessions", "tags"),
            "Tags column should not exist after second run",
        )

    def test_migration_0013_handles_missing_column_gracefully(self):
        """
        Test migration 0013 when column is already missing.

        This scenario occurs in:
        - Fresh test databases where previous migrations already removed the column
        - Production databases where column was manually removed
        - Databases with squashed migrations
        """
        # Run migrations up to 0013
        call_command(
            "migrate", "review_manager", "0013_remove_searchsession_tags", verbosity=0
        )

        # Verify column doesn't exist
        self.assertFalse(
            self._column_exists("search_sessions", "tags"),
            "Tags column should not exist",
        )

        # Manually ensure column doesn't exist (simulating pre-removed state)
        with connection.cursor() as cursor:
            # This query will succeed even if column doesn't exist (using IF EXISTS)
            cursor.execute(
                'ALTER TABLE "search_sessions" DROP COLUMN IF EXISTS "tags" CASCADE'
            )

        # Run migration 0013 again - should handle missing column gracefully
        call_command(
            "migrate",
            "review_manager",
            "0012_increase_status_detail_length",
            verbosity=0,
        )
        call_command(
            "migrate", "review_manager", "0013_remove_searchsession_tags", verbosity=0
        )

        # Verify no errors occurred and column is still not present
        self.assertFalse(
            self._column_exists("search_sessions", "tags"),
            "Tags column should not exist after migration with missing column",
        )

    def test_migration_0013_removes_column_cascade(self):
        """
        Test that migration removes column with CASCADE.

        This ensures any dependent objects (indexes, constraints) are
        also removed, preventing orphaned database objects.
        """
        # Run migrations up to 0013
        call_command(
            "migrate", "review_manager", "0013_remove_searchsession_tags", verbosity=0
        )

        # Verify column doesn't exist
        self.assertFalse(
            self._column_exists("search_sessions", "tags"),
            "Tags column should be removed",
        )

        # Check for any orphaned indexes related to tags column
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'search_sessions'
                AND indexname LIKE '%tags%'
                """
            )
            orphaned_indexes = cursor.fetchall()

        # Verify no orphaned indexes remain
        self.assertEqual(
            len(orphaned_indexes),
            0,
            f"Found orphaned indexes after migration: {orphaned_indexes}",
        )


class Migration0013RollbackTest(TransactionTestCase):
    """
    Test rollback behaviour of migration 0013.

    The migration uses migrations.RunPython.noop for reverse,
    so rollback should be a no-op (safe but doesn't restore column).
    """

    def tearDown(self):
        """Restore all migrations to latest after each test."""
        call_command("migrate", verbosity=0)
        super().tearDown()

    def test_migration_0013_rollback_is_safe(self):
        """
        Test that rolling back migration 0013 doesn't cause errors.

        The reverse operation is a no-op, which is appropriate for
        a data migration that can't safely restore removed data.
        """
        # Run migrations up to 0013
        call_command(
            "migrate", "review_manager", "0013_remove_searchsession_tags", verbosity=0
        )

        # Rollback to 0012
        call_command(
            "migrate",
            "review_manager",
            "0012_increase_status_detail_length",
            verbosity=0,
        )

        # Verify rollback completed without errors
        # The column will not be restored (no-op reverse), which is expected
        # We're just checking that the rollback doesn't crash
        self.assertTrue(True, "Rollback completed successfully")


class MigrationTestCase(TestCase):
    """
    General migration tests for review_manager app.

    These tests verify overall migration health and compatibility.
    """

    def test_all_migrations_have_dependencies(self):
        """
        Test that all migrations have proper dependencies.

        This ensures migration order is deterministic and prevents
        migration conflicts.
        """
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(connection)
        graph = loader.graph

        # Get all review_manager migrations
        review_manager_migrations = [
            node for node in graph.nodes if node[0] == "review_manager"
        ]

        # Verify each migration (except the first) has at least one dependency
        for migration_name in review_manager_migrations:
            migration = graph.nodes[migration_name]
            if migration_name[1] != "0001_initial":
                self.assertTrue(
                    len(migration.dependencies) > 0,
                    f"Migration {migration_name} has no dependencies",
                )

    def test_migration_0013_exists_and_is_accessible(self):
        """
        Test that migration 0013 exists and can be loaded.

        This is a basic sanity check that the migration file is
        properly formatted and importable.
        """
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(connection)

        # Check migration 0013 exists
        migration_key = ("review_manager", "0013_remove_searchsession_tags")
        self.assertIn(
            migration_key, loader.graph.nodes, "Migration 0013 should exist in graph"
        )

        # Verify migration can be loaded
        migration = loader.graph.nodes[migration_key]
        self.assertIsNotNone(migration, "Migration 0013 should be loadable")

    def test_migration_0013_has_correct_dependency(self):
        """
        Test that migration 0013 depends on 0012 as expected.

        This ensures the migration order is correct and prevents
        potential migration conflicts.
        """
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(connection)
        migration_key = ("review_manager", "0013_remove_searchsession_tags")

        migration = loader.graph.nodes[migration_key]

        # Check dependencies
        dependencies = [
            dep for dep in migration.dependencies if dep[0] == "review_manager"
        ]

        self.assertEqual(
            len(dependencies),
            1,
            "Migration 0013 should have exactly one review_manager dependency",
        )
        self.assertEqual(
            dependencies[0][1],
            "0012_increase_status_detail_length",
            "Migration 0013 should depend on 0012",
        )
