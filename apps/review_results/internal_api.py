"""
Internal API for review_results slice.
VSA-compliant data access without exposing models.
"""


def get_review_decisions_data(session_id: str):
    """
    Get review decisions for a session without exposing models.
    """
    from .models import SimpleReviewDecision

    decisions = SimpleReviewDecision.objects.filter(
        session_id=session_id
    ).select_related("result", "reviewer")

    return [
        {
            "id": str(decision.id),
            "result_id": str(decision.result.id),
            "decision": decision.decision,
            "decision_display": decision.get_decision_display(),
            "exclusion_reason": decision.exclusion_reason,
            "exclusion_reason_display": (
                decision.get_exclusion_reason_display()
                if decision.exclusion_reason
                else ""
            ),
            "notes": decision.notes,
            "reviewed_at": decision.reviewed_at.isoformat(),
            "reviewer_id": str(decision.reviewer.id) if decision.reviewer else None,
        }
        for decision in decisions
    ]


def get_decision_counts(session_id: str):
    """Get decision counts for a session."""
    from django.db.models import Count

    from .models import SimpleReviewDecision

    decision_counts = (
        SimpleReviewDecision.objects.filter(session__id=session_id)
        .values("decision")
        .annotate(count=Count("decision"))
    )

    return {item["decision"]: item["count"] for item in decision_counts}


def _wf2_progress_counts(session) -> tuple[int, int, int, int]:
    """
    Return (included, excluded, maybe, reviewed) for a WF2 session.

    Mirrors the consensus logic in signals_denormalized._calculate_wf2_stats.
    Counts are per-result, not per-decision, to avoid double-counting when
    multiple reviewers have decided on the same result.
    """
    from .models import ConflictResolution, ReviewerDecision
    from .services.review_coordination_service import consensus_value

    # Read consensus criteria once from session config
    criteria = (
        session.current_configuration.consensus_criteria
        if session.current_configuration
        else "MAJORITY"
    )

    # Distinct results with at least one non-ABSTAIN, non-revote decision
    reviewed = (
        ReviewerDecision.objects.filter(result__session=session, is_revote=False)
        .exclude(decision="ABSTAIN")
        .values("result")
        .distinct()
        .count()
    )

    conflicted_result_ids = set(
        ConflictResolution.objects.filter(result__session=session).values_list(
            "result_id", flat=True
        )
    )

    # Bulk-fetch (result_id, decision, min_reviewers_required) for non-conflicted results.
    # Join through result to get min_reviewers_required in one query (no N+1).
    rows = list(
        ReviewerDecision.objects.filter(result__session=session, is_revote=False)
        .exclude(decision="ABSTAIN")
        .exclude(result_id__in=conflicted_result_ids)
        .values_list("result_id", "decision", "result__min_reviewers_required")
    )

    # Group decisions and min_req by result_id
    decisions_by_result: dict = {}
    min_req_by_result: dict = {}
    for result_id, decision, min_req in rows:
        decisions_by_result.setdefault(result_id, []).append(decision)
        min_req_by_result[result_id] = min_req

    # Bucket each non-conflicted result by its consensus winner
    counts: dict[str, int] = {"INCLUDE": 0, "EXCLUDE": 0, "MAYBE": 0}
    for result_id, values in decisions_by_result.items():
        min_req = min_req_by_result.get(result_id, 1) or 1
        winner = consensus_value(values, criteria, min_req)
        if winner in counts:
            counts[winner] += 1

    def _resolved_count(decision_value: str) -> int:
        return ConflictResolution.objects.filter(
            result__session=session,
            status=ConflictResolution.STATUS_RESOLVED,
            final_decision__decision=decision_value,
        ).count()

    included = counts["INCLUDE"] + _resolved_count("INCLUDE")
    excluded = counts["EXCLUDE"] + _resolved_count("EXCLUDE")
    maybe = counts["MAYBE"] + _resolved_count("MAYBE")

    return included, excluded, maybe, reviewed


def get_review_progress_stats(session_id: str):
    """Get review progress statistics for a session."""
    from apps.results_manager.api import get_processed_results_count
    from apps.review_manager.models import SearchSession

    total_results = get_processed_results_count(session_id)
    session = SearchSession.objects.select_related("current_configuration").get(
        id=session_id
    )
    cfg = session.current_configuration

    if cfg and cfg.is_workflow_2:
        included, excluded, maybe, reviewed = _wf2_progress_counts(session)
    else:
        from .models import SimpleReviewDecision

        decisions = SimpleReviewDecision.objects.filter(session__id=session_id)
        reviewed = decisions.exclude(decision="pending").count()
        included = decisions.filter(decision="include").count()
        excluded = decisions.filter(decision="exclude").count()
        maybe = decisions.filter(decision="maybe").count()

    pending = total_results - reviewed

    return {
        "total_results": total_results,
        "reviewed_results": reviewed,
        "pending_results": pending,
        "completion_percentage": (
            round((reviewed / total_results * 100), 1) if total_results > 0 else 0
        ),
        "included_results": included,
        "excluded_results": excluded,
        "maybe_results": maybe,
    }
