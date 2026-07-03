"""
Custom template tags for reporting and data export.

These tags provide convenient filters and tags for displaying
reports, statistics, and export functionality.
"""

import json

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ..services.performance_analytics_service import PerformanceAnalyticsService
from ..services.prisma_reporting_service import PrismaReportingService
from ..utils.formatters import StatusFormatters

register = template.Library()


@register.filter
def format_large_number(value: int) -> str:
    """
    Format large numbers with appropriate suffixes.

    Args:
        value: Number to format

    Returns:
        Formatted number string
    """
    if not value:
        return "0"

    if value >= 1000000:
        return f"{value / 1000000:.1f}M"
    if value >= 1000:
        return f"{value / 1000:.1f}K"
    return str(value)


@register.filter
def percentage_badge(
    value: float, threshold_good: float = 75, threshold_fair: float = 50
) -> str:
    """
    Render a percentage as a colored badge.

    Args:
        value: Percentage value
        threshold_good: Threshold for good performance
        threshold_fair: Threshold for fair performance

    Returns:
        HTML string with colored badge
    """
    if not value:
        value = 0

    # Tailwind semantic status colours
    if value >= threshold_good:
        color = "bg-success text-white"
    elif value >= threshold_fair:
        color = "bg-warning text-white"
    else:
        color = "bg-destructive text-destructive-foreground"

    return format_html(
        '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {}">{:.0f}%</span>',
        color,
        value,
    )


@register.inclusion_tag("reporting/tags/prisma_flow_diagram.html")
def prisma_flow_diagram(session_id: str):
    """
    Render PRISMA flow diagram with data.

    Args:
        session_id: UUID of the SearchSession

    Returns:
        Context for PRISMA flow diagram template
    """
    service = PrismaReportingService()
    flow_data = service.generate_prisma_flow_data(session_id)

    return {
        "session_id": session_id,
        "flow_data": flow_data,
        "has_data": bool(flow_data),
    }


@register.simple_tag
def performance_metric_card(session_id: str, metric_type: str) -> str:
    """
    Render a performance metric card.

    Args:
        session_id: UUID of the SearchSession
        metric_type: Type of metric ('efficiency', 'relevance', 'cost')

    Returns:
        HTML string with metric card
    """
    service = PerformanceAnalyticsService()
    metrics = service.calculate_search_performance_metrics(session_id)

    # Card configs with inline SVG icons and Tailwind semantic colours
    card_configs = {
        "efficiency": {
            "title": "Search Efficiency",
            "icon": '<svg class="w-12 h-12 text-primary mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>',
            "value": f"{metrics.get('search_efficiency', {}).get('success_rate', 0)}%",
            "description": "Success Rate",
            "color": "primary",
        },
        "relevance": {
            "title": "Relevance",
            "icon": '<svg class="w-12 h-12 text-success mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>',
            "value": f"{metrics.get('relevance_metrics', {}).get('precision', 0)}%",
            "description": "Precision",
            "color": "success",
        },
        "cost": {
            "title": "Basic Metrics",
            "icon": '<svg class="w-12 h-12 text-primary mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>',
            "value": f"{metrics.get('search_efficiency', {}).get('success_rate', 0):.0f}%",
            "description": "Search Success Rate",
            "color": "primary",
        },
    }

    if metric_type not in card_configs:
        return ""

    config = card_configs[metric_type]

    # Tailwind card with semantic colour border
    border_class = (
        f"border-{config['color']}"
        if config["color"] in ["primary", "success"]
        else "border-border"
    )

    return format_html(
        '<div class="rounded-lg border {} bg-card shadow-sm h-full">'
        '<div class="p-6 text-center">'
        "{}"
        '<h3 class="text-lg font-semibold text-foreground">{}</h3>'
        '<h2 class="text-3xl font-bold text-{} my-2">{}</h2>'
        '<p class="text-muted-foreground">{}</p>'
        "</div>"
        "</div>",
        border_class,
        mark_safe(config["icon"]),
        config["title"],
        config["color"],
        config["value"],
        config["description"],
    )


