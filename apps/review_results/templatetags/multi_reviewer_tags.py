"""
Template tags for Workflow #2 (Independent Screening with multiple reviewers).

Provides blinding-aware template tags that only show the current user's decisions,
enforcing PRISMA 2020 dual-screening requirements.
"""

from __future__ import annotations

from django import template
from django.utils.safestring import mark_safe

from ..models import ReviewerCompletion, ReviewerDecision
from ._review_tag_helpers import (
    card_class_for_decision,
    render_completion_indicator,
    render_decision_buttons,
    render_progress_bar,
    truncate_notes,
)

register = template.Library()


def _get_reviewer_decision(result, user) -> str:
    """
    Look up the current reviewer's decision for a result.

    Uses annotated attribute first (performance), falls back to DB query.
    """
    if hasattr(result, "user_decision_type") and result.user_decision_type:
        return result.user_decision_type.lower()

    try:
        decision = ReviewerDecision.objects.get(
            result=result,
            reviewer=user,
            is_revote=False,
        )
        return decision.decision.lower()
    except ReviewerDecision.DoesNotExist:
        return "pending"
    except ReviewerDecision.MultipleObjectsReturned:
        decision = (
            ReviewerDecision.objects.filter(
                result=result, reviewer=user, is_revote=False
            )
            .order_by("-created_at")
            .first()
        )
        return decision.decision.lower() if decision else "pending"


def _get_user_review_progress(session, user) -> tuple[int, int, int]:
    """
    Get review progress for a user in a session.

    Returns:
        Tuple of (reviewed, total, percentage).
    """
    try:
        completion = ReviewerCompletion.objects.get(session=session, reviewer=user)
        reviewed = completion.reviewed_results
        total = completion.total_results
    except ReviewerCompletion.DoesNotExist:
        from apps.results_manager.models import ProcessedResult

        reviewed = (
            ReviewerDecision.objects.filter(
                result__session=session, reviewer=user, is_revote=False
            )
            .values("result")
            .distinct()
            .count()
        )
        total = ProcessedResult.objects.filter(session=session).count()

    percentage = int((reviewed / total) * 100) if total > 0 else 0
    return reviewed, total, percentage


@register.simple_tag(takes_context=True)
def reviewer_decision_buttons(context, result) -> str:
    """
    Render decision buttons for Workflow #2 (multi-reviewer independent screening).

    Shows only the current user's decision for this result, enforcing blinding.
    """
    request = context.get("request")
    session = context.get("session")

    if not request or not session:
        return mark_safe(
            '<span class="text-danger">Context error: missing request or session</span>'
        )

    current_decision = _get_reviewer_decision(result, request.user)
    return render_decision_buttons(
        result_id=str(result.id),
        current_decision=current_decision,
        onclick_fn="makeReviewerDecision",
    )


@register.simple_tag(takes_context=True)
def reviewer_decision_card_class(context, result) -> str:
    """Return the Tailwind background class for the result card based on current decision."""
    request = context.get("request")
    session = context.get("session")

    if not request or not session:
        return ""

    current_decision = _get_reviewer_decision(result, request.user)
    return card_class_for_decision(current_decision)


@register.filter
def reviewer_notes_preview(result, user, max_length: int = 100) -> str:
    """
    Show preview of review notes for Workflow #2 (per-reviewer notes).

    Only shows the current user's notes, enforcing blinding.
    """
    try:
        decision = ReviewerDecision.objects.get(
            result=result, reviewer=user, is_revote=False
        )
        return truncate_notes(decision.notes, max_length)
    except ReviewerDecision.DoesNotExist:
        return "No notes"
    except ReviewerDecision.MultipleObjectsReturned:
        decision = (
            ReviewerDecision.objects.filter(
                result=result, reviewer=user, is_revote=False
            )
            .order_by("-created_at")
            .first()
        )
        return truncate_notes(decision.notes if decision else None, max_length)


@register.simple_tag(takes_context=True)
def multi_reviewer_progress_bar(context, session) -> str:
    """Render progress bar for Workflow #2 showing current user's review progress."""
    request = context.get("request")

    if not request:
        return mark_safe(
            '<span class="text-danger">Context error: missing request</span>'
        )

    reviewed, total, percentage = _get_user_review_progress(session, request.user)
    return render_progress_bar(percentage, reviewed, total)


@register.simple_tag(takes_context=True)
def multi_reviewer_completion_indicator(context, session) -> str:
    """Show completion indicator for Workflow #2 (current user only)."""
    request = context.get("request")

    if not request:
        return mark_safe(
            '<span class="text-danger">Context error: missing request</span>'
        )

    _reviewed, _total, percentage = _get_user_review_progress(session, request.user)
    return render_completion_indicator(percentage, label="Your Review")


@register.inclusion_tag(
    "review_results/tags/multi_reviewer_stats.html", takes_context=True
)
def multi_reviewer_stats(context, session):
    """
    Render multi-reviewer statistics for Workflow #2.

    Shows current user's progress and blinded aggregate stats.
    """
    request = context.get("request")

    if not request:
        return {"error": "Context error: missing request"}

    reviewed, total, percentage = _get_user_review_progress(session, request.user)

    # Get aggregate stats (blinded -- no individual reviewer info)
    all_completions = ReviewerCompletion.objects.filter(session=session)
    total_reviewers = all_completions.count()
    completed_reviewers = all_completions.filter(is_complete=True).count()

    return {
        "session_id": str(session.id),
        "user_reviewed": reviewed,
        "total_results": total,
        "percentage": percentage,
        "total_reviewers": total_reviewers,
        "completed_reviewers": completed_reviewers,
    }
