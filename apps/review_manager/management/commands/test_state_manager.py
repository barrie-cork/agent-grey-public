"""
Management command to test the state management system.

Usage:
    python manage.py test_state_manager --session-id <uuid> --transition <status>
    python manage.py test_state_manager --diagnose <uuid>
    python manage.py test_state_manager --recover-stuck
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.review_manager.models import SearchSession
from apps.review_manager.services.recovery_manager import WorkflowRecoveryManager
from apps.review_manager.services.state_manager import (
    SessionStateManager,
    StateTransitionError,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Test and debug the workflow state management system"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--session-id", type=str, help="UUID of the session to test"
        )

        parser.add_argument(
            "--transition",
            type=str,
            choices=[status[0] for status in SearchSession.STATUS_CHOICES],
            help="Target status to transition to",
        )

        parser.add_argument(
            "--force",
            action="store_true",
            help="Force the transition (bypass validation)",
        )

        parser.add_argument(
            "--diagnose",
            type=str,
            help="Get diagnostics for a session (provide session ID)",
        )

        parser.add_argument(
            "--recover-stuck",
            action="store_true",
            help="Run recovery process for all stuck sessions",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def handle(self, *args, **options):
        """Handle the command."""
        if options["recover_stuck"]:
            self._handle_recovery(options["dry_run"])
        elif options["diagnose"]:
            self._handle_diagnostics(options["diagnose"])
        elif options["session_id"] and options["transition"]:
            self._handle_transition(
                options["session_id"],
                options["transition"],
                options["force"],
                options["dry_run"],
            )
        else:
            raise CommandError(
                "Please provide either --recover-stuck, --diagnose <id>, "
                "or both --session-id and --transition"
            )

    def _handle_transition(self, session_id, target_status, force, dry_run):
        """Test a state transition."""
        session = self._get_session(session_id)
        state_manager = SessionStateManager(session)

        self._display_session_info(session, target_status)

        if not force and not self._check_transition_allowed(
            state_manager, target_status
        ):
            return

        if dry_run:
            self._perform_dry_run(state_manager, session, target_status)
            return

        self._execute_transition(state_manager, target_status, force, session)

    def _get_session(self, session_id):
        """Get session by ID or raise error."""
        try:
            return SearchSession.objects.get(id=session_id)
        except SearchSession.DoesNotExist:
            raise CommandError(f"Session {session_id} not found")

    def _display_session_info(self, session, target_status):
        """Display session and target status information."""
        self.stdout.write(f"\nSession: {session.title}")
        self.stdout.write(
            f"Current status: {session.status} ({session.get_status_display()})"
        )
        self.stdout.write(f"Target status: {target_status}")

    def _check_transition_allowed(self, state_manager, target_status):
        """Check if transition is allowed and display results."""
        allowed = state_manager.get_allowed_transitions()
        self.stdout.write(f"Allowed transitions: {', '.join(allowed)}")

        if target_status not in allowed:
            self.stdout.write(
                self.style.ERROR(
                    f"Transition to '{target_status}' not allowed. "
                    f"Use --force to override."
                )
            )
            return False
        return True

    def _perform_dry_run(self, state_manager, session, target_status):
        """Perform dry run validation."""
        self.stdout.write(self.style.WARNING("\nDRY RUN - No changes will be made"))

        is_valid, error = state_manager.validate_transition(session, target_status)

        if is_valid:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Transition would succeed: {session.status} -> {target_status}"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"Transition would fail validation: {error}")
            )

    def _execute_transition(self, state_manager, target_status, force, session):
        """Execute the state transition."""
        try:
            if force:
                self._execute_force_transition(state_manager, target_status, session)
            else:
                self._execute_normal_transition(state_manager, target_status)
        except StateTransitionError as e:
            self.stdout.write(self.style.ERROR(f"Transition failed: {str(e)}"))

    def _execute_force_transition(self, state_manager, target_status, session):
        """Execute forced transition."""
        success = state_manager.force_transition(
            target_status, reason="Manual test via management command"
        )
        if success:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Force transition successful: {session.status} -> {target_status}"
                )
            )
        else:
            self.stdout.write(self.style.ERROR("Force transition failed"))

    def _execute_normal_transition(self, state_manager, target_status):
        """Execute normal transition."""
        state_manager.transition_to(
            target_status, metadata={"source": "management_command"}
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Transition successful: "
                f"{state_manager.session.status} -> {target_status}"
            )
        )

    def _handle_diagnostics(self, session_id):
        """Get diagnostics for a session."""
        recovery_manager = WorkflowRecoveryManager()
        diagnostics = recovery_manager.get_session_diagnostics(session_id)

        if "error" in diagnostics:
            self.stdout.write(self.style.ERROR(f"Error: {diagnostics['error']}"))
            return

        self._display_diagnostics_header(diagnostics)
        self._display_basic_info(diagnostics)
        self._display_queries_info(diagnostics)
        self._display_executions_info(diagnostics)
        self._display_results_info(diagnostics)
        self._display_health_check(diagnostics)
        self._display_data_integrity(diagnostics)
        self._display_recent_activities(diagnostics)

    def _display_diagnostics_header(self, diagnostics):
        """Display diagnostics header."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(f"SESSION DIAGNOSTICS: {diagnostics['title']}")
        self.stdout.write("=" * 60)

    def _display_basic_info(self, diagnostics):
        """Display basic session information."""
        self.stdout.write(f"\nSession ID: {diagnostics['session_id']}")
        self.stdout.write(f"Status: {diagnostics['status']}")
        self.stdout.write(f"Created: {diagnostics['created_at']}")
        self.stdout.write(f"Updated: {diagnostics['updated_at']}")
        self.stdout.write(
            f"Time in current status: {diagnostics['time_in_current_status']:.1f} seconds"
        )

    def _display_queries_info(self, diagnostics):
        """Display queries information."""
        self.stdout.write("\nQueries:")
        self.stdout.write(f"  Total: {diagnostics['queries']['total']}")
        self.stdout.write(f"  Active: {diagnostics['queries']['active']}")

    def _display_executions_info(self, diagnostics):
        """Display executions information."""
        self.stdout.write("\nExecutions:")
        for status, count in diagnostics["executions"].items():
            if count > 0:
                self.stdout.write(f"  {status}: {count}")

    def _display_results_info(self, diagnostics):
        """Display results information."""
        self.stdout.write("\nResults:")
        self.stdout.write(f"  Total: {diagnostics['results']['total_results']}")
        self.stdout.write(f"  Reviewed: {diagnostics['results']['reviewed_results']}")
        self.stdout.write(f"  Included: {diagnostics['results']['included_results']}")

    def _display_health_check(self, diagnostics):
        """Display health check information."""
        if "health_check" not in diagnostics:
            return

        self.stdout.write("\nHealth Check:")
        health = diagnostics["health_check"]

        if health["healthy"]:
            self.stdout.write(self.style.SUCCESS("  Status: HEALTHY"))
        else:
            self.stdout.write(
                self.style.ERROR(f"  Status: UNHEALTHY - {health['issue']}")
            )
            if health.get("would_recover_to"):
                self.stdout.write(f"  Would recover to: {health['would_recover_to']}")

    def _display_data_integrity(self, diagnostics):
        """Display data integrity information."""
        if "data_integrity" not in diagnostics:
            return

        self.stdout.write("\nData Integrity:")
        integrity = diagnostics["data_integrity"]

        if integrity["valid"]:
            self.stdout.write(self.style.SUCCESS("  Valid"))
        else:
            self.stdout.write(self.style.ERROR("  Invalid"))
        self.stdout.write(f"  {integrity['report']}")

    def _display_recent_activities(self, diagnostics):
        """Display recent activities."""
        if not diagnostics.get("recent_activities"):
            return

        self.stdout.write("\nRecent Activities:")
        for activity in diagnostics["recent_activities"]:
            self.stdout.write(
                f"  - {activity['created_at']}: {activity['type']} - {activity['description']}"
            )

    def _handle_recovery(self, dry_run):
        """Run recovery process."""
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN - Showing what would be recovered")
            )

        recovery_manager = WorkflowRecoveryManager()
        stuck_count = self._display_stuck_sessions(recovery_manager)

        if stuck_count == 0:
            self.stdout.write(self.style.SUCCESS("\nNo stuck sessions found!"))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\nWould attempt to recover {stuck_count} sessions")
            )
            return

        self._execute_recovery(recovery_manager, stuck_count)

    def _display_stuck_sessions(self, recovery_manager):
        """Display stuck sessions and return count."""
        self.stdout.write("\nChecking for stuck sessions...")

        stuck_count = 0
        for status, rules in recovery_manager.RECOVERY_RULES.items():
            stuck_sessions = recovery_manager._find_stuck_sessions(
                status, rules["timeout"]
            )

            if stuck_sessions:
                stuck_count += stuck_sessions.count()
                self._display_stuck_sessions_for_status(
                    status, rules["timeout"], stuck_sessions
                )

        return stuck_count

    def _display_stuck_sessions_for_status(self, status, timeout, stuck_sessions):
        """Display stuck sessions for a specific status."""
        self.stdout.write(f"\n{status.upper()} (timeout: {timeout}):")

        for session in stuck_sessions[:5]:  # Show first 5
            age = (timezone.now() - session.updated_at).total_seconds() / 3600
            self.stdout.write(
                f"  - {session.title} (ID: {session.id}, Age: {age:.1f} hours)"
            )

        if stuck_sessions.count() > 5:
            self.stdout.write(f"  ... and {stuck_sessions.count() - 5} more")

    def _execute_recovery(self, recovery_manager, stuck_count):
        """Execute recovery and display results."""
        self.stdout.write(f"\nAttempting to recover {stuck_count} sessions...")

        results = recovery_manager.recover_stuck_sessions()

        self._display_recovery_header()
        self._display_recovery_summary(results)
        self._display_recovery_details(results)
        self._display_recovery_execution_time(results)

    def _display_recovery_header(self):
        """Display recovery results header."""
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("RECOVERY RESULTS")
        self.stdout.write("=" * 60)

    def _display_recovery_summary(self, results):
        """Display recovery summary statistics."""
        self.stdout.write(f"\nSessions checked: {results['sessions_checked']}")
        self.stdout.write(f"Issues detected: {results['issues_detected']}")
        self.stdout.write(f"Recovery attempts: {results['recoveries_attempted']}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Successful recoveries: {results['recoveries_succeeded']}"
            )
        )

        if results["recoveries_failed"] > 0:
            self.stdout.write(
                self.style.ERROR(f"Failed recoveries: {results['recoveries_failed']}")
            )

    def _display_recovery_details(self, results):
        """Display detailed recovery results."""
        if not results.get("details"):
            return

        self.stdout.write("\nDetails:")
        for detail in results["details"]:
            if detail["recovery_success"]:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ {detail['session_title']}: {detail['details']}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ {detail['session_title']}: {detail['details']}"
                    )
                )

    def _display_recovery_execution_time(self, results):
        """Display recovery execution time."""
        self.stdout.write(
            f"\nExecution time: {results.get('execution_time_seconds', 0):.2f} seconds"
        )
