"""
Management command to detect and fix sessions stuck in processing_results state.

This command checks for sessions that have completed processing but failed to
transition to the ready_for_review state, and attempts to fix them.
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.results_manager.models import ProcessedResult, ProcessingSession
from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_manager.services.state_manager import SessionStateManager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Find and fix sessions stuck in processing_results state"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be fixed without making changes",
        )
        parser.add_argument(
            "--hours",
            type=int,
            default=1,
            help="Consider sessions stuck if in processing_results for more than this many hours (default: 1)",
        )

    def handle(self, *args, **options):
        """Handle the fix command."""
        dry_run = options["dry_run"]
        hours_threshold = options["hours"]
        cutoff_time = timezone.now() - timedelta(hours=hours_threshold)

        self.stdout.write(
            f"Checking for sessions stuck in processing_results state "
            f"for more than {hours_threshold} hour(s)..."
        )

        # Find potentially stuck sessions
        stuck_sessions = SearchSession.objects.filter(
            status="processing_results", updated_at__lt=cutoff_time
        ).select_related("owner")

        if not stuck_sessions:
            self.stdout.write(self.style.SUCCESS("No stuck sessions found!"))
            return

        self.stdout.write(
            f"Found {stuck_sessions.count()} potentially stuck session(s)"
        )

        fixed_count = 0
        failed_count = 0

        for session in stuck_sessions:
            result = self._process_stuck_session(session, dry_run)
            if result == "fixed":
                fixed_count += 1
            elif result == "failed":
                failed_count += 1

        # Summary
        self._display_summary(
            stuck_sessions.count(), fixed_count, failed_count, dry_run
        )

    def _process_stuck_session(self, session, dry_run):
        """Process a single stuck session."""
        self.stdout.write(f"\nChecking session: {session.title} (ID: {session.id})")

        try:
            processing_session = ProcessingSession.objects.filter(
                search_session=session
            ).latest("created_at")
        except ProcessingSession.DoesNotExist:
            self.stdout.write(self.style.WARNING("  - No processing session found"))
            return "skipped"
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  - Error checking session: {str(e)}"))
            return "failed"

        # Check if processing is actually complete
        if processing_session.status != "completed":
            self.stdout.write(
                f"  - Processing still in progress (status: {processing_session.status})"
            )
            return "skipped"

        # Count processed results
        processed_count = ProcessedResult.objects.filter(session=session).count()

        self.stdout.write(f"  - Processing completed with {processed_count} results")
        self.stdout.write(f"  - Processing session: {processing_session.id}")
        self.stdout.write(f"  - Completed at: {processing_session.completed_at}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("  - [DRY RUN] Would fix this session")
            )
            return "fixed"

        # Attempt to fix the session
        return self._fix_session(session, processing_session, processed_count)

    def _fix_session(self, session, processing_session, processed_count):
        """Attempt to fix a stuck session."""
        try:
            state_manager = SessionStateManager(session)
            state_manager.transition_to(
                "ready_for_review",
                metadata={
                    "trigger": "management_command_fix",
                    "reason": "Automatic fix for stuck session",
                    "processed_results": processed_count,
                    "processing_session_id": str(processing_session.id),
                    "command": "fix_stuck_sessions",
                },
            )

            # Update result counts
            session.total_results = processed_count
            session.save(update_fields=["total_results"])

            self.stdout.write(
                self.style.SUCCESS("  - Fixed! Session now in 'ready_for_review' state")
            )
            return "fixed"

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  - Failed to fix: {str(e)}"))
            return self._fix_session_fallback(session, processed_count, e)

    def _fix_session_fallback(self, session, processed_count, original_error):
        """Attempt fallback fix method."""
        try:
            session.status = "ready_for_review"
            session.total_results = processed_count
            session.save(update_fields=["status", "total_results"])

            # Log the manual fix
            SessionActivity.objects.create(
                session=session,
                activity_type="status_changed",
                description="Manual fix for stuck session via management command (fallback)",
                user=session.owner,
                metadata={
                    "old_status": "processing_results",
                    "new_status": "ready_for_review",
                    "command": "fix_stuck_sessions",
                    "fallback": True,
                    "error": str(original_error),
                },
            )

            self.stdout.write(self.style.WARNING("  - Fixed using fallback method"))
            return "fixed"

        except Exception as fallback_error:
            self.stdout.write(
                self.style.ERROR(f"  - Fallback also failed: {str(fallback_error)}")
            )
            return "failed"

    def _display_summary(self, total_found, fixed_count, failed_count, dry_run):
        """Display summary of operations."""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"Total stuck sessions found: {total_found}")
        if dry_run:
            self.stdout.write(f"Sessions that would be fixed: {fixed_count}")
        else:
            self.stdout.write(self.style.SUCCESS(f"Sessions fixed: {fixed_count}"))
            if failed_count > 0:
                self.stdout.write(self.style.ERROR(f"Sessions failed: {failed_count}"))
