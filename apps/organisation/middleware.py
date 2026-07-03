"""
Organisation middleware for request context injection.

Attaches organisation to request based on user membership.
"""

import logging

from apps.organisation.context import clear_current_org, set_current_org
from apps.organisation.models import OrganisationMembership

logger = logging.getLogger(__name__)


class OrganisationMiddleware:
    """
    Attach organisation to request based on user membership.

    CRITICAL: Must come AFTER AuthenticationMiddleware in settings.py
    PATTERN: Always set request.organisation (even if None)
    GOTCHA: Multi-org users default to most recent membership

    AUTHENTICATION SKIP: Skips execution for authentication paths to prevent
    database queries during authentication transaction (GitHub Issue #32).
    """

    # Authentication paths where middleware should skip execution
    # Prevents database queries during authentication transaction (GitHub Issue #32)
    SKIP_PATHS = [
        "/accounts/login/",
        "/accounts/logout/",
        "/accounts/signup/",
        "/accounts/password-reset/",
        "/accounts/password-reset/done/",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Sync middleware path -- Django wraps this for ASGI automatically."""
        self._setup_organisation(request)
        response = self.get_response(request)
        return response

    def _setup_organisation(self, request):
        """
        Extract organisation from user membership and attach to request.

        CRITICAL: Skip execution for authentication views to prevent database
        queries from interfering with the authentication transaction.
        See: GitHub Issue #32 (E2E authentication rejection)
        """
        # Always set request.organisation (even if None) to avoid AttributeError
        request.organisation = None
        # Reset contextvar at the start of each request
        clear_current_org()

        # Skip middleware for authentication views to prevent auth interference
        if request.path in self.SKIP_PATHS or request.path.startswith(
            "/accounts/reset/"
        ):
            logger.debug("OrganisationMiddleware: skipping auth path %s", request.path)
            return

        if hasattr(request, "user") and request.user.is_authenticated:
            # Get user's default organisation (most recent membership)
            # Using select_related for performance
            membership = (
                OrganisationMembership.objects.filter(user=request.user, is_active=True)
                .select_related("organisation")
                .order_by("-joined_at")
                .first()
            )

            if membership:
                request.organisation = membership.organisation
                # Also attach membership for role checking
                request.organisation_membership = membership
                # Set contextvar for permission backend fallback
                set_current_org(membership.organisation)
