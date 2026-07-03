"""
Management command to fix incorrect document_type labeling for PDFs.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.results_manager.models import ProcessedResult


class Command(BaseCommand):
    help = "Fix document_type field for PDFs that were incorrectly labeled as webpages"

    def handle(self, *args, **options):
        self.stdout.write("Fixing PDF document types...")

        # Find all results that should be PDFs
        results_to_fix = ProcessedResult.objects.filter(
            is_pdf=True, document_type="webpage"
        )

        count_before = results_to_fix.count()
        self.stdout.write(f"Found {count_before} PDFs incorrectly labeled as webpages")

        if count_before > 0:
            with transaction.atomic():
                # Update all at once
                updated = results_to_fix.update(document_type="pdf")
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully updated {updated} records")
                )

        # Also check for PDFs by title
        title_pdfs = ProcessedResult.objects.filter(
            title__icontains="[PDF]", document_type="webpage"
        )

        title_count = title_pdfs.count()
        if title_count > 0:
            self.stdout.write(f"Found {title_count} additional PDFs by title marker")
            with transaction.atomic():
                # Update these to be PDFs
                for result in title_pdfs:
                    result.document_type = "pdf"
                    result.is_pdf = True
                    result.save(update_fields=["document_type", "is_pdf"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated {title_count} records with [PDF] in title"
                    )
                )

        # Check URLs with pdf in them
        url_pdfs = ProcessedResult.objects.filter(document_type="webpage").exclude(
            is_pdf=True
        )

        pdf_url_count = 0
        with transaction.atomic():
            for result in url_pdfs:
                url_lower = result.url.lower()
                # Check various PDF indicators in URL
                if (
                    ".pdf" in url_lower
                    or "pdf" in url_lower.split("/")[-1]
                    or "/pdf/" in url_lower
                    or "-pdf-" in url_lower
                ):
                    result.document_type = "pdf"
                    result.is_pdf = True
                    result.save(update_fields=["document_type", "is_pdf"])
                    pdf_url_count += 1

        if pdf_url_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated {pdf_url_count} records with PDF indicators in URL"
                )
            )

        # Final summary
        total_pdfs = ProcessedResult.objects.filter(document_type="pdf").count()
        total_webpages = ProcessedResult.objects.filter(document_type="webpage").count()

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("FINAL SUMMARY:")
        self.stdout.write(f"Total PDFs: {total_pdfs}")
        self.stdout.write(f"Total Webpages: {total_webpages}")
        self.stdout.write("=" * 50)
