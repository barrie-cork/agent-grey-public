"""Context processors for core app.

Provides template context variables available to all templates.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest


def posthog_context(request: HttpRequest) -> dict[str, Any]:
    """Provide PostHog configuration to all templates."""
    enabled = getattr(settings, "POSTHOG_ENABLED", False)
    if not enabled:
        return {"posthog_enabled": False}

    context: dict[str, Any] = {
        "posthog_enabled": True,
        "posthog_api_key": getattr(settings, "POSTHOG_API_KEY", ""),
        "posthog_host": getattr(settings, "POSTHOG_HOST", ""),
    }

    # Add user identification for authenticated users
    if hasattr(request, "user") and request.user.is_authenticated:
        context["posthog_user_id"] = str(request.user.pk)

    return context
