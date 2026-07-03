"""
IRR (Inter-Rater Reliability) report generator implementation.

Generates PDF reports with Cohen's Kappa metrics, percentage agreement,
conflict breakdown, and compliance recommendations for dual-reviewer screening.
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


class IRRReportGenerator(ReportGenerator):
    """Generate Inter-Rater Reliability reports using WeasyPrint."""

    def generate(self, report: "ExportReport", data: dict) -> bytes:
        """
        Generate IRR PDF report content.

        Args:
            report: ExportReport instance with metadata
            data: Dictionary containing IRR metrics:
                - cohens_kappa: float (-1 to 1)
                - cohens_kappa_ci_lower: float (95% CI lower bound)
                - cohens_kappa_ci_upper: float (95% CI upper bound)
                - percentage_agreement: float (0-100)
                - total_comparisons: int
                - agreements: int
                - disagreements: int
                - conflict_breakdown: dict with conflict type counts
                - meets_cochrane_standard: bool (kappa >= 0.70)
                - recommendation: str
                - reviewer_pairs: list of reviewer pair data
                - session: SearchSession instance
                - generated_at: datetime

        Returns:
            bytes: Generated PDF content
        """
        if HTML is None:
            error_msg = (
                "WeasyPrint is not installed. PDF generation requires WeasyPrint. "
                "Install it with: docker-compose -f docker-compose.dev.yml run --rm web pip install weasyprint"
            )
            logger.error(error_msg)
            raise ImportError(error_msg)

        # Determine template based on report type
        template = get_template("reporting/exports/irr_report.html")

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

    def _prepare_context(self, report: "ExportReport", data: dict) -> dict:
        """
        Prepare template context with IRR metrics and analysis.

        Args:
            report: ExportReport instance
            data: IRR metrics data

        Returns:
            dict: Template context with formatted IRR data
        """
        from django.utils import timezone

        # Calculate compliance status
        kappa = data.get("cohens_kappa", 0)
        meets_standard = kappa >= 0.70

        # Determine recommendation based on kappa value
        if kappa < 0.40:
            recommendation = (
                "Poor agreement. Recalibration required before continuing review."
            )
            severity = "critical"
        elif kappa < 0.60:
            recommendation = "Fair agreement. Reviewer recalibration recommended."
            severity = "warning"
        elif kappa < 0.70:
            recommendation = (
                "Moderate agreement. Monitor ongoing IRR and consider recalibration."
            )
            severity = "warning"
        elif kappa < 0.80:
            recommendation = (
                "Good agreement. Meets Cochrane minimum standard (κ ≥ 0.70)."
            )
            severity = "success"
        else:
            recommendation = "Excellent agreement. High-quality dual review process."
            severity = "success"

        return {
            "report": report,
            "session": data.get("session"),
            "data": data,
            "generated_at": data.get("generated_at", timezone.now()),
            "meets_standard": meets_standard,
            "recommendation": data.get("recommendation", recommendation),
            "severity": severity,
            "include_metadata": report.parameters.get("include_metadata", True),
        }

    def _convert_to_pdf(self, html_content: str) -> bytes:
        """
        Convert HTML content to PDF.

        Args:
            html_content: Rendered HTML template

        Returns:
            bytes: PDF content
        """
        pdf = HTML(string=html_content).write_pdf()  # type: ignore[reportOptionalCall]
        return pdf
