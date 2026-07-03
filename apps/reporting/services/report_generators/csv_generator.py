"""
CSV report generator implementation.

Supports export of search results, bibliographies, duplicate audits,
IRR metrics, and decision audit trails for PRISMA 2020 compliance.
"""

import csv
from io import StringIO
from typing import TYPE_CHECKING

from . import ReportGenerator

if TYPE_CHECKING:
    from apps.reporting.models import ExportReport


class CSVReportGenerator(ReportGenerator):
    """Generate CSV reports for data export."""

    def generate(self, report: "ExportReport", data: dict) -> bytes:
        """Generate CSV report content."""
        output = StringIO()

        if report.report_type == "results_summary":
            self._generate_results_csv(output, data)
            # Add IRR metrics section if dual-screening is enabled
            if data.get("irr_metrics") and self._has_irr_data(data.get("irr_metrics")):
                output.write("\n")  # Separator
                self._generate_irr_metrics_csv(output, data.get("irr_metrics"))
        elif report.report_type == "bibliography":
            self._generate_bibliography_csv(output, data)
        elif report.report_type == "duplicates_audit":
            self._generate_duplicates_csv(output, data)
        elif report.report_type == "irr_metrics":
            self._generate_irr_metrics_csv(output, data.get("irr_metrics", []))
        elif report.report_type == "audit_trail":
            self._generate_audit_trail_csv(output, data)
        else:
            # Default to results summary format
            self._generate_results_csv(output, data)

        return output.getvalue().encode("utf-8")

    def _has_irr_data(self, irr_metrics) -> bool:
        """Check if IRR metrics contain data."""
        if irr_metrics is None:
            return False
        # Handle QuerySet or list
        if hasattr(irr_metrics, "exists"):
            return irr_metrics.exists()
        return len(irr_metrics) > 0

    def get_content_type(self) -> str:
        """Get MIME content type for CSV."""
        return "text/csv"

    def get_file_extension(self) -> str:
        """Get file extension for CSV."""
        return "csv"

    def _generate_results_csv(self, output: StringIO, data: dict) -> None:
        """Generate CSV with search results."""
        writer = csv.writer(output)

        # Write header - only essential metadata fields
        headers = [
            "SERP Identifier",
            "Search String",
            "Title",
            "URL",
            "Decision",
            "Exclusion Reason",
            "Notes",
        ]
        writer.writerow(headers)

        # Write data rows
        results = data.get("results", [])
        for result in results:
            row = [
                result.get("id", ""),  # SERP identifier
                result.get("query_text", ""),  # Search string that found this result
                result.get("title", ""),
                result.get("url", ""),
                result.get("decision", ""),
                result.get("exclusion_reason", ""),
                result.get("notes", ""),
            ]
            writer.writerow(row)

    def _generate_bibliography_csv(self, output: StringIO, data: dict) -> None:
        """Generate CSV with bibliography entries."""
        writer = csv.writer(output)

        # Write header - only essential metadata fields
        headers = ["SERP Identifier", "Search String", "Title", "URL"]
        writer.writerow(headers)

        # Write bibliography entries
        entries = data.get("bibliography_entries", [])
        for entry in entries:
            row = [
                entry.get("id", ""),  # SERP identifier
                entry.get("query_text", ""),  # Search string that found this result
                entry.get("title", ""),
                entry.get("url", ""),
            ]
            writer.writerow(row)

    def _generate_duplicates_csv(self, output: StringIO, data: dict) -> None:
        """Generate CSV with duplicate audit trail."""
        writer = csv.writer(output)

        # Write header - duplicate audit trail structure
        headers = [
            "SERP Identifier",
            "Search String",
            "Title",
            "URL",
            "Detection Method",
        ]
        writer.writerow(headers)

        # Write duplicate entries (URL-based deduplication via ProcessedResult status)
        duplicates = data.get("duplicates", [])
        for duplicate in duplicates:
            row = [
                duplicate.get("id", ""),
                duplicate.get("query_text", ""),
                duplicate.get("title", ""),
                duplicate.get("url", ""),
                duplicate.get("detection_method", "url_match"),
            ]
            writer.writerow(row)

    def _generate_irr_metrics_csv(self, output: StringIO, irr_metrics) -> None:
        """
        Generate CSV with Inter-Rater Reliability metrics.

        Outputs Cohen's Kappa, percentage agreement, and reviewer pair breakdowns
        for PRISMA 2020 compliance and dual-screening quality assurance.
        """
        writer = csv.writer(output)

        # Write section header
        writer.writerow(["## Inter-Rater Reliability Metrics"])
        writer.writerow([])

        # Write IRR data header
        headers = [
            "Reviewer A",
            "Reviewer B",
            "Cohen's Kappa",
            "Percentage Agreement",
            "Total Comparisons",
            "Agreements",
            "Disagreements",
            "Meets Cochrane Threshold (>=0.70)",
            "Screening Stage",
            "Calculated At",
        ]
        writer.writerow(headers)

        # Handle QuerySet or list of IRR metrics
        metrics_list = list(irr_metrics) if irr_metrics else []

        for metric in metrics_list:
            # Handle both dict and model object access
            if hasattr(metric, "cohens_kappa"):
                # Model object
                kappa = metric.cohens_kappa
                reviewer_a_name = self._get_reviewer_name(metric.reviewer_a)
                reviewer_b_name = self._get_reviewer_name(metric.reviewer_b)
                row = [
                    reviewer_a_name,
                    reviewer_b_name,
                    f"{kappa:.3f}" if kappa is not None else "N/A",
                    f"{metric.percentage_agreement:.1f}%"
                    if metric.percentage_agreement is not None
                    else "N/A",
                    metric.total_comparisons or 0,
                    metric.agreements or 0,
                    metric.disagreements or 0,
                    "Yes" if kappa is not None and kappa >= 0.70 else "No",
                    metric.screening_stage or "title_abstract",
                    metric.calculated_at.strftime("%Y-%m-%d %H:%M:%S")
                    if metric.calculated_at
                    else "",
                ]
            else:
                # Dictionary
                kappa = metric.get("cohens_kappa")
                row = [
                    metric.get("reviewer_a", ""),
                    metric.get("reviewer_b", ""),
                    f"{kappa:.3f}" if kappa is not None else "N/A",
                    f"{metric.get('percentage_agreement', 0):.1f}%",
                    metric.get("total_comparisons", 0),
                    metric.get("agreements", 0),
                    metric.get("disagreements", 0),
                    "Yes" if kappa is not None and kappa >= 0.70 else "No",
                    metric.get("screening_stage", "title_abstract"),
                    metric.get("calculated_at", ""),
                ]
            writer.writerow(row)

        # Write summary if there are metrics
        if metrics_list:
            writer.writerow([])
            self._write_irr_summary(writer, metrics_list)

    def _get_reviewer_name(self, reviewer) -> str:
        """Get display name for a reviewer."""
        if reviewer is None:
            return "All Reviewers"
        if hasattr(reviewer, "get_full_name"):
            full_name = reviewer.get_full_name()
            if full_name and full_name.strip():
                return full_name.strip()
        if hasattr(reviewer, "username"):
            return reviewer.username
        return str(reviewer)

    def _write_irr_summary(self, writer, metrics_list) -> None:
        """Write summary statistics for IRR metrics."""
        writer.writerow(["## IRR Summary"])

        # Calculate aggregate statistics
        kappa_values = []
        total_comparisons = 0
        total_agreements = 0
        total_disagreements = 0

        for metric in metrics_list:
            if hasattr(metric, "cohens_kappa"):
                if metric.cohens_kappa is not None:
                    kappa_values.append(metric.cohens_kappa)
                total_comparisons += metric.total_comparisons or 0
                total_agreements += metric.agreements or 0
                total_disagreements += metric.disagreements or 0
            else:
                kappa = metric.get("cohens_kappa")
                if kappa is not None:
                    kappa_values.append(kappa)
                total_comparisons += metric.get("total_comparisons", 0)
                total_agreements += metric.get("agreements", 0)
                total_disagreements += metric.get("disagreements", 0)

        # Write summary rows
        if kappa_values:
            avg_kappa = sum(kappa_values) / len(kappa_values)
            min_kappa = min(kappa_values)
            max_kappa = max(kappa_values)
            meets_threshold = all(k >= 0.70 for k in kappa_values)

            writer.writerow(["Average Cohen's Kappa", f"{avg_kappa:.3f}"])
            writer.writerow(["Min Kappa", f"{min_kappa:.3f}"])
            writer.writerow(["Max Kappa", f"{max_kappa:.3f}"])
            writer.writerow(["Total Comparisons", total_comparisons])
            writer.writerow(["Total Agreements", total_agreements])
            writer.writerow(["Total Disagreements", total_disagreements])
            writer.writerow(
                [
                    "Overall Agreement Rate",
                    f"{(total_agreements / total_comparisons * 100):.1f}%"
                    if total_comparisons > 0
                    else "N/A",
                ]
            )
            writer.writerow(
                [
                    "All Pairs Meet Cochrane Threshold",
                    "Yes" if meets_threshold else "No",
                ]
            )

    def _generate_audit_trail_csv(self, output: StringIO, data: dict) -> None:
        """
        Generate CSV with decision audit trail for PRISMA Item 7 compliance.

        Exports all reviewer decisions with timestamps and metadata.
        """
        writer = csv.writer(output)

        # Write header
        headers = [
            "Result ID",
            "Result Title",
            "Result URL",
            "Reviewer",
            "Decision",
            "Decision Date",
            "Exclusion Reason",
            "Notes",
            "Version",
            "Is Current",
        ]
        writer.writerow(headers)

        # Write audit trail entries
        decisions = data.get("decisions", [])
        for decision in decisions:
            if hasattr(decision, "decision_type"):
                # Model object (ReviewerDecision)
                row = [
                    str(decision.result_id) if hasattr(decision, "result_id") else "",
                    decision.result.title
                    if hasattr(decision, "result") and decision.result
                    else "",
                    decision.result.url
                    if hasattr(decision, "result") and decision.result
                    else "",
                    self._get_reviewer_name(decision.reviewer)
                    if hasattr(decision, "reviewer")
                    else "",
                    decision.decision_type
                    if hasattr(decision, "decision_type")
                    else "",
                    decision.created_at.strftime("%Y-%m-%d %H:%M:%S")
                    if hasattr(decision, "created_at") and decision.created_at
                    else "",
                    decision.exclusion_reason
                    if hasattr(decision, "exclusion_reason")
                    else "",
                    decision.notes if hasattr(decision, "notes") else "",
                    decision.version if hasattr(decision, "version") else 1,
                    "Yes"
                    if hasattr(decision, "is_current") and decision.is_current
                    else "No",
                ]
            else:
                # Dictionary
                row = [
                    decision.get("result_id", ""),
                    decision.get("result_title", ""),
                    decision.get("result_url", ""),
                    decision.get("reviewer", ""),
                    decision.get("decision", ""),
                    decision.get("decision_date", ""),
                    decision.get("exclusion_reason", ""),
                    decision.get("notes", ""),
                    decision.get("version", 1),
                    "Yes" if decision.get("is_current", True) else "No",
                ]
            writer.writerow(row)
