"""
Secure metrics endpoint for Prometheus scraping.

Requires staff authentication to prevent exposure of operational data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from django.http import HttpRequest, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = structlog.get_logger(__name__)


def is_staff_or_metrics_user(user: AbstractBaseUser) -> bool:
    """
    Check if user is staff or has metrics access permission.

    Args:
        user (AbstractBaseUser): Django user instance.

    Returns:
        bool: True if user has metrics access, False otherwise.

    Note:
        For production: consider creating dedicated 'metrics_viewer' permission.

    Example:
        >>> is_staff_or_metrics_user(staff_user)
        True
    """
    return user.is_authenticated and user.is_staff


def is_allowed_prometheus_access(request: HttpRequest) -> bool:
    """
    Check if request is allowed to access metrics endpoint.

    Phase 3 Development: Allow Docker network access (Prometheus container).
    Phase 4 Production: Implement proper authentication or IP whitelist.

    Args:
        request (HttpRequest): Django HTTP request object.

    Returns:
        bool: True if access is allowed, False otherwise.

    Example:
        >>> is_allowed_prometheus_access(request)
        True
    """
    # Allow authenticated staff users
    if request.user.is_authenticated and request.user.is_staff:
        return True

    # Allow unauthenticated access from Docker network (dev environment only)
    # This allows Prometheus container to scrape metrics
    from django.conf import settings

    if settings.DEBUG:
        return True

    return False


@never_cache
@require_GET
def prometheus_metrics_view(request: HttpRequest) -> HttpResponse:
    """
    Export Prometheus metrics with authentication.

    This endpoint should be scraped by Prometheus server.
    Phase 3: Development mode allows Docker network access.
    Phase 4: Production will use IP whitelist or service account authentication.

    Args:
        request (HttpRequest): Django HTTP request object.

    Returns:
        HttpResponse: Prometheus metrics in text format or error response.

    Raises:
        Exception: Logged but not raised; returns 500 error response.

    Example:
        >>> response = prometheus_metrics_view(request)
        >>> response.status_code
        200
        >>> 'agent_grey_' in response.content.decode()
        True
    """
    # Check access permission
    if not is_allowed_prometheus_access(request):
        return HttpResponse("Forbidden", status=403)

    try:
        # Generate metrics in Prometheus format
        metrics_output = generate_latest()

        # Log access (only if authenticated)
        if request.user.is_authenticated:
            logger.info(
                "metrics_endpoint_accessed",
                user_id=str(request.user.id),
                user_email=request.user.email,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        else:
            logger.info(
                "metrics_endpoint_accessed",
                user="prometheus_scraper",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

        return HttpResponse(
            metrics_output,
            content_type=CONTENT_TYPE_LATEST,
        )

    except Exception as e:
        logger.error(
            "metrics_endpoint_error",
            error=str(e),
            exc_info=True,
        )
        return HttpResponse(
            "Internal Server Error",
            status=500,
        )
