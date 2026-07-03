"""
Custom template tags for SearchExecution and API integration rendering.

These tags provide convenient filters and tags for displaying
execution status, performance metrics, and cost information.
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.timesince import timesince

from ..models import SearchExecution
from ..recovery import recovery_manager
from ..utils import get_execution_statistics

register = template.Library()


@register.filter
def execution_status_badge(execution: SearchExecution) -> str:
    """
    Render a status badge for search execution.

    Args:
        execution: SearchExecution instance

    Returns:
        HTML string with styled badge
    """
    # Tailwind semantic status colours
    status_colors = {
        "pending": "bg-secondary text-secondary-foreground",
        "running": "bg-primary text-primary-foreground",
        "completed": "bg-success text-white",
        "failed": "bg-destructive text-destructive-foreground",
        "cancelled": "bg-warning text-white",
        "rate_limited": "bg-warning text-white",
    }

    color = status_colors.get(
        execution.status, "bg-secondary text-secondary-foreground"
    )
    display_text = execution.get_status_display()

    return format_html(
        '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {}">{}</span>',
        color,
        display_text,
    )


@register.filter
def format_duration(seconds: float) -> str:
    """
    Format execution duration in human-readable format.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string
    """
    if not seconds:
        return "N/A"

    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}min"
    hours = seconds / 3600
    return f"{hours:.1f}h"


@register.simple_tag
def execution_status_message(execution: SearchExecution) -> str:
    """
    Render execution status message (no progress bar).

    Args:
        execution: SearchExecution instance

    Returns:
        HTML string with status message
    """
    # Tailwind semantic status colours
    status_messages = {
        "pending": ("text-muted-foreground", "Pending execution"),
        "running": ("text-primary", "Executing query"),
        "completed": ("text-success", "Completed"),
        "failed": ("text-destructive", "Failed"),
        "cancelled": ("text-warning", "Cancelled"),
        "rate_limited": ("text-warning", "Rate limited - waiting"),
    }

    css_class, message = status_messages.get(
        execution.status, ("text-muted-foreground", "Unknown")
    )

    # If there's a current_step, use that instead
    if execution.current_step:
        message = execution.current_step

    return format_html('<span class="{}">{}</span>', css_class, message)


@register.inclusion_tag("serp_execution/tags/execution_summary.html")
def execution_summary_card(execution: SearchExecution):
    """
    Render a summary card for search execution.

    Args:
        execution: SearchExecution instance

    Returns:
        Context for the execution summary template
    """
    return {
        "execution": execution,
        "can_retry": execution.can_retry(),
        "duration_formatted": format_duration(execution.duration_seconds or 0),
        "time_since_created": timesince(execution.created_at),
    }


@register.filter
def engine_icon(engine_name: str) -> str:
    """
    Return an SVG icon for search engines.

    Args:
        engine_name: Name of the search engine

    Returns:
        HTML string with icon
    """
    # Default search icon SVG
    default_svg = (
        '<svg class="w-4 h-4 mr-1 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24" title="{}">'
        '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>'
        "</svg>"
    )

    # Engine-specific icons (all use search icon with different colours for simplicity)
    icons = {
        "google": '<svg class="w-4 h-4 mr-1 inline-block text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24" title="Google"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>',
        "bing": '<svg class="w-4 h-4 mr-1 inline-block text-primary/80" fill="none" stroke="currentColor" viewBox="0 0 24 24" title="Bing"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>',
        "duckduckgo": '<svg class="w-4 h-4 mr-1 inline-block text-success" fill="currentColor" viewBox="0 0 24 24" title="DuckDuckGo"><path fill-rule="evenodd" d="M12.516 2.17a.75.75 0 00-1.032 0 11.209 11.209 0 01-7.877 3.08.75.75 0 00-.722.515A12.74 12.74 0 002.25 9.75c0 5.942 4.064 10.933 9.563 12.348a.749.749 0 00.374 0c5.499-1.415 9.563-6.406 9.563-12.348 0-1.39-.223-2.73-.635-3.985a.75.75 0 00-.722-.516l-.143.001c-2.996 0-5.717-1.17-7.734-3.08zm3.094 8.016a.75.75 0 10-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.14-.094l3.75-5.25z" clip-rule="evenodd"></path></svg>',
        "yahoo": '<svg class="w-4 h-4 mr-1 inline-block text-warning" fill="none" stroke="currentColor" viewBox="0 0 24 24" title="Yahoo"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>',
    }

    svg = icons.get(engine_name.lower(), default_svg.format(engine_name.title()))

    return mark_safe(svg)


@register.simple_tag
def retry_button(execution: SearchExecution) -> str:
    """
    Render retry button if execution can be retried.

    Args:
        execution: SearchExecution instance

    Returns:
        HTML string with retry button or empty string
    """
    if not execution.can_retry():
        return ""

    return format_html(
        '<button class="inline-flex items-center px-2 py-1 text-xs border border-warning text-warning rounded hover:bg-warning/10" onclick="retryExecution(\'{}\')">'
        '<svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
        '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>'
        "</svg>Retry ({}/3)"
        "</button>",
        execution.id,
        execution.retry_count + 1,
    )


@register.filter
def failure_category_badge(execution: SearchExecution) -> str:
    """
    Render a badge for failure category.

    Args:
        execution: SearchExecution instance

    Returns:
        HTML string with failure category badge
    """
    if execution.status != "failed":
        return ""

    category = recovery_manager.get_error_category(execution.error_message)

    # Tailwind semantic status colours
    category_colors = {
        "rate_limit": "bg-warning text-white",
        "timeout": "bg-primary text-primary-foreground",
        "network": "bg-destructive text-destructive-foreground",
        "authentication": "bg-destructive text-destructive-foreground",
        "quota_exceeded": "bg-warning text-white",
        "api_error": "bg-destructive text-destructive-foreground",
        "unknown": "bg-secondary text-secondary-foreground",
    }

    color = category_colors.get(category, "bg-secondary text-secondary-foreground")
    display_name = category.replace("_", " ").title()

    return format_html(
        '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {} ml-1">{}</span>',
        color,
        display_name,
    )


@register.simple_tag
def session_execution_stats(session_id: str):
    """
    Get execution statistics for a session.

    Args:
        session_id: UUID of the SearchSession

    Returns:
        Dictionary with execution statistics
    """
    return get_execution_statistics(session_id)


@register.inclusion_tag("serp_execution/tags/metrics_dashboard.html")
def execution_metrics_dashboard(session):
    """
    Render execution metrics dashboard.

    Args:
        session: SearchSession instance

    Returns:
        Context for the metrics dashboard template
    """
    stats = get_execution_statistics(str(session.id))

    return {
        "session": session,
        "stats": stats,
        "has_executions": stats["total_executions"] > 0,
    }


@register.simple_tag
def execution_timeline_item(execution: SearchExecution) -> str:
    """
    Render a timeline item for execution.

    Args:
        execution: SearchExecution instance

    Returns:
        HTML string with timeline item
    """
    # SVG icons for each status with Tailwind semantic colours
    status_icons = {
        "pending": '<svg class="w-5 h-5 text-muted-foreground" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75s4.365 9.75 9.75 9.75 9.75-4.365 9.75-9.75S17.385 2.25 12 2.25zM12.75 6a.75.75 0 00-1.5 0v6c0 .414.336.75.75.75h4.5a.75.75 0 000-1.5h-3.75V6z" clip-rule="evenodd"></path></svg>',
        "running": '<svg class="w-5 h-5 text-primary animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>',
        "completed": '<svg class="w-5 h-5 text-success" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm13.36-1.814a.75.75 0 10-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.14-.094l3.75-5.25z" clip-rule="evenodd"></path></svg>',
        "failed": '<svg class="w-5 h-5 text-destructive" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75s4.365 9.75 9.75 9.75 9.75-4.365 9.75-9.75S17.385 2.25 12 2.25zm-1.72 6.97a.75.75 0 10-1.06 1.06L10.94 12l-1.72 1.72a.75.75 0 101.06 1.06L12 13.06l1.72 1.72a.75.75 0 101.06-1.06L13.06 12l1.72-1.72a.75.75 0 10-1.06-1.06L12 10.94l-1.72-1.72z" clip-rule="evenodd"></path></svg>',
        "cancelled": '<svg class="w-5 h-5 text-warning" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zM9 8.25a.75.75 0 00-.75.75v6c0 .414.336.75.75.75h6a.75.75 0 00.75-.75V9a.75.75 0 00-.75-.75H9z" clip-rule="evenodd"></path></svg>',
        "rate_limited": '<svg class="w-5 h-5 text-warning" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M12.516 2.17a.75.75 0 00-1.032 0 11.209 11.209 0 01-7.877 3.08.75.75 0 00-.722.515A12.74 12.74 0 002.25 9.75c0 5.942 4.064 10.933 9.563 12.348a.749.749 0 00.374 0c5.499-1.415 9.563-6.406 9.563-12.348 0-1.39-.223-2.73-.635-3.985a.75.75 0 00-.722-.516l-.143.001c-2.996 0-5.717-1.17-7.734-3.08zM12 8.25a.75.75 0 01.75.75v3.75a.75.75 0 01-1.5 0V9a.75.75 0 01.75-.75zM12 15a.75.75 0 00-.75.75v.008c0 .414.336.75.75.75h.008a.75.75 0 00.75-.75v-.008a.75.75 0 00-.75-.75H12z" clip-rule="evenodd"></path></svg>',
    }

    icon_svg = status_icons.get(
        execution.status,
        '<svg class="w-5 h-5 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke-width="2"></circle></svg>',
    )
    time_display = timesince(execution.created_at)

    error_html = ""
    if execution.error_message:
        error_html = f'<div class="mt-1"><small class="text-destructive">{execution.error_message[:100]}...</small></div>'

    return format_html(
        '<div class="timeline-item flex gap-3">'
        '<div class="timeline-marker flex-shrink-0">'
        "{}"
        "</div>"
        '<div class="timeline-content">'
        '<h6 class="mb-1 font-medium">{} - {}</h6>'
        '<small class="text-muted-foreground">{} ago</small>'
        "{}"
        "</div>"
        "</div>",
        mark_safe(icon_svg),
        execution.get_status_display(),
        execution.search_engine.title(),
        time_display,
        mark_safe(error_html),
    )


@register.filter
def api_health_indicator(success_rate: float) -> str:
    """
    Show API health indicator based on success rate.

    Args:
        success_rate: Success rate percentage

    Returns:
        HTML string with health indicator
    """
    if success_rate >= 95:
        return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-success text-white">Excellent</span>'
    if success_rate >= 85:
        return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary text-primary-foreground">Good</span>'
    if success_rate >= 70:
        return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-warning text-white">Fair</span>'
    return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-destructive text-destructive-foreground">Poor</span>'
