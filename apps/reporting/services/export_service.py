"""
Export service for reporting slice.
Business capability: Data export and format conversion.
"""

import csv
import io
import json

from django.utils import timezone

from apps.core.logging import ServiceLoggerMixin
from apps.reporting.constants import ExportConstants


class ExportService(ServiceLoggerMixin):
    """Service for exporting data in various formats."""

    def generate_export_formats(self, data: dict, format_type: str):
        """
        Convert report data to various export formats.

        Args:
            data: Report data dictionary
            format_type: Export format ('json', 'csv', 'pdf')

        Returns:
            Dictionary with formatted data and metadata
        """
        export_result = {
            "format": format_type,
            "generated_at": timezone.now().isoformat(),
            "data": data,
            "file_info": {
                "filename": f"report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.{format_type}",
                "content_type": self.get_content_type(format_type),
                "estimated_size": self.estimate_file_size(data, format_type),
            },
        }

        return export_result

    def get_content_type(self, format_type: str) -> str:
        """
        Get MIME content type for export format.

        Args:
            format_type: The export format type (e.g., 'json', 'csv', 'pdf')

        Returns:
            MIME content type string
        """
        return ExportConstants.CONTENT_TYPES.get(
            format_type, ExportConstants.DEFAULT_CONTENT_TYPE
        )

    def estimate_file_size(self, data: dict, format_type: str) -> int:
        """
        Estimate file size for export format.

        Args:
            data: The data to be exported
            format_type: The export format type

        Returns:
            Estimated file size in bytes
        """
        # Basic estimation based on JSON size
        json_size = len(json.dumps(data, default=str))

        # Get format-specific multiplier
        multiplier = ExportConstants.SIZE_MULTIPLIERS.get(
            format_type, ExportConstants.DEFAULT_SIZE_MULTIPLIER
        )

        return int(json_size * multiplier)

    def export_to_csv(self, data: dict, export_type: str = "studies") -> str:
        """
        Export data to CSV format.

        Args:
            data: Data to export
            export_type: Type of export ('studies', 'queries', 'metrics')

        Returns:
            CSV string
        """
        output = io.StringIO()

        if export_type == "studies" and "studies" in data:
            writer = csv.DictWriter(output, fieldnames=ExportConstants.STUDY_CSV_FIELDS)
            writer.writeheader()

            for study in data["studies"]:
                writer.writerow(
                    {
                        "id": study.get("id", ""),
                        "title": study.get("title", ""),
                        "publication_year": study.get("publication_year", ""),
                        "document_type": study.get("document_type", ""),
                        "url": study.get("url", ""),
                        "has_full_text": study.get("has_full_text", False),
                    }
                )

        elif export_type == "queries" and "queries" in data:
            writer = csv.DictWriter(output, fieldnames=ExportConstants.QUERY_CSV_FIELDS)
            writer.writeheader()

            for query in data["queries"]:
                writer.writerow(
                    {
                        "id": query.get("id", ""),
                        "query_text": query.get("query_text", ""),
                        "population": query.get("pic_framework", {}).get(
                            "population", ""
                        ),
                        "interest": query.get("pic_framework", {}).get("interest", ""),
                        "context": query.get("pic_framework", {}).get("context", ""),
                        "search_engines": ", ".join(
                            query.get("parameters", {}).get("search_engines", [])
                        ),
                        "total_results": query.get("execution_results", {}).get(
                            "total_results", 0
                        ),
                        "success_rate": query.get("execution_results", {}).get(
                            "success_rate", 0
                        ),
                    }
                )

        return output.getvalue()

    def generate_export_summary(self, session_id: str, export_types: list):
        """
        Generate summary of available export options.

        Args:
            session_id: UUID of the SearchSession
            export_types: List of requested export types

        Returns:
            Dictionary with export options summary
        """
        from apps.results_manager.models import ProcessedResult
        from apps.review_results.models import SimpleReviewDecision

        # Count available data
        total_results = ProcessedResult.objects.filter(session__id=session_id).count()
        included_studies = SimpleReviewDecision.objects.filter(
            session__id=session_id, decision="include"
        ).count()

        export_summary = {
            "session_id": session_id,
            "data_available": {
                "total_results": total_results,
                "included_studies": included_studies,
                "has_prisma_data": total_results > 0,
                "has_search_strategy": True,  # Assume available if session exists
                "has_performance_metrics": total_results > 0,
            },
            "export_options": [],
            "recommended_formats": [],
        }

        # Available export options
        for export_type in export_types:
            if export_type in ExportConstants.EXPORT_TYPE_NAMES:
                available = True
                if export_type in ["prisma_flow"]:
                    available = total_results > 0
                elif export_type in ["study_characteristics", "bibliography"]:
                    available = included_studies > 0

                export_summary["export_options"].append(
                    {
                        "type": export_type,
                        "name": ExportConstants.EXPORT_TYPE_NAMES[export_type],
                        "formats": ExportConstants.EXPORT_FORMATS.get(export_type, []),
                        "available": available,
                    }
                )

        # Recommendations based on data availability
        if included_studies > 0:
            export_summary["recommended_formats"].extend(
                ["study_characteristics_csv", "bibliography_json", "prisma_flow_pdf"]
            )

        if total_results > 10:
            export_summary["recommended_formats"].append("performance_metrics_json")

        return export_summary

    def export_decision_audit_trail(self, session_id: str) -> str:
        """
        Export complete decision audit trail for PRISMA Item 7 compliance.

        Exports all reviewer decisions with metadata for institutional audits
        and PRISMA reporting requirements. Includes both single-reviewer and
        dual-reviewer screening data.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            CSV string with complete audit trail

        PRISMA Item 7 Compliance:
            This export provides the complete audit trail required for
            transparent reporting of the screening process, including
            individual reviewer decisions before conflict resolution.
        """
        from apps.review_results.models import ReviewerDecision

        output = io.StringIO()
        writer = csv.writer(output)

        # CSV header matching PRP specification (lines 387-391)
        headers = [
            "result_id",
            "reviewer_id",
            "reviewer_username",
            "decision",
            "exclusion_reason",
            "confidence_level",
            "notes",
            "decided_at",
            "time_spent_seconds",
            "report_accessed",
            "is_blinded",
            "screening_stage",
            "version",
        ]
        writer.writerow(headers)

        # Get all decisions for the session ordered by decision time
        decisions = (
            ReviewerDecision.objects.filter(result__session__id=session_id)
            .select_related("reviewer", "result")
            .order_by("decided_at")
        )

        # Write data rows
        for decision in decisions:
            row = [
                str(decision.result.id),
                str(decision.reviewer.id),
                decision.reviewer.username,
                decision.decision,
                decision.exclusion_reason or "",
                decision.get_confidence_level_display(),
                decision.notes or "",
                decision.decided_at.isoformat(),
                decision.time_spent_seconds or "",
                decision.report_accessed,
                decision.is_blinded,
                decision.screening_stage,
                decision.version,
            ]
            writer.writerow(row)

        self.log_info(
            f"Exported {decisions.count()} decisions for session {session_id}"
        )

        return output.getvalue()
