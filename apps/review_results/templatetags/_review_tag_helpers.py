"""
Shared helper functions for review template tags.

Consolidates duplicated rendering logic used by both simple_review_tags.py
(Workflow #1) and multi_reviewer_tags.py (Workflow #2).
"""

from __future__ import annotations

from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe

# -- SVG icon constants (used by completion indicators) --

_ICON_COMPLETE = (
    '<svg class="w-5 h-5 mr-2 text-success" fill="currentColor" viewBox="0 0 24 24">'
    '<path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 '
    "9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm13.36-1.814a.75.75 0 10-1.22-.872l-3.236 "
    '4.53L9.53 12.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.14-.094l3.75-5.25z" '
    'clip-rule="evenodd"></path>'
    "</svg>"
)

_ICON_NEARLY = (
    '<svg class="w-5 h-5 mr-2 text-primary" fill="currentColor" viewBox="0 0 24 24">'
    '<path fill-rule="evenodd" d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75s4.365 9.75 9.75 '
    "9.75 9.75-4.365 9.75-9.75S17.385 2.25 12 2.25zM12.75 6a.75.75 0 00-1.5 0v6c0 "
    '.414.336.75.75.75h4.5a.75.75 0 000-1.5h-3.75V6z" clip-rule="evenodd"></path>'
    "</svg>"
)

_ICON_IN_PROGRESS = (
    '<svg class="w-5 h-5 mr-2 text-warning" fill="currentColor" viewBox="0 0 24 24">'
    '<path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 '
    "9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm14.024-.983a1.125 1.125 0 010 "
    "1.966l-5.603 3.113A1.125 1.125 0 019 15.113V8.887c0-.857.921-1.4 1.671-.983l5.603 "
    '3.113z" clip-rule="evenodd"></path>'
    "</svg>"
)

_ICON_NOT_STARTED = (
    '<svg class="w-5 h-5 mr-2 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
    '<circle cx="12" cy="12" r="10" stroke-width="2"></circle>'
    "</svg>"
)

# -- SVG icons for decision buttons --

_SVG_INCLUDE = (
    '<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
    '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>'
    "</svg>"
)

_SVG_EXCLUDE = (
    '<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
    '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>'
    "</svg>"
)

_SVG_MAYBE = (
    '<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
    '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
    'd="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 '
    '2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>'
    "</svg>"
)

# -- Button style constants --

_BUTTON_STYLES: dict[str, dict[str, str]] = {
    "include": {
        "active": "bg-success text-white hover:bg-success/90",
        "inactive": "border border-success text-success hover:bg-success/10",
        "svg": _SVG_INCLUDE,
        "label": "Include",
    },
    "exclude": {
        "active": "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        "inactive": "border border-destructive text-destructive hover:bg-destructive/10",
        "svg": _SVG_EXCLUDE,
        "label": "Exclude",
    },
    "maybe": {
        "active": "bg-warning text-white hover:bg-warning/90",
        "inactive": "border border-warning text-warning hover:bg-warning/10",
        "svg": _SVG_MAYBE,
        "label": "Maybe",
    },
}


def progress_bar_color(percentage: int | float) -> str:
    """Return Tailwind background class for a progress percentage."""
    if percentage == 100:
        return "bg-success"
    elif percentage >= 75:
        return "bg-primary"
    elif percentage >= 50:
        return "bg-warning"
    return "bg-destructive"


def render_progress_bar(
    percentage: int | float, reviewed: int, total: int
) -> SafeString:
    """Render a progress bar HTML fragment."""
    color = progress_bar_color(percentage)
    return format_html(
        '<div class="w-full bg-secondary rounded-full h-5 overflow-hidden">'
        '<div class="{} h-5 rounded-full text-xs text-white flex items-center '
        'justify-center transition-all duration-300" '
        'role="progressbar" style="width: {}%" '
        'aria-valuenow="{}" aria-valuemin="0" aria-valuemax="100">'
        "{}% Complete ({}/{})"
        "</div>"
        "</div>",
        color,
        percentage,
        percentage,
        percentage,
        reviewed,
        total,
    )


def render_decision_buttons(
    result_id: str,
    current_decision: str,
    onclick_fn: str = "makeDecision",
) -> SafeString:
    """
    Render Include/Exclude/Maybe decision buttons.

    Args:
        result_id: UUID of the ProcessedResult.
        current_decision: Current decision string (include/exclude/maybe/pending).
        onclick_fn: JavaScript function name for the onclick handler.

    Returns:
        HTML string with three decision buttons.
    """
    buttons = []
    for decision_type, style in _BUTTON_STYLES.items():
        css_class = (
            style["active"] if current_decision == decision_type else style["inactive"]
        )
        # Last button (maybe) has no mr-1
        mr = " mr-1" if decision_type != "maybe" else ""
        buttons.append(
            format_html(
                '<button class="inline-flex items-center px-2 py-1 text-xs rounded{} {}" '
                'data-testid="{}-btn-{}" '
                "onclick=\"{}('{}', '{}')\">"
                "{}{}"
                "</button>",
                mr,
                css_class,
                decision_type,
                result_id,
                onclick_fn,
                result_id,
                decision_type,
                mark_safe(style["svg"]),
                style["label"],
            )
        )

    # SECURITY: Safe because all HTML is generated by format_html() which escapes user input.
    # result_id (UUID) is escaped by format_html(). Button classes are trusted constants.
    return mark_safe("".join(buttons))  # nosec B703, B308


def card_class_for_decision(decision: str) -> str:
    """Return Tailwind background class for a decision state."""
    mapping = {
        "include": "bg-success/5",
        "exclude": "bg-destructive/5",
        "maybe": "bg-warning/5",
    }
    return mapping.get(decision, "")


def render_completion_indicator(percentage: int, label: str = "") -> SafeString:
    """
    Render a completion indicator with icon and text.

    Args:
        percentage: Completion percentage (0-100).
        label: Optional prefix for 100% text (e.g. "Your Review" becomes "Your Review Complete").
    """
    if percentage == 100:
        icon_svg = _ICON_COMPLETE
        text = f"{label} Complete".strip() if label else "Review Complete"
    elif percentage >= 75:
        icon_svg = _ICON_NEARLY
        text = "Nearly Complete"
    elif percentage > 0:
        icon_svg = _ICON_IN_PROGRESS
        text = "In Progress"
    else:
        icon_svg = _ICON_NOT_STARTED
        text = "Not Started"

    return format_html(
        '<div class="flex items-center">{}<span>{} ({}%)</span></div>',
        mark_safe(icon_svg),
        text,
        percentage,
    )


def truncate_notes(notes: str | None, max_length: int = 100) -> str:
    """Truncate notes to max_length with ellipsis, or return 'No notes'."""
    if not notes:
        return "No notes"
    if len(notes) <= max_length:
        return notes
    return notes[:max_length] + "..."
