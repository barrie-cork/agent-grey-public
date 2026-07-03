from django import template

register = template.Library()


@register.filter
def status_color(status):
    """Return semantic color variant for session status badge."""
    status_colors = {
        "draft": "secondary",
        "defining_search": "info",
        "ready_to_execute": "primary",
        "executing": "warning",
        "processing_results": "warning",
        "ready_for_review": "success",
        "under_review": "success",
        "completed": "dark",
        "archived": "secondary",
    }
    return status_colors.get(status, "secondary")
