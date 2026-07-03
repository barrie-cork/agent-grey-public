"""
JSON report generator implementation.
"""

import json
from typing import TYPE_CHECKING

from django.utils import timezone

from . import ReportGenerator

if TYPE_CHECKING:
    from apps.reporting.models import ExportReport


class JSONReportGenerator(ReportGenerator):
    """Generate JSON reports for data export and API consumption."""

    def generate(self, report: "ExportReport", data: dict) -> bytes:
        """Generate JSON report content."""
        # Prepare output data
        output_data = {
            "metadata": {
                "report_id": str(report.id),
                "report_type": report.report_type,
                "generated_at": timezone.now().isoformat(),
                "session": {
                    "id": str(report.session.id),
                    "title": report.session.title,
                    "description": report.session.description,
                },
            }
        }

        # Add report-specific data
        if report.report_type == "prisma_flow":
            output_data["prisma_flow"] = data
        elif report.report_type == "results_summary":
            output_data["results"] = self._prepare_results_data(data)
        elif report.report_type == "bibliography":
            output_data["bibliography"] = data.get("bibliography_entries", [])
        else:
            # Include all data for other report types
            output_data["data"] = data

        # Convert to JSON with pretty printing
        json_str = json.dumps(output_data, indent=2, default=str)
        return json_str.encode("utf-8")

    def get_content_type(self) -> str:
        """Get MIME content type for JSON."""
        return "application/json"

    def get_file_extension(self) -> str:
        """Get file extension for JSON."""
        return "json"

    def _prepare_results_data(self, data: dict):
        """Prepare results data for JSON export."""
        results = data.get("results", [])

        return {
            "total_results": len(results),
            "included": sum(1 for r in results if r.get("decision") == "include"),
            "excluded": sum(1 for r in results if r.get("decision") == "exclude"),
            "maybe": sum(1 for r in results if r.get("decision") == "maybe"),
            "pending": sum(1 for r in results if r.get("decision") == "pending"),
            "results": results,
        }