@register.filter
def export_format_icon(format_type: str) -> str:
    """
    Get SVG icon for export format.

    Args:
        format_type: Export format type

    Returns:
        HTML string with icon
    """
    # SVG icons for each export format
    icons = {
        "pdf": '<svg class="w-5 h-5 text-destructive inline-block" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M5.625 1.5c-1.036 0-1.875.84-1.875 1.875v17.25c0 1.035.84 1.875 1.875 1.875h12.75c1.035 0 1.875-.84 1.875-1.875V12.75A3.75 3.75 0 0016.5 9h-1.875a1.875 1.875 0 01-1.875-1.875V5.25A3.75 3.75 0 009 1.5H5.625zM7.5 15a.75.75 0 01.75-.75h7.5a.75.75 0 010 1.5h-7.5A.75.75 0 017.5 15zm.75 2.25a.75.75 0 000 1.5H12a.75.75 0 000-1.5H8.25z" clip-rule="evenodd"></path><path d="M12.971 1.816A5.23 5.23 0 0114.25 5.25v1.875c0 .207.168.375.375.375H16.5a5.23 5.23 0 013.434 1.279 9.768 9.768 0 00-6.963-6.963z"></path></svg>',
        "csv": '<svg class="w-5 h-5 text-primary inline-block" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M5.625 1.5H9a3.75 3.75 0 013.75 3.75v1.875c0 1.036.84 1.875 1.875 1.875H16.5a3.75 3.75 0 013.75 3.75v7.875c0 1.035-.84 1.875-1.875 1.875H5.625a1.875 1.875 0 01-1.875-1.875V3.375c0-1.036.84-1.875 1.875-1.875zM9.75 17.25a.75.75 0 00-1.5 0V18a.75.75 0 001.5 0v-.75zm2.25-3a.75.75 0 01.75.75v3a.75.75 0 01-1.5 0v-3a.75.75 0 01.75-.75zm3.75-1.5a.75.75 0 00-1.5 0V18a.75.75 0 001.5 0v-5.25z" clip-rule="evenodd"></path><path d="M14.25 5.25a5.23 5.23 0 00-1.279-3.434 9.768 9.768 0 016.963 6.963A5.23 5.23 0 0016.5 7.5h-1.875a.375.375 0 01-.375-.375V5.25z"></path></svg>',
        "json": '<svg class="w-5 h-5 text-warning inline-block" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M5.625 1.5c-1.036 0-1.875.84-1.875 1.875v17.25c0 1.035.84 1.875 1.875 1.875h12.75c1.035 0 1.875-.84 1.875-1.875V12.75A3.75 3.75 0 0016.5 9h-1.875a1.875 1.875 0 01-1.875-1.875V5.25A3.75 3.75 0 009 1.5H5.625zM7.5 12.75a.75.75 0 01.75-.75h7.5a.75.75 0 010 1.5h-7.5a.75.75 0 01-.75-.75zm.75 2.25a.75.75 0 000 1.5h4.5a.75.75 0 000-1.5H8.25z" clip-rule="evenodd"></path><path d="M12.971 1.816A5.23 5.23 0 0114.25 5.25v1.875c0 .207.168.375.375.375H16.5a5.23 5.23 0 013.434 1.279 9.768 9.768 0 00-6.963-6.963z"></path></svg>',
    }

    icon_svg = icons.get(
        format_type,
        '<svg class="w-5 h-5 text-muted-foreground inline-block" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M5.625 1.5c-1.036 0-1.875.84-1.875 1.875v17.25c0 1.035.84 1.875 1.875 1.875h12.75c1.035 0 1.875-.84 1.875-1.875V12.75A3.75 3.75 0 0016.5 9h-1.875a1.875 1.875 0 01-1.875-1.875V5.25A3.75 3.75 0 009 1.5H5.625z" clip-rule="evenodd"></path></svg>',
    )

    return mark_safe(icon_svg)


@register.filter
def format_badge_class(format_type: str) -> str:
    """
    Get badge color class for export format.

    Args:
        format_type: Export format type

    Returns:
        Bootstrap color class for badge
    """
    badge_colors = {
        "pdf": "danger",
        "csv": "info",
        "json": "warning",
    }

    return badge_colors.get(format_type, "secondary")


@register.simple_tag
def study_characteristics_summary(session_id: str) -> str:
    """
    Generate summary of study characteristics.

    Args:
        session_id: UUID of the SearchSession

    Returns:
        HTML string with characteristics summary
    """
    from ..utils import (
        generate_study_characteristics_table,  # type: ignore[attr-defined]
    )

    characteristics = generate_study_characteristics_table(session_id)
    total_studies = characteristics["total_studies"]

    if total_studies == 0:
        return '<p class="text-muted-foreground">No included studies to summarize.</p>'

    # Get year range
    years = characteristics["summary_statistics"]["publication_years"]
    year_range = f"{min(years.keys())}-{max(years.keys())}" if years else "Unknown"

    # Get document types
    doc_types = list(characteristics["summary_statistics"]["document_types"].keys())[:3]
    types_text = ", ".join(doc_types) + ("..." if len(doc_types) > 3 else "")

    # Full text availability
    full_text_count = characteristics["summary_statistics"]["full_text_availability"]
    full_text_pct = (
        round(full_text_count / total_studies * 100, 1) if total_studies > 0 else 0
    )

    return format_html(
        '<div class="grid grid-cols-1 md:grid-cols-4 gap-4">'
        "<div>"
        '<h5 class="text-lg font-semibold text-foreground">{}</h5>'
        '<p class="text-muted-foreground">Total Studies</p>'
        "</div>"
        "<div>"
        '<h5 class="text-lg font-semibold text-foreground">{}</h5>'
        '<p class="text-muted-foreground">Publication Years</p>'
        "</div>"
        "<div>"
        '<h5 class="text-lg font-semibold text-foreground">{}%</h5>'
        '<p class="text-muted-foreground">Full Text Available</p>'
        "</div>"
        "<div>"
        '<h5 class="text-lg font-semibold text-foreground">{}</h5>'
        '<p class="text-muted-foreground">Document Types</p>'
        "</div>"
        "</div>",
        total_studies,
        year_range,
        full_text_pct,
        types_text,
    )


