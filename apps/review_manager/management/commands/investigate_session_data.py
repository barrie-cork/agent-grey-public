"""
Management command to investigate session data for debugging zero results issue.

This command provides detailed database analysis for a specific session to help
identify why results aren't appearing in the review interface.

Usage:
    python manage.py investigate_session_data <session_id>
"""

import logging
from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.serp_execution.models import RawSearchResult

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Investigate session data to debug zero results issue"

    def add_arguments(self, parser):
        parser.add_argument(
            "session_id",
            type=str,
            help="Session ID to investigate",
        )

    def handle(self, *args, **options):
        session_id = options.get("session_id")

        self.stdout.write(f"\n{'=' * 80}")
        self.stdout.write(f"DATABASE INVESTIGATION: Session {session_id}")
        self.stdout.write(f"{'=' * 80}\n")

        # Get and display session
        session = self._get_session(session_id)
        if not session:
            return

        # Collect diagnostic data
        raw_results = self._display_raw_results(session)
        processed_results, total_processed = self._display_processed_results(session_id)
        duplicate_url_count = self._display_duplicate_analysis(processed_results)

        # Display sample results
        self._display_sample_results(processed_results)

        # Provide analysis and recommendations
        self._display_recommendations(
            session_id,
            processed_results,
            total_processed,
            duplicate_url_count,
            raw_results,
        )

        self.stdout.write("")

    def _get_session(self, session_id):
        """Retrieve and display session information."""
        try:
            session = SearchSession.objects.get(id=session_id)
            self.stdout.write(
                f"📋 Session: {session.title}\n"
                f"   Status: {session.status}\n"
                f"   Owner: {session.owner.email}\n"
                f"   Created: {session.created_at}\n"
            )
            return session
        except SearchSession.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ Session {session_id} not found"))
            return None

    def _display_raw_results(self, session):
        """Display raw search results statistics."""
        raw_results = RawSearchResult.objects.filter(execution__query__session=session)
        self.stdout.write(
            f"\n📦 Raw Results:\n"
            f"   Total: {raw_results.count()}\n"
            f"   Processed: {raw_results.filter(is_processed=True).count()}\n"
            f"   Unprocessed: {raw_results.filter(is_processed=False).count()}\n"
        )
        return raw_results

    def _display_processed_results(self, session_id):
        """Display processed results status breakdown."""
        processed_results = ProcessedResult.objects.filter(session_id=session_id)
        total_processed = processed_results.count()

        status_counts = (
            processed_results.values("processing_status")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        self.stdout.write(
            f"\n📊 ProcessedResult Status Breakdown (Total: {total_processed}):"
        )

        for item in status_counts:
            self._display_status_line(item, total_processed)

        return processed_results, total_processed

    def _display_status_line(self, item, total_processed):
        """Display a single status line with formatting."""
        status = item["processing_status"]
        count = item["count"]
        percentage = (count / total_processed * 100) if total_processed > 0 else 0

        status_styles = {
            "success": (self.style.SUCCESS, "✅"),
            "filtered": (self.style.WARNING, "🔄"),
            "error": (self.style.ERROR, "❌"),
        }

        style_func, icon = status_styles.get(status, (lambda x: x, "❓"))
        formatted_line = f"   {icon} {status.upper()}: {count} ({percentage:.1f}%)"

        self.stdout.write(style_func(formatted_line))

    def _display_duplicate_analysis(self, processed_results):
        """Display duplicate URL analysis."""
        url_counts = (
            processed_results.values("url")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .order_by("-count")
        )

        duplicate_url_count = url_counts.count()
        self.stdout.write("\n🔍 Duplicate URL Analysis:")
        self.stdout.write(f"   URLs appearing multiple times: {duplicate_url_count}")

        if duplicate_url_count > 0:
            self._display_top_duplicates(url_counts, processed_results)

        return duplicate_url_count

    def _display_top_duplicates(self, url_counts, processed_results):
        """Display top 10 duplicated URLs with their statuses."""
        self.stdout.write("\n   Top 10 duplicated URLs:")
        for item in url_counts[:10]:
            url = item["url"]
            count = item["count"]
            self.stdout.write(f"      • {url[:70]}... ({count} times)")

            # Show the statuses of these duplicates
            duplicate_records = processed_results.filter(url=url)
            statuses = duplicate_records.values_list("processing_status", flat=True)
            status_str = ", ".join([f"{s}" for s in statuses])
            self.stdout.write(f"        Statuses: {status_str}")

    def _display_sample_results(self, processed_results):
        """Display sample results for each status type."""
        self.stdout.write("\n📋 Sample Results:")

        samples = {
            "success": (self.style.SUCCESS, "✅"),
            "filtered": (self.style.WARNING, "🔄"),
            "error": (self.style.ERROR, "❌"),
        }

        for status, (style_func, icon) in samples.items():
            sample = processed_results.filter(processing_status=status).first()
            if sample:
                self._display_sample_result(sample, style_func, icon, status.upper())
            elif status == "success":
                self.stdout.write(self.style.WARNING("   ⚠️  No SUCCESS results found"))

    def _display_sample_result(self, sample, style_func, icon, status_label):
        """Display a single sample result."""
        self.stdout.write(
            style_func(
                f"\n   {icon} {status_label} sample:\n"
                f"      ID: {sample.id}\n"
                f"      URL: {sample.url[:70]}\n"
                f"      Title: {sample.title[:50]}\n"
                f"      Processed: {sample.processed_at}"
            )
        )

    def _display_recommendations(
        self,
        session_id,
        processed_results,
        total_processed,
        duplicate_url_count,
        raw_results,
    ):
        """Display analysis and recommendations."""
        self.stdout.write(f"\n{'=' * 80}")
        self.stdout.write("ANALYSIS & RECOMMENDATIONS:")
        self.stdout.write(f"{'=' * 80}\n")

        success_count = processed_results.filter(processing_status="success").count()
        filtered_count = processed_results.filter(processing_status="filtered").count()

        # Determine scenario and display appropriate recommendation
        if success_count == 0 and filtered_count > 0:
            self._recommend_filtered_issue_fix(
                session_id, filtered_count, duplicate_url_count
            )
        elif success_count > 0:
            self._recommend_results_available(success_count)
        elif total_processed == 0:
            self._recommend_no_processed_results(session_id, raw_results)

    def _recommend_filtered_issue_fix(
        self, session_id, filtered_count, duplicate_url_count
    ):
        """Recommend fix for filtered results issue."""
        if duplicate_url_count == 0:
            self.stdout.write(
                self.style.ERROR(
                    "🚨 CRITICAL BUG DETECTED:\n"
                    f"   • {filtered_count} results marked as FILTERED\n"
                    "   • But 0 actual duplicate URLs found\n"
                    "   • This indicates FALSE DUPLICATE marking\n\n"
                    "RECOMMENDED FIX:\n"
                    f"   python manage.py diagnose_zero_results {session_id} --fix\n"
                    "   This will correct falsely marked FILTERED results to SUCCESS"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  POSSIBLE ISSUE:\n"
                    f"   • {filtered_count} results marked as FILTERED\n"
                    f"   • {duplicate_url_count} URLs appear multiple times\n"
                    "   • May have mix of true duplicates and false positives\n\n"
                    "RECOMMENDED FIX:\n"
                    f"   python manage.py diagnose_zero_results {session_id} --fix\n"
                    "   This will preserve true duplicates but correct false ones"
                )
            )

    def _recommend_results_available(self, success_count):
        """Recommend actions when results are available."""
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ RESULTS AVAILABLE:\n"
                f"   • {success_count} results with SUCCESS status\n"
                "   • These should be visible in review interface\n\n"
                "If not visible, check:\n"
                "   1. Session status (should be ready_for_review or under_review)\n"
                "   2. Browser cache (try hard refresh: Ctrl+Shift+R)\n"
                "   3. Review interface filters (check if 'All' is selected)"
            )
        )

    def _recommend_no_processed_results(self, session_id, raw_results):
        """Recommend fix when no processed results exist."""
        self.stdout.write(
            self.style.ERROR(
                "💥 NO PROCESSED RESULTS:\n"
                f"   • Raw results: {raw_results.count()}\n"
                "   • Processed results: 0\n"
                "   • Processing may have failed or not started\n\n"
                "RECOMMENDED FIX:\n"
                f"   python manage.py diagnose_zero_results {session_id} --fix\n"
                "   This will trigger reprocessing of raw results"
            )
        )
