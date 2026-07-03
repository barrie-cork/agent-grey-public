"""
Management command to fix false duplicate marking in ProcessedResults.

This command identifies results that were incorrectly marked as FILTERED (duplicates)
and corrects them to SUCCESS status so they appear in the review interface.

The bug: When get_or_create() found an existing URL, it changed the original result's
status from SUCCESS to FILTERED, even though the original result should remain SUCCESS.

This fix:
1. Identifies URLs that only appear once (not true duplicates)
2. Changes their status from FILTERED back to SUCCESS
3. Preserves true duplicates (URLs appearing multiple times keep FILTERED status)

Usage:
    python manage.py fix_false_duplicates <session_id>
    python manage.py fix_false_duplicates <session_id> --dry-run
"""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fix false duplicate marking - correct FILTERED results that aren't true duplicates"

    def add_arguments(self, parser):
        parser.add_argument(
            "session_id",
            type=str,
            help="Session ID to fix",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be fixed without making changes",
        )

    def handle(self, *args, **options):  # noqa: C901 - Duplicate detection and fixing
        session_id = options.get("session_id")
        dry_run = options.get("dry_run")

        self.stdout.write(f"\n{'=' * 80}")
        if dry_run:
            self.stdout.write("DRY RUN MODE - No changes will be made")
        self.stdout.write(f"Fixing False Duplicates: Session {session_id}")
        self.stdout.write(f"{'=' * 80}\n")

        # Get session
        try:
            session = SearchSession.objects.get(id=session_id)
            self.stdout.write(
                f"📋 Session: {session.title}\n   Status: {session.status}\n"
            )
        except SearchSession.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ Session {session_id} not found"))
            return

        # Get all processed results
        processed_results = ProcessedResult.objects.filter(session_id=session_id)
        total_results = processed_results.count()

        if total_results == 0:
            self.stdout.write(
                self.style.WARNING("⚠️  No processed results found for this session")
            )
            return

        # Get current status breakdown
        status_counts = processed_results.values("processing_status").annotate(
            count=Count("id")
        )

        self.stdout.write("\n📊 Current Status Breakdown:")
        for item in status_counts:
            status = item["processing_status"]
            count = item["count"]
            percentage = count / total_results * 100

            if status == "success":
                self.stdout.write(
                    self.style.SUCCESS(f"   ✅ SUCCESS: {count} ({percentage:.1f}%)")
                )
            elif status == "filtered":
                self.stdout.write(
                    self.style.WARNING(f"   🔄 FILTERED: {count} ({percentage:.1f}%)")
                )
            elif status == "error":
                self.stdout.write(
                    self.style.ERROR(f"   ❌ ERROR: {count} ({percentage:.1f}%)")
                )

        # Find truly duplicated URLs (appear more than once)
        truly_duplicated_urls = set(
            processed_results.values("url")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
            .values_list("url", flat=True)
        )

        self.stdout.write("\n🔍 Duplicate Analysis:")
        self.stdout.write(f"   Total results: {total_results}")
        self.stdout.write(
            f"   URLs appearing multiple times: {len(truly_duplicated_urls)}"
        )

        # Find FILTERED results that aren't true duplicates
        filtered_results = processed_results.filter(processing_status="filtered")
        falsely_filtered = [
            result
            for result in filtered_results
            if result.url not in truly_duplicated_urls
        ]

        self.stdout.write("\n🔧 Fix Analysis:")
        self.stdout.write(f"   Total FILTERED results: {filtered_results.count()}")
        self.stdout.write(f"   False duplicates (to be fixed): {len(falsely_filtered)}")
        self.stdout.write(
            f"   True duplicates (will keep FILTERED): {filtered_results.count() - len(falsely_filtered)}"
        )

        if len(falsely_filtered) == 0:
            self.stdout.write(
                self.style.SUCCESS("\n✅ No false duplicates found - nothing to fix!")
            )
            return

        # Show samples of what will be fixed
        self.stdout.write("\n📋 Sample False Duplicates (first 5):")
        for i, result in enumerate(falsely_filtered[:5], 1):
            self.stdout.write(
                f"   {i}. {result.url[:70]}\n"
                f"      Title: {result.title[:50]}\n"
                f"      Current status: FILTERED → Will change to SUCCESS"
            )

        if len(falsely_filtered) > 5:
            self.stdout.write(f"   ... and {len(falsely_filtered) - 5} more")

        # Apply the fix
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\n🔍 DRY RUN COMPLETE\n"
                    f"   Would fix {len(falsely_filtered)} false duplicates\n"
                    f"   Run without --dry-run to apply changes"
                )
            )
        else:
            self.stdout.write("\n⚙️  Applying fixes...")

            with transaction.atomic():
                fixed_count = 0
                for result in falsely_filtered:
                    result.processing_status = "success"
                    result.save(update_fields=["processing_status"])
                    fixed_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n✅ SUCCESS!\n"
                        f"   Fixed {fixed_count} false duplicates\n"
                        f"   Changed status from FILTERED → SUCCESS"
                    )
                )

            # Show updated status breakdown
            updated_status_counts = processed_results.values(
                "processing_status"
            ).annotate(count=Count("id"))

            self.stdout.write("\n📊 Updated Status Breakdown:")
            for item in updated_status_counts:
                status = item["processing_status"]
                count = item["count"]
                percentage = count / total_results * 100

                if status == "success":
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"   ✅ SUCCESS: {count} ({percentage:.1f}%)"
                        )
                    )
                elif status == "filtered":
                    self.stdout.write(
                        self.style.WARNING(
                            f"   🔄 FILTERED: {count} ({percentage:.1f}%)"
                        )
                    )
                elif status == "error":
                    self.stdout.write(
                        self.style.ERROR(f"   ❌ ERROR: {count} ({percentage:.1f}%)")
                    )

            success_count = processed_results.filter(
                processing_status="success"
            ).count()
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n🎉 {success_count} results now available for review!"
                )
            )

        self.stdout.write("")
