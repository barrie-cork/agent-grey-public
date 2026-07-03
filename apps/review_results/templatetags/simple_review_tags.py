"""
Simple template tags for review results.
Provides basic filters and tags for displaying simple Include/Exclude interface.
"""

from __future__ import annotations

from typing import Any

from django import template
from django.utils.safestring import SafeString

from apps.results_manager.models import ProcessedResult

from ..models import SimpleReviewDecision
from ..services.simple_review_progress_service import SimpleReviewProgressService
from ._review_tag_helpers import (
    card_class_for_decision,
    render_completion_indicator,
    render_decision_buttons,
    render_progress_bar,
    truncate_notes,
)

register = template.Library()


def _get_simple_decision(result: ProcessedResult) -> str:
    """Look up the current simple review decision for a result."""
    try:
        decision = SimpleReviewDecision.objects.get(result=result)
        return decision.decision
    except SimpleReviewDecision.DoesNotExist:
        return "pending"


@register.simple_tag
def review_progress_bar(session_id: str) -> SafeString:
    """Render a simple progress bar for review completion."""
    service = SimpleReviewProgressService()
    progress = service.get_progress_summary(session_id)
    return render_progress_bar(
        progress["completion_percentage"],
        int(progress["reviewed_count"]),
        int(progress["total_results"]),
    )


@register.simple_tag
def quick_decision_buttons(result: ProcessedResult) -> SafeString:
    """Render quick decision buttons (Include/Exclude/Maybe)."""
    current_decision = _get_simple_decision(result)
    return render_decision_buttons(
        result_id=str(result.id),
        current_decision=current_decision,
        onclick_fn="makeDecision",
    )


@register.simple_tag
def quick_decision_card_class(result: ProcessedResult) -> str:
    """Return the Tailwind background class for the result card based on current simple decision."""
    current_decision = _get_simple_decision(result)
    return card_class_for_decision(current_decision)


@register.filter
def review_notes_preview(result: ProcessedResult, max_length: int = 100) -> str:
    """Show preview of review notes for a result."""
    try:
        decision = SimpleReviewDecision.objects.get(result=result)
        return truncate_notes(decision.notes, max_length)
    except SimpleReviewDecision.DoesNotExist:
        return "No notes"


@register.simple_tag(takes_context=True)
def review_completion_indicator(context: dict[str, Any], session_id: str) -> SafeString:
    """
    Show review completion indicator with status.

    Workflow-aware: uses ReviewerDecision for Workflow #2, SimpleReviewDecision
    for Workflow #1.
    """
    session = context.get("session")
    request = context.get("request")
    user = request.user if request else None

    service = SimpleReviewProgressService()
    progress = service.get_progress_summary(str(session_id), session=session, user=user)
    percentage = int(progress["completion_percentage"])

    return render_completion_indicator(percentage)


@register.inclusion_tag("review_results/tags/simple_review_stats.html")
def simple_review_stats(session_id: str) -> dict[str, Any]:
    """Render simple review statistics."""
    service = SimpleReviewProgressService()
    progress = service.get_progress_summary(session_id)
    return {
        "session_id": session_id,
        "progress": progress,
        "file_type_filtered_count": progress.get("file_type_filtered_count", 0),
    }


@register.filter
def replace(value: str, arg: str) -> str:
    """
    Replace occurrences of a string with another string.

    Usage:
        {{ "hello_world"|replace:"_: " }}  -> "hello world"
    """
    if not value or not arg:
        return value

    try:
        old, new = arg.split(":", 1)
        return value.replace(old, new)
    except (ValueError, AttributeError):
        return value


@register.filter
def div(value: Any, arg: Any) -> float:
    """
    Divide value by arg for template calculations.

    Usage:
        {{ total_results|div:total_groups }}  -> average group size
    """
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0