@register.simple_tag
def report_generation_status(report) -> str:
    """
    Show report generation status badge.

    Args:
        report: ExportReport instance

    Returns:
        HTML string with status badge
    """
    status = getattr(report, "status", "pending")
    return StatusFormatters.format_status_badge(status)


@register.inclusion_tag("reporting/tags/search_summary_table.html")
def search_summary_table(session_id: str):
    """
    Render search strategy summary table.

    Args:
        session_id: UUID of the SearchSession

    Returns:
        Context for search summary table
    """
    from ..utils import generate_search_strategy_report  # type: ignore[attr-defined]

    report_data = generate_search_strategy_report(session_id)

    return {
        "session_id": session_id,
        "report_data": report_data,
        "queries": report_data.get("queries", []),
        "execution_summary": report_data.get("execution_summary", {}),
    }


@register.filter
def format_cost(amount) -> str:
    """
    Format cost amount with currency symbol.

    Args:
        amount: Cost amount (Decimal or float)

    Returns:
        Formatted cost string
    """
    if not amount:
        return "$0.00"

    return f"${float(amount):.2f}"


@register.simple_tag
def export_button(session_id: str, format_type: str, report_type: str) -> str:
    """
    Render export button for specific format and report type.

    Args:
        session_id: UUID of the SearchSession
        format_type: Export format
        report_type: Type of report

    Returns:
        HTML string with export button
    """
    icon = export_format_icon(format_type)

    return format_html(
        '<button class="inline-flex items-center px-3 py-1.5 text-sm border border-primary text-primary rounded hover:bg-primary/10 mr-2" '
        "onclick=\"exportReport('{}', '{}', '{}')\">"
        "{} Export {}"
        "</button>",
        session_id,
        report_type,
        format_type,
        icon,
        format_type.upper(),
    )


@register.filter
def chart_data_json(data: dict) -> str:
    """
    Convert data to JSON for charts.

    Args:
        data: Data dictionary

    Returns:
        JSON string
    """
    return json.dumps(data, default=str)


@register.simple_tag
def prisma_compliance_indicator(session_id: str) -> str:
    """
    Show PRISMA compliance indicator.

    Args:
        session_id: UUID of the SearchSession

    Returns:
        HTML string with compliance indicator
    """
    from ..utils import export_prisma_checklist  # type: ignore[attr-defined]

    checklist = export_prisma_checklist(session_id)
    completion_pct = checklist.get("completion_summary", {}).get(
        "completion_percentage", 0
    )

    # SVG icons and Tailwind semantic colours for each compliance level
    if completion_pct >= 90:
        color = "text-success"
        icon = '<svg class="w-5 h-5 text-success mr-2" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm13.36-1.814a.75.75 0 10-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.14-.094l3.75-5.25z" clip-rule="evenodd"></path></svg>'
        text = "Highly Compliant"
    elif completion_pct >= 70:
        color = "text-warning"
        icon = '<svg class="w-5 h-5 text-warning mr-2" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M9.401 3.003c1.155-2 4.043-2 5.197 0l7.355 12.748c1.154 2-.29 4.5-2.599 4.5H4.645c-2.309 0-3.752-2.5-2.598-4.5L9.4 3.003zM12 8.25a.75.75 0 01.75.75v3.75a.75.75 0 01-1.5 0V9a.75.75 0 01.75-.75zm0 8.25a.75.75 0 100-1.5.75.75 0 000 1.5z" clip-rule="evenodd"></path></svg>'
        text = "Partially Compliant"
    else:
        color = "text-destructive"
        icon = '<svg class="w-5 h-5 text-destructive mr-2" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75s4.365 9.75 9.75 9.75 9.75-4.365 9.75-9.75S17.385 2.25 12 2.25zm-1.72 6.97a.75.75 0 10-1.06 1.06L10.94 12l-1.72 1.72a.75.75 0 101.06 1.06L12 13.06l1.72 1.72a.75.75 0 101.06-1.06L13.06 12l1.72-1.72a.75.75 0 10-1.06-1.06L12 10.94l-1.72-1.72z" clip-rule="evenodd"></path></svg>'
        text = "Needs Improvement"

    return format_html(
        '<div class="flex items-center">{}<span class="{}">{} ({}%)</span></div>',
        mark_safe(icon),
        color,
        text,
        completion_pct,
    )
