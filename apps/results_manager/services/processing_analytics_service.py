"""
Processing analytics service for results_manager slice.
Business capability: Processing statistics and basic result ordering.
"""

from django.db.models import Count, QuerySet
from django.utils import timezone

from apps.core.logging import ServiceLoggerMixin
from apps.results_manager.constants import ProcessingConstants


class ProcessingAnalyticsService(ServiceLoggerMixin):
    """Service for processing analytics and basic statistics."""

    def get_processing_statistics(self, session_id: str):
        """
        Get processing statistics for a session.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with processing statistics
        """
        from ..models import ProcessedResult

        results = ProcessedResult.objects.filter(session__id=session_id)

        if not results.exists():
            return self._empty_statistics()

        total_results = results.count()
        duplicates_removed = results.filter(
            processing_status="filtered",
            processing_error_category="duplicate",
        ).count()
        unique_results = total_results - duplicates_removed

        # Document type distribution
        doc_types = results.values("document_type").annotate(
            count=Count("document_type")
        )
        document_types = {
            item["document_type"] or "unknown": item["count"] for item in doc_types
        }

        # Publication year distribution
        years = (
            results.exclude(publication_year__isnull=True)
            .values("publication_year")
            .annotate(count=Count("publication_year"))
        )
        publication_years = {item["publication_year"]: item["count"] for item in years}

        # Other metrics
        pdf_count = results.filter(is_pdf=True).count()

        return {
            "total_results": total_results,
            "processed_results": total_results,
            "duplicates_removed": duplicates_removed,
            "unique_results": unique_results,
            "document_types": document_types,
            "publication_years": dict(sorted(publication_years.items(), reverse=True)),
            "pdf_count": pdf_count,
            "pdf_percentage": (
                round(
                    (
                        pdf_count
                        / total_results
                        * ProcessingConstants.PERCENTAGE_MULTIPLIER
                    ),
                    ProcessingConstants.DECIMAL_PLACES["percentage"],
                )
                if total_results > 0
                else 0
            ),
        }

    def get_results_for_review(
        self,
        session_id: str,
        limit: int = ProcessingConstants.DEFAULT_BATCH_SIZE,
    ) -> QuerySet:
        """
        Get results for manual review in simple order.

        Args:
            session_id: UUID of the SearchSession
            limit: Maximum number of results to return

        Returns:
            QuerySet of ProcessedResult instances ordered by processing time
        """
        from ..models import ProcessedResult

        results = ProcessedResult.objects.filter(
            session_id=session_id, is_reviewed=False
        )

        # Simple ordering - no complex scoring
        return results.order_by(
            "-publication_year",  # Recent publications first
            "-created_at",  # Recently processed first
        )[:limit]

    def export_results_summary(self, session_id: str):
        """
        Export a comprehensive summary of processed results.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with exportable results summary
        """
        from ..models import ProcessedResult

        results = ProcessedResult.objects.filter(session__id=session_id)
        stats = self.get_processing_statistics(session_id)

        # Get sample results for each document type (ordered by publication year - simplified approach)
        sample_results = {}
        for doc_type in stats["document_types"].keys():
            samples = results.filter(document_type=doc_type).order_by(
                "-publication_year", "-is_pdf"
            )[: ProcessingConstants.SAMPLE_RESULTS_LIMIT]
            sample_results[doc_type] = [
                {
                    "title": result.title,
                    "url": result.url,
                    "publication_year": result.publication_year,
                    "is_pdf": result.is_pdf,
                }
                for result in samples
            ]

        # Basic list of all results with essential metadata only
        all_results = [
            {
                "title": result.title,
                "url": result.url,
                "snippet": (
                    result.snippet[:200] + "..."
                    if len(result.snippet) > 200
                    else result.snippet
                ),
                "publication_year": result.publication_year,
                "source_organization": result.source_organization,
                "is_pdf": result.is_pdf,
                "is_duplicate": result.is_duplicate,
            }
            for result in results.order_by("-publication_year", "title")
        ]

        return {
            "session_id": session_id,
            "total_results": len(all_results),
            "basic_stats": {
                "total": stats["total_results"],
                "duplicates": stats["duplicates_removed"],
                "pdf_count": stats.get("pdf_count", 0),
            },
            "results": all_results,
            "export_timestamp": timezone.now().isoformat(),
        }

    def get_quality_distribution(self, session_id: str):
        """
        Get distribution of quality indicators across results.

        Args:
            session_id: UUID of the SearchSession

        Returns:
            Dictionary with quality metrics distribution
        """
        from ..models import ProcessedResult

        results = ProcessedResult.objects.filter(session__id=session_id)

        if not results.exists():
            return {"total_results": 0}

        total = results.count()

        # Basic processing statistics only
        return {
            "total_results": total,
            "pdf_count": results.filter(is_pdf=True).count(),
            "recent_count": (
                results.filter(publication_year__gte=2020).count()
                if results.filter(publication_year__isnull=False).exists()
                else 0
            ),
            "duplicate_count": results.filter(
                processing_status="filtered",
                processing_error_category="duplicate",
            ).count(),
        }

    def _empty_statistics(self):
        """Return empty statistics structure."""
        return ProcessingConstants.EMPTY_STATS_DEFAULTS.copy()
