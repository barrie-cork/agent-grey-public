"""
Test command for debugging WorkflowRecoveryManager functionality.

This command provides a way to manually test and debug the recovery
manager without waiting for scheduled tasks.
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.review_manager.models import SearchSession
from apps.review_manager.services.recovery_manager import WorkflowRecoveryManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Test and debug the WorkflowRecoveryManager"

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-id", type=str, help="Specific session ID to test recovery on"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run detection only without applying fixes",
        )
        parser.add_argument(
            "--verbose", action="store_true", help="Enable verbose logging"
        )

    def handle(self, *args, **options):
        # Configure logging
        if options["verbose"]:
            logging.getLogger("apps.review_manager").setLevel(logging.DEBUG)
            logging.getLogger("apps.results_manager").setLevel(logging.DEBUG)

        session_id = options.get("session_id")
        dry_run = options.get("dry_run", False)

        self.stdout.write(
            self.style.NOTICE(f"Testing WorkflowRecoveryManager (dry_run={dry_run})")
        )

        try:
            # Initialize recovery manager
            recovery_manager = WorkflowRecoveryManager()

            if session_id:
                # Test specific session
                self._test_specific_session(recovery_manager, session_id, dry_run)
            else:
                # Test all stuck sessions
                self._test_all_sessions(recovery_manager, dry_run)

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"Error during recovery test: {type(e).__name__}: {str(e)}"
                )
            )
            if options["verbose"]:
                import traceback

                self.stdout.write(self.style.ERROR(traceback.format_exc()))

    def _test_specific_session(self, recovery_manager, session_id, dry_run):
        """Test recovery for a specific session."""
        try:
            session = SearchSession.objects.get(id=session_id)
            self.stdout.write(f"\nTesting session: {session.title}")
            self.stdout.write(f"Current status: {session.status}")
            self.stdout.write(f"Last updated: {session.updated_at}")

            # Check if session needs recovery
            time_since_update = timezone.now() - session.updated_at
            if session.status in ["executing", "processing_results"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"Session in {session.status} for {time_since_update}"
                    )
                )

                if dry_run:
                    self.stdout.write(
                        self.style.NOTICE("DRY RUN: Would attempt recovery")
                    )
                else:
                    # Attempt recovery
                    rules = recovery_manager.RECOVERY_RULES.get(session.status, {})
                    success, details = recovery_manager._attempt_recovery(
                        session, rules
                    )
                    if success:
                        self.stdout.write(
                            self.style.SUCCESS(f"Recovery successful: {details}")
                        )
                    else:
                        self.stdout.write(
                            self.style.ERROR(f"Recovery failed: {details}")
                        )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Session appears healthy (status: {session.status})"
                    )
                )

        except SearchSession.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Session {session_id} not found"))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error testing session {session_id}: {str(e)}")
            )

    def _test_all_sessions(self, recovery_manager, dry_run):
        """Test recovery for all potentially stuck sessions."""
        self.stdout.write("\nScanning for stuck sessions...")

        if dry_run:
            # Just detect issues without fixing
            self.stdout.write("\nChecking for stuck sessions by state:")

            total_issues = 0
            for status, rules in recovery_manager.RECOVERY_RULES.items():
                stuck_sessions = recovery_manager._find_stuck_sessions(
                    status, rules["timeout"]
                )

                if stuck_sessions:
                    self.stdout.write(
                        self.style.WARNING(
                            f"\n{status.upper()}: Found {len(stuck_sessions)} stuck sessions"
                        )
                    )
                    total_issues += len(stuck_sessions)

                    for session in stuck_sessions[:5]:  # Show max 5 per state
                        time_since = timezone.now() - session.updated_at
                        self.stdout.write(
                            f"  - {session.id}: {session.title} "
                            f"(stuck for {time_since})"
                        )

                        # Check health without fixing
                        check_method = getattr(
                            recovery_manager, rules.get("check_method", ""), None
                        )
                        if check_method:
                            healthy, reason = check_method(session)
                            if not healthy:
                                self.stdout.write(f"    Issue: {reason}")

            self.stdout.write(f"\nTotal issues found: {total_issues}")

        else:
            # Run full recovery
            results = recovery_manager.recover_stuck_sessions()

            self.stdout.write("\nRecovery Results:")
            self.stdout.write(
                f"- Sessions checked: {results.get('sessions_checked', 0)}"
            )
            self.stdout.write(f"- Issues detected: {results.get('issues_detected', 0)}")
            self.stdout.write(
                f"- Recoveries attempted: {results.get('recoveries_attempted', 0)}"
            )
            self.stdout.write(
                f"- Recoveries succeeded: {results.get('recoveries_succeeded', 0)}"
            )
            self.stdout.write(
                f"- Recoveries failed: {results.get('recoveries_failed', 0)}"
            )

            # Show details
            if results.get("details"):
                self.stdout.write("\nDetailed Results:")
                for detail in results["details"]:
                    status = "✓" if detail.get("recovery_success") else "✗"
                    self.stdout.write(
                        f"{status} Session {detail.get('session_id')}: "
                        f"{detail.get('original_status')} - "
                        f"{detail.get('details', 'Unknown')}"
                    )

        self.stdout.write(self.style.SUCCESS("\nRecovery test completed"))
