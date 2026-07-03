"""
PDF report generator implementation.
"""

import logging
from typing import TYPE_CHECKING

from django.template.loader import get_template

from . import ReportGenerator

if TYPE_CHECKING:
    from apps.reporting.models import ExportReport

logger = logging.getLogger(__name__)

# WeasyPrint import - handle gracefully if not installed
try:
    from weasyprint import HTML
except ImportError:
    HTML = None
    logger.warning("WeasyPrint not installed - PDF generation will not work")


class PDFReportGenerator(ReportGenerator):
    """Generate PDF reports using WeasyPrint."""

    def generate(self, report: "ExportReport", data: dict) -> bytes:
        """Generate PDF report content."""
        if HTML is None:
            # Log detailed error and provide instructions
            error_msg = (
                "WeasyPrint is not installed. PDF generation requires WeasyPrint. "
                "Install it with: docker-compose -f docker-compose.dev.yml run --rm web pip install weasyprint"
            )
            logger.error(error_msg)
            raise ImportError(error_msg)

        # Determine template based on report type
        template_path = self._get_template_path(report.report_type)
        template = get_template(template_path)

        # Prepare context
        context = self._prepare_context(report, data)

        # Render HTML
        html_content = template.render(context)

        # Convert to PDF
        return self._convert_to_pdf(html_content)

    def get_content_type(self) -> str:
        """Get MIME content type for PDF."""
        return "application/pdf"

    def get_file_extension(self) -> str:
        """Get file extension for PDF."""
        return "pdf"

    def _get_template_path(self, report_type: str) -> str:
        """Get template path based on report type."""
        template_map = {
            "full_report": "reporting/exports/full_report.html",
            "prisma_flow": "reporting/exports/prisma_flow.html",
            "search_strategy": "reporting/exports/search_strategy.html",
            "bibliography": "reporting/exports/bibliography.html",
        }
        return template_map.get(report_type, "reporting/exports/full_report.html")

    def _prepare_context(self, report: "ExportReport", data: dict) -> dict:
        """Prepare template context."""
        from django.utils import timezone

        return {
            "report": report,
            "session": report.session,
            "data": data,
            "generated_at": timezone.now(),
            "include_prisma_flow": report.parameters.get("include_prisma_flow", True),
            "include_checklist": report.parameters.get("include_checklist", False),
            "include_metadata": report.parameters.get("include_metadata", True),
        }

    def _convert_to_pdf(self, html_content: str) -> bytes:
        """Convert HTML content to PDF."""
        pdf = HTML(string=html_content).write_pdf()  # type: ignore[reportOptionalCall]
        return pdf
