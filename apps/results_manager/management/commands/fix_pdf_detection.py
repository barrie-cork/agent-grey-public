"""
Management command to fix PDF detection in ProcessedResult records.

This command retroactively updates the is_pdf field based on comprehensive
detection logic that checks URL patterns, title markers, and raw result flags.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.results_manager.constants import DocumentType
from apps.results_manager.models import ProcessedResult


class Command(BaseCommand):
    help = "Fix PDF detection for existing ProcessedResult records"

    def _is_pdf_document(self, result):
        """
        Determine if a ProcessedResult represents a PDF document.

        Args:
            result: ProcessedResult instance to check

        Returns:
            bool: True if the result is likely a PDF document
        """
        url_lower = result.url.lower()
        title_lower = result.title.lower()

        # Check multiple indicators for PDF
        is_pdf = (
            ".pdf" in url_lower
            or "pdf" in url_lower.split("/")[-1]
            or "[pdf]" in title_lower
            or (result.raw_result and result.raw_result.has_pdf)
            or result.document_type == DocumentType.PDF
        )

        # Also check full_text_url if it contains PDF
        if result.full_text_url:
            full_text_lower = result.full_text_url.lower()
            is_pdf = is_pdf or ".pdf" in full_text_lower

        return is_pdf

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )
        parser.add_argument(
            "--session-id", type=str, help="Process only a specific session"
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        session_id = options.get("session_id")

        # Build query
        queryset = ProcessedResult.objects.select_related("raw_result")
        if session_id:
            queryset = queryset.filter(session_id=session_id)
            self.stdout.write(f"Processing session {session_id} only")

        total = queryset.count()
        self.stdout.write(f"Checking {total} ProcessedResult records...")

        updated_count = 0
        already_pdf_count = 0
        newly_pdf_count = 0

        with transaction.atomic():
            for result in queryset.iterator(chunk_size=100):
                # Use helper method for PDF detection
                should_be_pdf = self._is_pdf_document(result)

                # Check if update is needed
                if should_be_pdf and not result.is_pdf:
                    if not dry_run:
                        result.is_pdf = True
                        result.document_type = DocumentType.PDF
                        result.save(update_fields=["is_pdf", "document_type"])
                    newly_pdf_count += 1
                    updated_count += 1

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"{'[DRY RUN] Would update' if dry_run else 'Updated'}: "
                            f"{result.title[:50]}..."
                        )
                    )
                elif result.is_pdf:
                    already_pdf_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS(f"Total records checked: {total}"))
        self.stdout.write(
            self.style.SUCCESS(f"Already marked as PDF: {already_pdf_count}")
        )
        self.stdout.write(
            self.style.WARNING(f"Newly identified as PDF: {newly_pdf_count}")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Total PDFs after update: {already_pdf_count + newly_pdf_count}"
            )
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a dry run. No changes were made. "
                    "Run without --dry-run to apply changes."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nSuccessfully updated {updated_count} records")
            )
