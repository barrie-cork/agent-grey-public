"""
Custom authentication backends for Agent Grey.

Implements:
- RoleBasedPermissionBackend: Organisation-based role checking

PERFORMANCE NOTES:
- Uses request-cached membership when available (via user._cached_memberships)
- Falls back to database query for management commands
- Permission definitions centralised in apps.accounts.permissions
- Three-level caching: DRF permissions → user cache → database fallback
- Cache hit: 0 database queries, Cache miss: 1 database query (then cached)

INTEGRATION:
- OrganisationMiddleware sets request.organisation_membership on each request
- DRF permissions cache membership on user._cached_memberships before delegation
- Backend reads from user._cached_memberships cache before querying database
- Single source of truth: All permission logic delegates through has_perm()

MAINTENANCE:
- All permission strings defined in apps.accounts.permissions.Permissions class
- Role-permission mappings in Permissions.get_role_permissions() method
- Update permission registry when adding new permissions to maintain consistency
- Never hardcode permission strings - always use Permissions.CONSTANT_NAME

PATTERN EXAMPLE:
    # ❌ Don't do this (hardcoded string)
    if user.has_perm('review_manager.create_review'):
        ...

    # ✅ Do this (registry constant)
    from apps.accounts.permissions import Permissions
    if user.has_perm(Permissions.REVIEW_CREATE):
        ...

ARCHITECTURE:
See docs/architecture/authentication-backend-architecture.md for complete
request flow diagrams, caching strategies, and integration patterns.
"""

from apps.accounts.permissions import Permissions
from apps.organisation.models import Organisation, OrganisationMembership


class RoleBasedPermissionBackend:
    """
    Custom permission backend for organisation-based role checking.

    CRITICAL: This backend supplements Django's default backend.
    Configure in settings.py:
        AUTHENTICATION_BACKENDS = [
            'django.contrib.auth.backends.ModelBackend',  # Keep default
            'apps.accounts.backends.RoleBasedPermissionBackend',  # Add custom
        ]

    Permission Mapping (from PRD Section 4.6):
    - INFORMATION_SPECIALIST: All permissions (*)
    - SENIOR_RESEARCHER: View all reviews, view dashboard, export reports
    - LEAD_REVIEWER: Create reviews, edit own reviews, invite reviewers
    - REVIEWER: Claim results, submit decisions
    - OBSERVER: View final decisions
    """

    def has_perm(self, user_obj, perm, obj=None):
        """Check if user has permission based on organisation role."""
        if not user_obj or not user_obj.is_authenticated:
            return False

        # Extract organisation from object
        org = None
        if obj and hasattr(obj, "organisation"):
            org = obj.organisation
        elif obj and isinstance(obj, Organisation):
            org = obj

        # Fallback: use contextvar set by OrganisationMiddleware
        if not org:
            from apps.organisation.context import get_current_org

            org = get_current_org()

        if not org:
            return False

        # OPTIMISATION: Try to use cached membership first
        membership = self._get_membership_cached(user_obj, org)

        if not membership:
            return False

        # Use centralised permission registry
        allowed_perms = Permissions.get_role_permissions(membership.role)

        # Information Specialist has all permissions
        if Permissions.ALL_PERMISSIONS in allowed_perms:
            return True

        # Check specific permission
        if perm in allowed_perms:
            # Object-level check for "own" permissions
            if perm == Permissions.REVIEW_EDIT_OWN:
                return obj is not None and obj.owner == user_obj
            return True

        return False

    def _get_membership_cached(self, user_obj, org):
        """
        Get OrganisationMembership with caching strategy.

        PATTERN: Check three sources in order:
        1. user._cached_memberships (set by DRF permissions)
        2. Database query (fallback for management commands)
        3. Cache result for subsequent calls in same request

        Args:
            user_obj: User instance
            org: Organisation instance

        Returns:
            OrganisationMembership or None

        Performance:
            First call: 1 DB query + cache population
            Subsequent calls: 0 DB queries (cache hit)
        """
        # Try request-level cache first (set by DRF permissions)
        if hasattr(user_obj, "_cached_memberships"):
            cache_key = f"{user_obj.id}:{org.id}"
            if cache_key in user_obj._cached_memberships:
                return user_obj._cached_memberships[cache_key]

        # Fallback to database query (safe for management commands)
        try:
            membership = OrganisationMembership.objects.get(
                user=user_obj, organisation=org, is_active=True
            )

            # Cache for subsequent calls in same request
            if not hasattr(user_obj, "_cached_memberships"):
                user_obj._cached_memberships = {}
            cache_key = f"{user_obj.id}:{org.id}"
            user_obj._cached_memberships[cache_key] = membership

            return membership
        except OrganisationMembership.DoesNotExist:
            return None

    def has_module_perms(self, user_obj, app_label):
        """
        Check if user has any permissions in app.

        GOTCHA: Required by Django auth backend contract.
        Return True if user has any permissions in app.

        Args:
            user_obj: User instance
            app_label: App label (e.g., 'review_manager')

        Returns:
            bool: True if user has module-level access
        """
        if not user_obj or not user_obj.is_authenticated:
            return False

        # Information Specialists have access to all apps
        info_specialist = OrganisationMembership.objects.filter(
            user=user_obj, role="INFORMATION_SPECIALIST", is_active=True
        ).exists()

        if info_specialist:
            return True

        # Other roles have module-level access based on app
        allowed_apps = {
            "SENIOR_RESEARCHER": ["review_manager", "organisation"],
            "LEAD_REVIEWER": ["review_manager", "review_results"],
            "REVIEWER": ["review_results"],
            "OBSERVER": ["review_results"],
        }

        membership = OrganisationMembership.objects.filter(
            user=user_obj, is_active=True
        ).first()

        if membership:
            return app_label in allowed_apps.get(membership.role, [])

        return False

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        This backend does not handle authentication.

        Django's ModelBackend handles user authentication.
        This backend only handles authorization (permissions).

        Returns:
            None: Indicates this backend does not handle authentication
        """
        return None

    def get_user(self, user_id):
        """
        This backend does not handle user retrieval.

        Django's ModelBackend handles user retrieval.

        Returns:
            None: Indicates this backend does not handle user retrieval
        """
        return None
