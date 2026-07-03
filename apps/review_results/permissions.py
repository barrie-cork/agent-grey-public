"""
Custom DRF Permissions for Dual Screening APIs.

Integrates with RoleBasedPermissionBackend from apps.accounts.backends
to provide API-level permission enforcement.

Permission Hierarchy (from PRD Section 4.6):
- INFORMATION_SPECIALIST: All permissions (*)
- SENIOR_RESEARCHER: View metrics, act as arbitrator, export reports
- LEAD_REVIEWER: Create reviews, edit own reviews, manage team
- REVIEWER: Claim results, submit decisions
- OBSERVER: View final decisions only

ARCHITECTURE:
All DRF permissions delegate to RoleBasedPermissionBackend via user.has_perm()
to maintain single source of truth for authorisation logic.

OPTIMISATION:
Permissions cache middleware's organisation_membership on user._cached_memberships
before calling has_perm() to minimise database queries.
"""

from rest_framework.permissions import BasePermission

from apps.accounts.permissions import Permissions


def _cache_membership(request):
    """Cache organisation membership on user object for backend optimisation."""
    if hasattr(request, "organisation_membership") and request.organisation_membership:
        if not hasattr(request.user, "_cached_memberships"):
            request.user._cached_memberships = {}

        membership = request.organisation_membership
        cache_key = f"{request.user.id}:{membership.organisation.id}"
        request.user._cached_memberships[cache_key] = membership


class IsInfoSpecialistOrSeniorResearcher(BasePermission):
    """
    Permission for organisation-level dashboards and reports.

    Allows: INFORMATION_SPECIALIST, SENIOR_RESEARCHER.
    Delegates to RoleBasedPermissionBackend for authorisation.
    """

    message = "Only information specialists or senior researchers can access organisation dashboards."

    def has_permission(self, request, view):
        """Check if user has senior role."""
        if not request.user or not request.user.is_authenticated:
            return False

        _cache_membership(request)

        return request.user.has_perm(
            Permissions.ORG_VIEW_DASHBOARD, request.organisation
        )

    def has_object_permission(self, request, view, obj):
        """
        Object-level check for organisation access.

        User must have active membership in the organisation.
        """
        if not request.user or not request.user.is_authenticated:
            return False

        _cache_membership(request)

        return request.user.has_perm(Permissions.ORG_VIEW_DASHBOARD, obj)


class IsInfoSpecialistOnly(BasePermission):
    """
    Permission for Information Specialist only actions.

    Allows: User invitations, organisation management.
    Delegates to RoleBasedPermissionBackend for authorisation.
    """

    message = "Only information specialists can perform this action."

    def has_permission(self, request, view):
        """Check if user is information specialist."""
        if not request.user or not request.user.is_authenticated:
            return False

        _cache_membership(request)

        return request.user.has_perm(
            Permissions.MANAGE_ORGANISATION, request.organisation
        )

    def has_object_permission(self, request, view, obj):
        """Object-level check for organisation management."""
        if not request.user or not request.user.is_authenticated:
            return False

        _cache_membership(request)

        return request.user.has_perm(Permissions.MANAGE_ORGANISATION, obj)
