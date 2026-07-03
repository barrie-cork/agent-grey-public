"""
Search result analysis service for reporting slice.
Business capability: Search result flow analysis and reporting.
"""

from apps.core.logging import ServiceLoggerMixin

# Use dependency injection instead of direct imports
from ..dependencies import get_results_manager, get_review_results, get_serp_execution


class SearchResultAnalysisService(ServiceLoggerMixin):
    """Service for analyzing search result flow through the system."""

    def __init__(self):
        """Initialize service with dependencies."""
        self.results_manager = get_results_manager()
        self.review_results = get_review_results()
        self.serp_execution = get_serp_execution()

    def generate_result_flow_summary(self, session_id: str):
        """
        Generate summary of search result flow through the system.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with result flow data (raw -> processed -> reviewed)
        """
        # Raw results retrieved from search
        raw_results_response = self.serp_execution.get_raw_results_count(session_id)
        # Extract count from response dict - get_raw_results_count returns a RawResultsCountResponse
        raw_count = (
            raw_results_response.get("count", 0)
            if isinstance(raw_results_response, dict)
            else raw_results_response
        )

        # Processed results (after deduplication)
        processed_results = self.results_manager.get_processed_results_for_session(
            session_id
        )
        processed_count = len(processed_results)

        # Review decisions
        inclusion_stats = self.review_results.get_inclusion_statistics(session_id)
        reviewed_count = inclusion_stats["total"]
        pending_count = processed_count - reviewed_count

        return {
            "session_id": session_id,
            "raw_results_retrieved": raw_count,
            "processed_results": processed_count,
            "duplicates_removed": raw_count - processed_count,
            "results_reviewed": reviewed_count,
            "results_pending": pending_count,
            "results_included": inclusion_stats["include"],
            "results_excluded": inclusion_stats["exclude"],
            "results_maybe": inclusion_stats["maybe"],
            "completion_percentage": (
                round((reviewed_count / processed_count * 100), 1)
                if processed_count > 0
                else 0
            ),
        }

    def get_document_type_distribution(self, session_id: str):
        """
        Get distribution of document types in processed results.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with document type counts
        """
        results = self.results_manager.get_processed_results_for_session(session_id)

        type_counts = {}
        for result in results:
            doc_type = result.get("file_type", "unknown")
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

        return type_counts

    def get_basic_statistics(self, session_id: str):
        """
        Get basic statistics about search results.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with basic statistics
        """
        results = self.results_manager.get_processed_results_for_session(session_id)
        total_count = len(results)

        # Count PDFs based on file_type
        pdf_count = sum(1 for r in results if r.get("file_type", "").lower() == "pdf")

        # Publication years (if available) - not in our interface, so skip for now
        year_counts = {}

        return {
            "total_results": total_count,
            "pdf_documents": pdf_count,
            "non_pdf_documents": total_count - pdf_count,
            "publication_years": year_counts,
        }

    def calculate_result_statistics(self, session_id: str):
        """
        Calculate comprehensive result statistics for a session.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with comprehensive statistics
        """
        # Get flow summary
        flow_summary = self.generate_result_flow_summary(session_id)

        # Get basic statistics
        basic_stats = self.get_basic_statistics(session_id)

        # Get document type distribution
        doc_types = self.get_document_type_distribution(session_id)

        # Calculate percentages
        total = basic_stats["total_results"]
        included_percentage = (
            (flow_summary["results_included"] / total * 100) if total > 0 else 0
        )
        excluded_percentage = (
            (flow_summary["results_excluded"] / total * 100) if total > 0 else 0
        )
        pending_percentage = (
            (flow_summary["results_pending"] / total * 100) if total > 0 else 0
        )

        return {
            "total_results": basic_stats["total_results"],
            "pdf_documents": basic_stats["pdf_documents"],
            "non_pdf_documents": basic_stats["non_pdf_documents"],
            "raw_results_retrieved": flow_summary["raw_results_retrieved"],
            "duplicates_removed": flow_summary["duplicates_removed"],
            "results_reviewed": flow_summary["results_reviewed"],
            "results_pending": flow_summary["results_pending"],
            "results_included": flow_summary["results_included"],
            "results_excluded": flow_summary["results_excluded"],
            "results_maybe": flow_summary["results_maybe"],
            "completion_percentage": flow_summary["completion_percentage"],
            "document_types": doc_types,
            "review_progress": {
                "reviewed": flow_summary["results_reviewed"],
                "pending": flow_summary["results_pending"],
                "total": basic_stats["total_results"],
            },
            # Add calculated percentages
            "included_count": flow_summary["results_included"],
            "excluded_count": flow_summary["results_excluded"],
            "pending_count": flow_summary["results_pending"],
            "included_percentage": round(included_percentage, 1),
            "excluded_percentage": round(excluded_percentage, 1),
            "pending_percentage": round(pending_percentage, 1),
        }

    def analyze_quality_distribution(self, session_id: str):
        """Analysis of document types and inclusion statistics."""
        return {
            "document_type_distribution": {},
            "quality_summary": {
                "high_quality": 0,
                "medium_quality": 0,
                "low_quality": 0,
                "total_reviewed": 0,
            },
            "inclusion_rate": 0.0,
            "pdf_inclusion_rate": 0.0,
            "distribution": {},
            "average_score": 0.0,
        }

    def _calculate_pdf_inclusion_rate(
        self, results: list, review_decisions: list
    ) -> float:
        """Calculate inclusion rate specifically for PDF documents."""
        pdf_results = [r for r in results if r.get("is_pdf", False)]
        if not pdf_results:
            return 0.0

        pdf_ids = {str(r.get("id")) for r in pdf_results}
        included_pdfs = sum(
            1
            for d in review_decisions
            if str(d.get("result_id")) in pdf_ids and d.get("decision") == "include"
        )

        return round((included_pdfs / len(pdf_results) * 100), 1)
