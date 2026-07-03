"""
Custom template tags for ProcessedResult rendering.

These tags provide convenient filters and tags for displaying
results, metadata, and processing statistics.
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ..models import ProcessedResult

register = template.Library()


@register.filter
def replace(value: str, args: str) -> str:
    """
    Replace occurrences of a string with another string.

    Usage: {{ value|replace:"old:new" }}
    """
    if not value:
        return value

    if ":" not in args:
        return value

    old, new = args.split(":", 1)
    return value.replace(old, new)


@register.filter
def document_type_badge(doc_type: str) -> str:
    """
    Simple document type badge.
    """
    display_name = doc_type.replace("_", " ").title() if doc_type else "Unknown"

    return format_html(
        '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-secondary text-secondary-foreground">{}</span>',
        display_name,
    )


@register.filter
def document_indicators(result: ProcessedResult) -> str:
    """
    Render simple document type indicators.

    Args:
        result: ProcessedResult instance

    Returns:
        HTML string with document indicators
    """
    indicators = []

    if result.is_pdf:
        indicators.append(
            '<svg class="w-5 h-5 text-destructive inline-block" fill="currentColor" viewBox="0 0 24 24" title="PDF document">'
            '<path fill-rule="evenodd" d="M5.625 1.5c-1.036 0-1.875.84-1.875 1.875v17.25c0 1.035.84 1.875 1.875 1.875h12.75c1.035 0 1.875-.84 1.875-1.875V12.75A3.75 3.75 0 0016.5 9h-1.875a1.875 1.875 0 01-1.875-1.875V5.25A3.75 3.75 0 009 1.5H5.625zM7.5 15a.75.75 0 01.75-.75h7.5a.75.75 0 010 1.5h-7.5A.75.75 0 017.5 15zm.75 2.25a.75.75 0 000 1.5H12a.75.75 0 000-1.5H8.25z" clip-rule="evenodd"></path>'
            '<path d="M12.971 1.816A5.23 5.23 0 0114.25 5.25v1.875c0 .207.168.375.375.375H16.5a5.23 5.23 0 013.434 1.279 9.768 9.768 0 00-6.963-6.963z"></path>'
            "</svg>"
        )
    else:
        indicators.append(
            '<svg class="w-5 h-5 text-primary inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24" title="Webpage">'
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"></path>'
            "</svg>"
        )

    if result.is_duplicate:
        indicators.append(
            '<svg class="w-5 h-5 text-muted-foreground inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24" title="Duplicate">'
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2"></path>'
            "</svg>"
        )
    elif result.processing_status == "filtered":
        indicators.append(
            '<svg class="w-5 h-5 text-muted-foreground inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24" title="Filtered">'
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path>'
            "</svg>"
        )

    # SECURITY: Safe to use mark_safe here because we only concatenate:
    # 1. Static SVG icon HTML (trusted, hardcoded strings)
    # 2. No user input is involved - all HTML is from trusted constants
    # All icon classes and attributes are hardcoded Tailwind components.
    return mark_safe(" ".join(indicators))  # nosec B703, B308


@register.filter
def truncate_title(title: str, max_length: int = 80) -> str:
    """
    Truncate title for display.

    Args:
        title: Original title
        max_length: Maximum length before truncation

    Returns:
        Truncated title
    """
    if not title:
        return ""

    if len(title) <= max_length:
        return title

    truncated = title[:max_length].rsplit(" ", 1)[0]
    return f"{truncated}..."


@register.inclusion_tag("results_manager/tags/result_card.html")
def result_summary_card(result: ProcessedResult):
    """
    Render a summary card for a processed result.

    Args:
        result: ProcessedResult instance

    Returns:
        Context for the result card template
    """
    return {
        "result": result,
        "domain": result.get_display_url(),
        "is_pdf": result.is_pdf,
        "is_duplicate": result.is_duplicate,
    }


@register.filter
def publication_year_badge(year: int) -> str:
    """
    Simple publication year badge.
    """
    if not year:
        return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-secondary text-muted-foreground">Unknown</span>'

    return format_html(
        '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-secondary text-secondary-foreground">{}</span>',
        year,
    )
