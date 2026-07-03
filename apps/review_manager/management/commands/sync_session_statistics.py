"""
Management command to synchronize denormalized session statistics.

This command updates the denormalized fields in SearchSession model
(total_results, reviewed_results, included_results) by querying the
actual data from related models.
"""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import SimpleReviewDecision

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Synchronize denormalized session statistics with actual data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-id",
            type=str,
            help="Sync statistics for a specific session (UUID)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed output",
        )

    def handle(self, *args, **options):
        """Handle the sync command."""
        session_id = options.get("session_id")
        dry_run = options.get("dry_run")
        verbose = options.get("verbose")

        sessions = self._get_sessions_to_sync(session_id)
        if not sessions:
            return

        updated_count, errors = self._sync_all_sessions(sessions, dry_run, verbose)

        self._display_summary(updated_count, errors)

    def _get_sessions_to_sync(self, session_id):
        """Get sessions to sync based on options."""
        if session_id:
            try:
                session = SearchSession.objects.get(id=session_id)
                self.stdout.write(f"Syncing statistics for session: {session.title}")
                return [session]
            except SearchSession.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Session with ID {session_id} not found")
                )
                return None
        else:
            sessions = SearchSession.objects.all().order_by("-created_at")
            self.stdout.write(f"Syncing statistics for {sessions.count()} sessions")
            return sessions

    def _sync_all_sessions(self, sessions, dry_run, verbose):
        """Sync statistics for all sessions."""
        updated_count = 0
        errors = []

        for session in sessions:
            try:
                updated = self._sync_session_statistics(session, dry_run, verbose)
                if updated:
                    updated_count += 1
            except Exception as e:
                error_msg = f"Error syncing session {session.id}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg, exc_info=True)

        return updated_count, errors

    def _display_summary(self, updated_count, errors):
        """Display sync summary."""
        self.stdout.write(
            self.style.SUCCESS(f"\nSync completed. Updated {updated_count} sessions.")
        )

        if errors:
            self.stdout.write(self.style.ERROR(f"\nEncountered {len(errors)} errors:"))
            for error in errors[:5]:  # Show first 5 errors
                self.stdout.write(self.style.ERROR(f"  - {error}"))
            if len(errors) > 5:
                self.stdout.write(
                    self.style.ERROR(f"  ... and {len(errors) - 5} more errors")
                )

    def _sync_session_statistics(self, session, dry_run, verbose):
        """
        Sync statistics for a single session.

        Returns True if the session was updated, False otherwise.
        """
        # Get actual counts from related models
        actual_stats = self._get_actual_statistics(session)

        # Compare with current denormalized values
        current_stats = {
            "total_results": session.total_results,
            "reviewed_results": session.reviewed_results,
            "included_results": session.included_results,
        }

        # Check if update needed
        needs_update = False
        updates = {}

        for field, actual_value in actual_stats.items():
            if current_stats[field] != actual_value:
                needs_update = True
                updates[field] = actual_value

        if not needs_update:
            if verbose:
                self.stdout.write(
                    f"  Session {session.id} ({session.title}): No updates needed"
                )
            return False

        # Show what will be updated
        if verbose or dry_run:
            self.stdout.write(f"\n  Session {session.id} ({session.title}):")
            self.stdout.write(f"    Status: {session.status}")
            for field, new_value in updates.items():
                old_value = current_stats[field]
                self.stdout.write(
                    f"    {field}: {old_value} → {new_value} "
                    f"(diff: {new_value - old_value:+d})"
                )

        # Apply updates if not dry run
        if not dry_run:
            with transaction.atomic():
                for field, value in updates.items():
                    setattr(session, field, value)
                session.save(update_fields=list(updates.keys()) + ["updated_at"])

                if verbose:
                    self.stdout.write(self.style.SUCCESS("    ✓ Updated"))

        return True

    def _get_actual_statistics(self, session):
        """
        Get actual statistics from related models.
        """
        # Get total processed results
        total_results = ProcessedResult.objects.filter(session=session).count()

        # Get review decision counts
        decision_stats = SimpleReviewDecision.objects.filter(session=session).aggregate(
            total_reviewed=Count("id", filter=~Q(decision="pending")),
            included=Count("id", filter=Q(decision="include")),
            excluded=Count("id", filter=Q(decision="exclude")),
            maybe=Count("id", filter=Q(decision="maybe")),
        )

        return {
            "total_results": total_results,
            "reviewed_results": decision_stats["total_reviewed"] or 0,
            "included_results": decision_stats["included"] or 0,
        }
