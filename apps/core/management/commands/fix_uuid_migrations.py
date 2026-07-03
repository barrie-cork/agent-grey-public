"""
Management command to fix the recurring UUID migration issue in the core app.

This command properly handles the Django migration state inconsistency caused by
the complex raw SQL migration 0005 that Django's migration system doesn't fully track.
"""

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = """
    Fix the recurring UUID migration issue for the core.Configuration model.

    This command resets the migration state and creates a proper UUID migration
    that Django's migration system can fully track, eliminating the recurring
    "multiple primary keys" PostgreSQL errors.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force the operation even if database has data",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🔧 Starting UUID Migration Fix Process"))

        # Check if this is a dry run
        dry_run = options["dry_run"]
        force = options["force"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("🔍 DRY RUN MODE - No changes will be made")
            )

        # Step 1: Analyze current state
        self.stdout.write("\n📊 Step 1: Analyzing current migration state...")
        self._check_current_state()

        # Step 2: Check data safety
        self.stdout.write("\n🛡️  Step 2: Checking data safety...")
        data_count = self._check_data_safety()

        if data_count > 0 and not force:
            self.stdout.write(
                self.style.ERROR(
                    f"⚠️  Database contains {data_count} Configuration records. "
                    "This operation will reset migration state but preserve data. "
                    "Use --force to proceed or backup your data first."
                )
            )
            return

        # Step 3: Reset migration state
        if not dry_run:
            self.stdout.write("\n🔄 Step 3: Resetting migration state...")
            self._reset_migration_state()
        else:
            self.stdout.write("\n🔄 Step 3: Would reset migration state")

        # Step 4: Create proper migration
        self.stdout.write("\n📝 Step 4: Creating proper UUID migration...")
        if not dry_run:
            self._create_proper_migration()
        else:
            self.stdout.write("Would create new migration 0005")

        # Step 5: Apply new migration
        if not dry_run:
            self.stdout.write("\n⚡ Step 5: Applying new migration...")
            self._apply_new_migration()
        else:
            self.stdout.write("\n⚡ Step 5: Would apply new migration")

        self.stdout.write(self.style.SUCCESS("\n✅ UUID Migration Fix Complete!"))

        # Final verification
        self.stdout.write("\n🔍 Final verification...")
        self._verify_fix()

    def _check_current_state(self):
        """Check the current state of migrations and database schema."""
        with connection.cursor() as cursor:
            # Check migration recorder
            cursor.execute(
                """
                SELECT name FROM django_migrations
                WHERE app = 'core'
                ORDER BY name
            """
            )
            applied_migrations = [row[0] for row in cursor.fetchall()]

            self.stdout.write(f"📋 Applied migrations: {len(applied_migrations)}")
            for migration in applied_migrations:
                self.stdout.write(f"   - {migration}")

            # Check table schema
            cursor.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'core_configuration'
                ORDER BY ordinal_position
            """
            )
            columns = cursor.fetchall()

            self.stdout.write(f"📋 Table schema ({len(columns)} columns):")
            for col_name, data_type, nullable in columns:
                self.stdout.write(
                    f"   - {col_name}: {data_type} {'NULL' if nullable == 'YES' else 'NOT NULL'}"
                )

    def _check_data_safety(self):
        """Check if there's existing data that needs to be preserved."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM core_configuration")
            count = cursor.fetchone()[0]

            if count > 0:
                self.stdout.write(f"📊 Found {count} existing Configuration records")
                cursor.execute("SELECT key FROM core_configuration LIMIT 5")
                sample_keys = [row[0] for row in cursor.fetchall()]
                self.stdout.write(f"📋 Sample keys: {sample_keys}")
            else:
                self.stdout.write("📊 No existing data found")

            return count

    def _reset_migration_state(self):
        """Reset the migration state in django_migrations table."""
        recorder = MigrationRecorder(connection)

        with transaction.atomic():
            # Remove migrations 0005-0009 from the recorder
            migrations_to_remove = [
                "0005_configuration_uuid_transition",
                "0006_auto_20250814_1052",
                "0007_alter_configuration_id",
                "0008_alter_configuration_id",
                "0009_alter_configuration_id",
            ]

            for migration_name in migrations_to_remove:
                recorder.record_unapplied("core", migration_name)
                self.stdout.write(
                    f"📤 Removed {migration_name} from migration recorder"
                )

    def _create_proper_migration(self):
        """Create a proper Django migration to replace the raw SQL approach."""
        migration_content = '''# Generated by fix_uuid_migrations command
# Replaces the problematic raw SQL migration with proper Django operations

import uuid
from django.db import migrations, models


def populate_uuid_values(apps, schema_editor):
    """Populate UUID values for existing Configuration records."""
    Configuration = apps.get_model('core', 'Configuration')

    for config in Configuration.objects.all():
        if not config.temp_uuid_id:
            config.temp_uuid_id = uuid.uuid4()
            config.save(update_fields=['temp_uuid_id'])


def reverse_uuid_population(apps, schema_editor):
    """Reverse operation - nothing to do as we'll be dropping the field."""
    pass


