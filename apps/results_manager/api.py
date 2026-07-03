"""
Internal API for results_manager slice.
VSA-compliant data access without exposing models.
"""


def get_processed_results_data(session_id: str):
    """Get processed results data for a session without exposing models."""
    from .models import ProcessedResult

    results = ProcessedResult.objects.filter(session__id=session_id)

    return [
        {
            "id": str(result.id),
            "title": result.title,
            "url": result.url,
            "snippet": result.snippet,
            "document_type": result.document_type,
            "is_pdf": result.is_pdf,
            "has_full_text": result.has_full_text,
            "publication_date": (
                result.publication_date.isoformat() if result.publication_date else None
            ),
            "is_duplicate": result.is_duplicate,
        }
        for result in results
    ]


def get_processed_results_count(session_id: str) -> int:
    """Get count of processed results for a session."""
    from .models import ProcessedResult

    return ProcessedResult.objects.filter(session__id=session_id).count()


def get_deduplication_stats(session_id: str):
    """Get deduplication statistics for a session.

    Source of truth: ProcessedResult records with processing_status='filtered'
    and processing_error_category='duplicate' (set by URLDeduplicationService).
    """
    from .models import ProcessedResult

    total_results = ProcessedResult.objects.filter(session__id=session_id).count()
    duplicates_removed = ProcessedResult.objects.filter(
        session__id=session_id,
        processing_status="filtered",
        processing_error_category="duplicate",
    ).count()
    unique_results = total_results - duplicates_removed

    return {
        "total_results": total_results,
        "duplicates_removed": duplicates_removed,
        "unique_results": unique_results,
        "deduplication_rate": (
            round((duplicates_removed / total_results * 100), 1)
            if total_results > 0
            else 0
        ),
    }
