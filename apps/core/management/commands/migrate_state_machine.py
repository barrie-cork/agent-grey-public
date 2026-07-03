"""
Management command for controlling state machine migration.

Usage:
    python manage.py migrate_state_machine enable
    python manage.py migrate_state_machine disable
    python manage.py migrate_state_machine status
    python manage.py migrate_state_machine validate
    python manage.py migrate_state_machine rollout --percentage=25
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Configuration
from apps.review_manager.models import SearchSession

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Manage state machine migration."""

    help = "Control event-driven state machine migration"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "action",
            choices=["enable", "disable", "status", "validate", "rollout"],
            help="Action to perform",
        )
        parser.add_argument(
            "--percentage",
            type=int,
            default=0,
            help="Rollout percentage (0-100) for gradual migration",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without applying them",
        )

    def handle(self, *args, **options):
        """Handle the command."""
        action = options["action"]
        dry_run = options.get("dry_run", False)

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        if action == "enable":
            self.enable_new_system(dry_run)
        elif action == "disable":
            self.disable_new_system(dry_run)
        elif action == "status":
            self.show_status()
        elif action == "validate":
            self.validate_system()
        elif action == "rollout":
            percentage = options["percentage"]
            self.gradual_rollout(percentage, dry_run)

    def enable_new_system(self, dry_run=False):
        """Enable the new event-driven state machine."""
        self.stdout.write("Enabling event-driven state machine...")

        if not dry_run:
            with transaction.atomic():
                # Set feature flags
                Configuration.set_config("use_event_driven_state_machine", True)
                Configuration.set_config("use_sse_instead_of_websocket", True)
                Configuration.set_config("state_machine_rollout_percentage", 100)

                # Log the change
                Configuration.set_config(
                    "state_machine_migration_status",
                    {
                        "enabled": True,
                        "enabled_at": timezone.now().isoformat(),
                        "enabled_by": "migrate_state_machine command",
                    },
                )

        self.stdout.write(self.style.SUCCESS("✓ Event-driven state machine enabled"))
        self.stdout.write(self.style.SUCCESS("✓ SSE enabled instead of WebSocket"))
        self.stdout.write(self.style.SUCCESS("✓ Rollout percentage set to 100%"))

        # Show validation
        self.validate_system()

    def disable_new_system(self, dry_run=False):
        """Disable the new event-driven state machine."""
        self.stdout.write("Disabling event-driven state machine...")

        # Check for active sessions
        active_sessions = SearchSession.objects.filter(
            status__in=["executing", "processing_results"]
        ).count()

        if active_sessions > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠ Warning: {active_sessions} sessions are currently active"
                )
            )
            if not dry_run:
                response = input("Continue with disable? (y/N): ")
                if response.lower() != "y":
                    self.stdout.write(self.style.ERROR("Aborted"))
                    return

        if not dry_run:
            with transaction.atomic():
                # Disable feature flags
                Configuration.set_config("use_event_driven_state_machine", False)
                Configuration.set_config("use_sse_instead_of_websocket", False)
                Configuration.set_config("state_machine_rollout_percentage", 0)

                # Log the change
                Configuration.set_config(
                    "state_machine_migration_status",
                    {
                        "enabled": False,
                        "disabled_at": timezone.now().isoformat(),
                        "disabled_by": "migrate_state_machine command",
                    },
                )

        self.stdout.write(self.style.SUCCESS("✓ Event-driven state machine disabled"))
        self.stdout.write(self.style.SUCCESS("✓ WebSocket re-enabled"))
        self.stdout.write(self.style.SUCCESS("✓ Using legacy state management"))

    def show_status(self):
        """Show current migration status."""
        self.stdout.write(self.style.MIGRATE_HEADING("Current Migration Status"))
        self.stdout.write("-" * 50)

        # Get feature flags
        use_event_system = Configuration.get_config(
            "use_event_driven_state_machine", False
        )
        use_sse = Configuration.get_config("use_sse_instead_of_websocket", False)
        rollout_percentage = Configuration.get_config(
            "state_machine_rollout_percentage", 0
        )
        migration_status = Configuration.get_config(
            "state_machine_migration_status", {}
        )

        # Display status
        self.stdout.write(
            f"Event-Driven System: {self._format_enabled(use_event_system)}"
        )
        self.stdout.write(f"SSE Instead of WebSocket: {self._format_enabled(use_sse)}")
        self.stdout.write(f"Rollout Percentage: {rollout_percentage}%")

        if migration_status:
            self.stdout.write("")
            self.stdout.write("Migration History:")
            if migration_status.get("enabled"):
                self.stdout.write(
                    f"  Enabled at: {migration_status.get('enabled_at', 'Unknown')}"
                )
            if not migration_status.get("enabled"):
                self.stdout.write(
                    f"  Disabled at: {migration_status.get('disabled_at', 'Unknown')}"
                )

        # Show session statistics
        self.stdout.write("")
        self.stdout.write("Session Statistics:")
        total_sessions = SearchSession.objects.count()
        active_sessions = SearchSession.objects.filter(
            status__in=["executing", "processing_results"]
        ).count()
        self.stdout.write(f"  Total sessions: {total_sessions}")
        self.stdout.write(f"  Active sessions: {active_sessions}")

    def validate_system(self):
        """Validate system health and configuration."""
        self.stdout.write(self.style.MIGRATE_HEADING("System Validation"))
        self.stdout.write("-" * 50)

        errors = []
        warnings = []

        # Run validation checks
        self._check_feature_flags(warnings)
        self._check_stuck_sessions(warnings)
        self._check_cache_availability(errors)
        self._check_channels_availability(warnings)

        # Display results
        self._display_validation_results(errors, warnings)

        return len(errors) == 0

    def _check_feature_flags(self, warnings):
        """Check feature flag consistency."""
        use_event_system = Configuration.get_config(
            "use_event_driven_state_machine", False
        )
        use_sse = Configuration.get_config("use_sse_instead_of_websocket", False)

        if use_event_system and not use_sse:
            warnings.append("Event system enabled but SSE disabled - may cause issues")

    def _check_stuck_sessions(self, warnings):
        """Check for stuck sessions."""
        from datetime import timedelta

        stuck_threshold = timezone.now() - timedelta(hours=1)
        stuck_sessions = SearchSession.objects.filter(
            status="executing", updated_at__lt=stuck_threshold
        ).count()

        if stuck_sessions > 0:
            warnings.append(
                f"{stuck_sessions} sessions may be stuck in executing state"
            )

    def _check_cache_availability(self, errors):
        """Check cache availability."""
        from django.core.cache import cache

        try:
            cache.set("migration_test", "test", 1)
            if cache.get("migration_test") != "test":
                errors.append("Cache not working properly")
            cache.delete("migration_test")
            self.stdout.write(self.style.SUCCESS("✓ Cache operational"))
        except Exception as e:
            errors.append(f"Cache error: {str(e)}")

    def _check_channels_availability(self, warnings):
        """Check Channels availability (for WebSocket fallback)."""
        try:
            from channels.layers import get_channel_layer  # type: ignore[reportMissingModuleSource]

            channel_layer = get_channel_layer()
            if channel_layer:
                self.stdout.write(self.style.SUCCESS("✓ Channels configured"))
            else:
                warnings.append("No channel layer configured - WebSocket disabled")
        except ImportError:
            warnings.append("Channels not installed - WebSocket unavailable")

    def _display_validation_results(self, errors, warnings):
        """Display validation results."""
        if errors:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("ERRORS:"))
            for error in errors:
                self.stdout.write(self.style.ERROR(f"  ✗ {error}"))

        if warnings:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("WARNINGS:"))
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f"  ⚠ {warning}"))

        if not errors and not warnings:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("✓ All systems operational"))

    def gradual_rollout(self, percentage, dry_run=False):
        """Gradually roll out the new system."""
        if percentage < 0 or percentage > 100:
            raise CommandError("Percentage must be between 0 and 100")

        self.stdout.write(f"Setting rollout percentage to {percentage}%...")

        if not dry_run:
            Configuration.set_config("state_machine_rollout_percentage", percentage)

            # Enable/disable based on percentage
            if percentage > 0:
                Configuration.set_config("use_event_driven_state_machine", True)
                if percentage >= 50:
                    Configuration.set_config("use_sse_instead_of_websocket", True)
            else:
                Configuration.set_config("use_event_driven_state_machine", False)
                Configuration.set_config("use_sse_instead_of_websocket", False)

        self.stdout.write(self.style.SUCCESS(f"✓ Rollout set to {percentage}%"))

        if percentage == 0:
            self.stdout.write("→ New system disabled")
        elif percentage < 50:
            self.stdout.write("→ New state machine enabled, WebSocket still active")
        elif percentage < 100:
            self.stdout.write("→ New state machine and SSE enabled for partial users")
        else:
            self.stdout.write("→ Full migration to new system")

    def _format_enabled(self, value):
        """Format enabled/disabled status."""
        if value:
            return self.style.SUCCESS("ENABLED")
        return self.style.WARNING("DISABLED")