class Migration(migrations.Migration):
    """
    Proper UUID primary key migration using Django operations.

    This migration replaces the raw SQL approach in the original migration 0005
    with proper Django operations that the migration system can fully track.
    """

    dependencies = [
        ('core', '0004_configuration_created_at'),
    ]

    operations = [
        # Step 1: Add temporary UUID field (not primary key yet)
        migrations.AddField(
            model_name='configuration',
            name='temp_uuid_id',
            field=models.UUIDField(default=uuid.uuid4, null=True),
        ),

        # Step 2: Populate UUID values for existing records
        migrations.RunPython(populate_uuid_values, reverse_uuid_population),

        # Step 3: Make UUID field non-nullable
        migrations.AlterField(
            model_name='configuration',
            name='temp_uuid_id',
            field=models.UUIDField(default=uuid.uuid4),
        ),

        # Step 4: Remove the old integer primary key field
        migrations.RemoveField(
            model_name='configuration',
            name='id',
        ),

        # Step 5: Rename temp_uuid_id to id (becomes primary key via model definition)
        migrations.RenameField(
            model_name='configuration',
            old_name='temp_uuid_id',
            new_name='id',
        ),

        # Step 6: Update other fields to match current model state
        migrations.AlterField(
            model_name='configuration',
            name='value',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Configuration value (JSON format)'
            ),
        ),
    ]
'''

        # Write the new migration file
        migration_path = "apps/core/migrations/0005_configuration_uuid_proper.py"

        # First remove old problematic migrations
        old_migrations = [
            "apps/core/migrations/0005_configuration_uuid_transition.py",
            "apps/core/migrations/0006_auto_20250814_1052.py",
            "apps/core/migrations/0007_alter_configuration_id.py",
            "apps/core/migrations/0008_alter_configuration_id.py",
            "apps/core/migrations/0009_alter_configuration_id.py",
        ]

        for old_migration in old_migrations:
            if os.path.exists(old_migration):
                os.remove(old_migration)
                self.stdout.write(f"🗑️  Removed {old_migration}")

        # Write new migration
        with open(migration_path, "w") as f:
            f.write(migration_content)

        self.stdout.write(f"📝 Created new migration: {migration_path}")

    def _apply_new_migration(self):
        """Apply the new migration using Django's migrate command."""
        from django.core.management import call_command

        try:
            # Apply the new migration
            call_command("migrate", "core", verbosity=1)
            self.stdout.write("✅ New migration applied successfully")
        except Exception as e:
            raise CommandError(f"Failed to apply migration: {str(e)}")

    def _verify_fix(self):
        """Verify that the fix worked and no more migrations are needed."""
        from io import StringIO

        from django.core.management import call_command

        # Check if makemigrations detects any changes
        out = StringIO()
        try:
            call_command("makemigrations", "--check", stdout=out, stderr=out)
            self.stdout.write("✅ No pending migrations detected")
        except SystemExit:
            # makemigrations --check exits with code 1 if changes are detected
            self.stdout.write(
                "⚠️  Still detecting pending migrations - check output above"
            )

        # Show current migration status
        self.stdout.write("\n📋 Final migration status:")
        call_command("showmigrations", "core")
