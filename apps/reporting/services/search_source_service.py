"""Service for computing per-provider search source breakdown."""

from apps.results_manager.models import ProcessedResult
from apps.review_results.models import SimpleReviewDecision


def get_search_source_breakdown(session_id: str) -> list[dict]:
    """Get per-provider breakdown of search results for a session.

    Queries SearchExecution grouped by serp_provider to compute
    per-provider result counts, unique results, and inclusion rates.

    Args:
        session_id: UUID of the SearchSession.

    Returns:
        List of dicts with keys: provider_key, display_name,
        queries_executed, total_results, unique_results,
        included_results, inclusion_rate.
    """
    from django.db.models import Count, Sum

    from apps.serp_execution.models import SearchExecution

    # Aggregate execution stats per provider
    provider_stats = (
        SearchExecution.objects.filter(query__session_id=session_id, status="completed")
        .values("serp_provider", "serp_provider_display")
        .annotate(
            queries_executed=Count("id"),
            total_results=Sum("results_count"),
        )
        .order_by("serp_provider")
    )

    breakdown = []
    for stat in provider_stats:
        provider_key = stat["serp_provider"]
        total = stat["total_results"] or 0

        # Count unique (non-duplicate) processed results from this provider
        unique_count = ProcessedResult.objects.filter(
            session_id=session_id,
            processing_status="success",
            raw_result__execution__serp_provider=provider_key,
        ).count()

        # Count included results from this provider
        included_count = SimpleReviewDecision.objects.filter(
            result__session_id=session_id,
            result__raw_result__execution__serp_provider=provider_key,
            decision="include",
        ).count()

        inclusion_rate = round((included_count / total * 100) if total > 0 else 0, 1)

        breakdown.append(
            {
                "provider_key": provider_key,
                "display_name": stat["serp_provider_display"] or provider_key,
                "queries_executed": stat["queries_executed"],
                "total_results": total,
                "unique_results": unique_count,
                "included_results": included_count,
                "inclusion_rate": inclusion_rate,
            }
        )

    return breakdown
