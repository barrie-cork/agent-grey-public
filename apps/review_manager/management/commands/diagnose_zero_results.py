"""
Management command to diagnose and fix zero results issues in search sessions.

This command helps identify and resolve cases where:
1. Search execution completed successfully
2. Raw results were created
3. But zero ProcessedResults with SUCCESS status exist for review

Usage:
    python manage.py diagnose_zero_results <session_id>
    python manage.py diagnose_zero_results <session_id> --fix
    python manage.py diagnose_zero_results --all --recent 7
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.results_manager.models import ProcessedResult, ProcessingSession
from apps.results_manager.services.processors.error_handler import ProcessingStatus
from apps.review_manager.models import SearchSession
from apps.serp_execution.models import RawSearchResult, SearchExecution

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Diagnose and optionally fix zero results issues in search sessions"

    def add_arguments(self, parser):
        parser.add_argument(
            "session_id",
            nargs="?",
            type=str,
            help="Session ID to diagnose (optional if using --all)",
        )
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Attempt to fix identified issues automatically",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Diagnose all sessions in ready_for_review or processing_results state",
        )
        parser.add_argument(
            "--recent",
            type=int,
            default=7,
            help="When using --all, only check sessions from last N days (default: 7)",
        )

    def handle(self, *args, **options):
        session_id: str | None = options.get("session_id")
        fix: bool = bool(options.get("fix", False))
        check_all = options.get("all")
        recent_days: int = int(options.get("recent") or 7)

        if not session_id and not check_all:
            self.stdout.write(
                self.style.ERROR(
                    "Error: Provide a session_id or use --all to check multiple sessions"
                )
            )
            return

        if check_all:
            self._diagnose_all_sessions(recent_days, fix)
        else:
            self._diagnose_session(session_id or "", fix)

    def _diagnose_all_sessions(self, recent_days: int, fix: bool):
        """Diagnose all recent sessions that might have zero results issues."""
        cutoff_date = timezone.now() - timedelta(days=recent_days)

        # Find sessions in ready_for_review or processing_results
        sessions = SearchSession.objects.filter(
            status__in=["ready_for_review", "processing_results"],
            created_at__gte=cutoff_date,
        ).order_by("-created_at")

        self.stdout.write(
            self.style.WARNING(
                f"\n🔍 Checking {sessions.count()} sessions from last {recent_days} days...\n"
            )
        )

        issues_found = 0
        for session in sessions:
            has_issue = self._diagnose_session(str(session.id), fix, verbose=False)
            if has_issue:
                issues_found += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Diagnosis complete: {issues_found} sessions with issues found"
            )
        )

    def _diagnose_session(  # noqa: C901 - Session diagnostic logic
        self, session_id: str, fix: bool = False, verbose: bool = True
    ) -> bool:
        """
        Diagnose a single session for zero results issues.

        Returns:
            bool: True if issues were found, False otherwise
        """
        if verbose:
            self.stdout.write(f"\n{'=' * 80}")
            self.stdout.write(f"Diagnosing session: {session_id}")
            self.stdout.write(f"{'=' * 80}\n")

        try:
            session = SearchSession.objects.get(id=session_id)
        except SearchSession.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ Session {session_id} not found"))
            return False

        # Step 1: Check basic session info
        self.stdout.write(
            f"📋 Session: {session.title}\n"
            f"   Status: {session.status}\n"
            f"   Owner: {session.owner.email}\n"
            f"   Created: {session.created_at}\n"
        )

        # Step 2: Check SearchExecutions
        executions = SearchExecution.objects.filter(query__session=session)
        completed_execs = executions.filter(status="completed")
        failed_execs = executions.filter(status="failed")

        self.stdout.write(
            f"\n🔍 Search Executions:\n"
            f"   Total: {executions.count()}\n"
            f"   Completed: {completed_execs.count()}\n"
            f"   Failed: {failed_execs.count()}\n"
        )

        # Step 3: Check RawSearchResults
        raw_results = RawSearchResult.objects.filter(execution__query__session=session)
        processed_raw = raw_results.filter(is_processed=True)
        unprocessed_raw = raw_results.filter(is_processed=False)

        self.stdout.write(
            f"\n📦 Raw Results:\n"
            f"   Total: {raw_results.count()}\n"
            f"   Processed: {processed_raw.count()}\n"
            f"   Unprocessed: {unprocessed_raw.count()}\n"
        )

        # Step 4: Check ProcessedResults by status
        processed_results = ProcessedResult.objects.filter(session=session)
        success_count = processed_results.filter(
            processing_status=ProcessingStatus.SUCCESS
        ).count()
        filtered_count = processed_results.filter(
            processing_status=ProcessingStatus.FILTERED
        ).count()
        error_count = processed_results.filter(
            processing_status=ProcessingStatus.ERROR
        ).count()

        self.stdout.write(
            f"\n📊 Processed Results:\n"
            f"   Total: {processed_results.count()}\n"
            f"   ✅ SUCCESS: {success_count}\n"
            f"   🔄 FILTERED (duplicates): {filtered_count}\n"
            f"   ❌ ERROR: {error_count}\n"
        )

        # Step 5: Check ProcessingSession
        try:
            processing_session = ProcessingSession.objects.get(search_session=session)
            self.stdout.write(
                f"\n⚙️  Processing Session:\n"
                f"   Status: {processing_session.status}\n"
                f"   Stage: {processing_session.current_stage}\n"
                f"   Processed: {processing_session.processed_count}\n"
                f"   Errors: {processing_session.error_count}\n"
                f"   Duplicates: {processing_session.duplicate_count}\n"
            )
        except ProcessingSession.DoesNotExist:
            self.stdout.write(self.style.WARNING("   No ProcessingSession found\n"))
            processing_session = None

        # Step 6: Identify issues
        has_issues = False
        issues = []

        if raw_results.count() > 0 and processed_results.count() == 0:
            has_issues = True
            issues.append(
                "💥 CRITICAL: Raw results exist but NO ProcessedResults created"
            )

        if success_count == 0 and filtered_count > 0:
            has_issues = True
            issues.append(
                f"⚠️  ZERO RESULTS BUG: All {filtered_count} results marked as FILTERED (duplicates)"
            )

        if (
            session.status == "ready_for_review"
            and success_count == 0
            and raw_results.count() > 0
        ):
            has_issues = True
            issues.append(
                "⚠️  Session in ready_for_review but zero SUCCESS results available"
            )

        if unprocessed_raw.count() > 0:
            has_issues = True
            issues.append(
                f"⚠️  {unprocessed_raw.count()} unprocessed raw results remaining"
            )

        # Step 7: Report issues
        if has_issues:
            self.stdout.write(self.style.ERROR("\n🚨 ISSUES DETECTED:\n"))
            for issue in issues:
                self.stdout.write(self.style.ERROR(f"   {issue}"))
            self.stdout.write("")

            # Step 8: Apply fixes if requested
            if fix:
                self.stdout.write(self.style.WARNING("\n🔧 Attempting fixes...\n"))
                self._apply_fixes(
                    session, raw_results, processed_results, processing_session
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "\n💡 Tip: Run with --fix to attempt automatic repairs\n"
                    )
                )
        else:
            if verbose:
                self.stdout.write(self.style.SUCCESS("\n✅ No issues detected\n"))

        return has_issues

    def _apply_fixes(self, session, raw_results, processed_results, processing_session):
        """Apply automated fixes to identified issues."""
        # Fix 1: Reprocess unprocessed raw results
        self._fix_unprocessed_results(session, raw_results)

        # Fix 2: Check for FILTERED results that should be SUCCESS
        self._fix_falsely_filtered_results(processed_results)

        # Fix 3: Force state reconciliation
        self._fix_state_reconciliation(session, processing_session)

        self.stdout.write(self.style.SUCCESS("\n✅ Fixes applied successfully\n"))

    def _fix_unprocessed_results(self, session, raw_results):
        """Trigger reprocessing of unprocessed raw results."""
        unprocessed = raw_results.filter(is_processed=False)
        if not unprocessed.exists():
            return

        self.stdout.write(
            f"   Triggering reprocessing of {unprocessed.count()} raw results..."
        )

        from apps.results_manager.tasks import process_session_results_task

        task = process_session_results_task.apply_async(
            args=(str(session.id),), countdown=2
        )
        self.stdout.write(
            self.style.SUCCESS(f"   ✅ Reprocessing task queued: {task.id}")
        )

    def _fix_falsely_filtered_results(self, processed_results):
        """Correct FILTERED results that aren't actually duplicates."""
        filtered_results = processed_results.filter(
            processing_status=ProcessingStatus.FILTERED
        )
        if not filtered_results.exists():
            return

        self.stdout.write(
            f"\n   Checking {filtered_results.count()} FILTERED results..."
        )

        # Identify truly duplicated URLs
        truly_duplicated_urls = self._find_duplicate_urls(processed_results)

        # Find and correct falsely filtered results
        falsely_filtered = [
            result
            for result in filtered_results
            if result.url not in truly_duplicated_urls
        ]

        if falsely_filtered:
            self._correct_filtered_results(falsely_filtered, processed_results)

    def _find_duplicate_urls(self, processed_results):
        """Find URLs that appear multiple times in processed results."""
        from django.db.models import Count

        url_counts = (
            processed_results.values("url")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )

        return {item["url"] for item in url_counts}

    def _correct_filtered_results(self, falsely_filtered, processed_results):
        """Correct processing status for falsely filtered results."""
        self.stdout.write(
            self.style.WARNING(
                f"   Found {len(falsely_filtered)} results incorrectly marked as FILTERED"
            )
        )
        self.stdout.write("   Correcting processing status...")

        with transaction.atomic():
            for result in falsely_filtered:
                result.processing_status = ProcessingStatus.SUCCESS
                result.save(update_fields=["processing_status"])

        self.stdout.write(
            self.style.SUCCESS(
                f"   ✅ Corrected {len(falsely_filtered)} results to SUCCESS status"
            )
        )

        # Report new success count
        success_count = processed_results.filter(
            processing_status=ProcessingStatus.SUCCESS
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"   ✅ Session now has {success_count} results available for review"
            )
        )

    def _fix_state_reconciliation(self, session, processing_session):
        """Force state reconciliation if session is stuck."""
        if not (
            session.status == "processing_results"
            and processing_session
            and processing_session.status == "completed"
        ):
            return

        self.stdout.write(
            "\n   Processing complete but session stuck in processing_results"
        )
        self.stdout.write("   Triggering state reconciliation...")

        from apps.serp_execution.tasks.monitoring_helpers import (
            reconcile_session_states,
        )

        result = reconcile_session_states(str(session.id))
        if result["reconciled"]:
            self.stdout.write(self.style.SUCCESS("   ✅ State reconciliation applied"))
            for change in result["changes"]:
                self.stdout.write(f"      - {change}")
        else:
            self.stdout.write(
                self.style.WARNING("   ⚠️  State reconciliation had no effect")
            )
