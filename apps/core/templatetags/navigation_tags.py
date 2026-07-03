from django import template
from django.conf import settings

register = template.Library()


@register.filter
def split(value, separator=","):
    """Split a string by separator and return a list."""
    return str(value).split(separator)


@register.simple_tag(takes_context=True)
def should_show_header(context):
    """Determine if header should be shown based on request and user."""
    request = context["request"]
    user = context.get("user")

    # Get navigation config from settings
    nav_config = getattr(settings, "NAVIGATION_CONFIG", {})

    # Hide on auth pages
    auth_pages = nav_config.get(
        "HIDE_HEADER_URLS",
        [
            "login",
            "signup",
            "password_reset",
            "password_reset_done",
            "password_reset_confirm",
            "password_reset_complete",
        ],
    )

    if hasattr(request, "resolver_match") and request.resolver_match:
        if request.resolver_match.url_name in auth_pages:
            return False

    # Hide for staff users (unless superuser)
    if user and user.is_authenticated:
        if user.is_staff and not user.is_superuser:
            return nav_config.get("SHOW_HEADER_FOR_STAFF", False)

    return True


@register.simple_tag
def user_can_access_dashboard(user):
    """Check if user can access admin dashboard."""
    if not user or not user.is_authenticated:
        return False

    # Superusers always have access
    if user.is_superuser:
        return True

    # Check if user is in admin groups
    nav_config = getattr(settings, "NAVIGATION_CONFIG", {})
    admin_groups = nav_config.get("ADMIN_GROUPS", ["Administrators"])

    return user.groups.filter(name__in=admin_groups).exists()
