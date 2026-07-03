"""
Health Check Bypass Middleware

Bypasses ALLOWED_HOSTS validation for health check endpoints to allow
Kubernetes/DigitalOcean health probes from pod IPs.

The health check endpoint (/health/) needs to be accessible from internal
pod IPs (10.244.x.x) which use the pod IP directly in the HTTP_HOST header,
not the external domain name.

While Django's ALLOWED_CIDR_NETS should handle this, it silently fails if
the netaddr library isn't available or if there are issues with the middleware
order.

This middleware explicitly bypasses host validation for health check endpoints
as a defense-in-depth measure.
"""

import logging

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http import HttpResponse

logger = logging.getLogger(__name__)


class HealthCheckBypassMiddleware:
    """
    Health check bypass middleware.

    Features:
    - Bypasses ALLOWED_HOSTS validation for health check endpoints
    - Supports pod IP detection (10.244.x.x for DigitalOcean)
    - Configurable via Django settings
    - Defense-in-depth alongside ALLOWED_CIDR_NETS

    This middleware must be placed BEFORE Django's CommonMiddleware
    in the MIDDLEWARE setting.
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # Load configuration from settings
        self.health_check_paths = getattr(
            settings, "HEALTH_CHECK_PATHS", ["/health/", "/healthz", "/health"]
        )
        self.pod_network_prefix = getattr(
            settings, "HEALTH_CHECK_POD_NETWORK_PREFIX", "10.244."
        )
        self.app_domain = getattr(
            settings, "HEALTH_CHECK_APP_DOMAIN", "grey-lit-app-ifa37.ondigitalocean.app"
        )

        logger.debug(
            f"HealthCheckBypassMiddleware initialized: paths={self.health_check_paths}"
        )

    def __call__(self, request):
        """Sync middleware path -- Django wraps this for ASGI automatically."""
        # Pre-process: Setup health check bypass if needed
        self._setup_health_check_bypass(request)

        # Process request through middleware chain
        try:
            response = self.get_response(request)
        except DisallowedHost as e:
            # Handle DisallowedHost exceptions for health checks
            bypass_response = self._handle_disallowed_host(request, e)
            if bypass_response:
                return bypass_response
            raise
        except Exception:
            # Let other exceptions propagate
            raise

        return response

    def _setup_health_check_bypass(self, request):
        """Setup health check bypass if this is a health check request."""
        path = request.path_info

        # Check if this is a health check endpoint
        if path not in self.health_check_paths:
            return

        # Get the host header
        host = request.META.get("HTTP_HOST", "")

        # Check if it's from the pod network (10.244.x.x)
        if not host.startswith(self.pod_network_prefix):
            return

        # Mark request as coming from health check
        request._health_check_bypass = True

        logger.debug(
            f"Health check bypass activated: "
            f"path={path}, host={host}, pod_prefix={self.pod_network_prefix}"
        )

        # Override get_host() to return a valid host
        _original_get_host = request.get_host

        def patched_get_host():
            """Return a valid host from ALLOWED_HOSTS instead of pod IP."""
            return self.app_domain

        request.get_host = patched_get_host

    def _handle_disallowed_host(self, request, exception):
        """Handle DisallowedHost exceptions for health check endpoints."""
        path = request.path_info

        # If this is a health check endpoint, return 200 OK
        if path in self.health_check_paths:
            logger.warning(
                f"DisallowedHost exception caught for health check: "
                f"path={path}, host={request.META.get('HTTP_HOST', 'unknown')}"
            )
            return HttpResponse(
                '{"status": "ok", "note": "Health check bypass active"}',
                content_type="application/json",
                status=200,
            )

        # Not a health check - let exception propagate
        return None
