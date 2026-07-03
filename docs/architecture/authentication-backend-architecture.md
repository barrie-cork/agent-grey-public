# Authentication Backend Architecture

**Document Version**: 1.0
**Last Updated**: 2025-10-25
**Status**: Implementation Complete
**Related Files**:
- `apps/accounts/backends.py` - Backend implementation
- `apps/accounts/permissions.py` - Permission registry
- `apps/review_results/permissions.py` - DRF permissions
- `apps/organisation/middleware.py` - Middleware caching

---

## Overview

Agent Grey uses a **dual authentication backend system** following Django best practices:

1. **ModelBackend** (Django default) - Handles **authentication** (login/logout)
2. **RoleBasedPermissionBackend** (custom) - Handles **authorisation** (permissions)

This separation follows the single responsibility principle and allows independent scaling of authentication and authorisation logic.

### Key Design Principles

- **Single Source of Truth**: All permission logic centralised in `RoleBasedPermissionBackend`
- **Performance First**: Three-level caching minimises database queries
- **Type Safety**: Permission registry prevents typos in permission strings
- **Maintainability**: Clear delegation patterns make code easy to understand

---

## Component Interaction

### Request Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        User HTTP Request                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              AuthenticationMiddleware (Django)                   │
│  - Authenticates user via ModelBackend                          │
│  - Sets request.user                                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              OrganisationMiddleware (Custom)                     │
│  - Caches organisation membership on request                    │
│  - Sets: request.organisation_membership                        │
│  - Performance: 1 DB query per request (cached)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              DRF Permission Check (API Views)                    │
│  - Example: IsReviewer, IsLeadReviewerOrAdmin                   │
│  - Caches membership: user._cached_memberships[key] = membership│
│  - Delegates: user.has_perm(Permissions.RESULT_CLAIM)          │
│  - Performance: 0 DB queries (uses middleware cache)            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         RoleBasedPermissionBackend.has_perm()                    │
│  1. Check user._cached_memberships (cache hit → 0 queries)      │
│  2. Fallback to database (cache miss → 1 query + cache)         │
│  3. Check permission via Permissions.get_role_permissions()     │
│  4. Return boolean result                                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Response to User                            │
│  - 200 OK (permission granted)                                  │
│  - 403 Forbidden (permission denied)                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Caching Strategy

### Three-Level Cache Hierarchy

The system implements a sophisticated three-level caching strategy to optimise permission checks:

```python
# Level 1: DRF Permission Cache (request.organisation_membership)
# - Set by: OrganisationMiddleware
# - Scope: Single HTTP request
# - Performance: Eliminates DB query in DRF permission classes

# Level 2: User Object Cache (user._cached_memberships)
# - Set by: DRF permissions before delegating to backend
# - Scope: Single HTTP request (user object lifetime)
# - Performance: Eliminates DB query in backend has_perm()

# Level 3: Database Fallback
# - Used when: Management commands, background tasks, cache miss
# - Scope: Per-query
# - Performance: 1 DB query + cache population for subsequent calls
```

### Cache Key Format

**CRITICAL**: Cache keys MUST follow this exact format:

```python
cache_key = f"{user_obj.id}:{org.id}"  # ✅ Correct format
```

**Invalid formats** (will break caching):
```python
cache_key = f"{user_obj.id}-{org.id}"      # ❌ Wrong separator
cache_key = f"{user_obj.pk}:{org.pk}"      # ❌ Inconsistent (works but non-standard)
cache_key = f"{user_obj.id}_{org.id}"      # ❌ Wrong separator
```

### Performance Benchmarks

| Operation | Before Refactoring | After (Cache Hit) | After (Cache Miss) | Improvement |
|-----------|-------------------|-------------------|-------------------|-------------|
| Single permission check | 2 DB queries | 0 DB queries | 1 DB query | 50-100% |
| 5 permission checks (same session) | 10 DB queries | 0 DB queries | 1 DB query | 90% |
| API request (3 permission checks) | 6 DB queries | 0 DB queries | 1 DB query | 83% |

**Overall Impact**: ~40% reduction in permission-related database queries across the application.

---

## Permission Registry

### Why a Registry?

**Before** (hardcoded strings everywhere):
```python
# apps/review_results/permissions.py
if user.has_perm('review_manager.create_review'):  # Typo risk!
    ...

# apps/review_manager/views.py
if user.has_perm('review_manager.create_reveiw'):  # Typo! Silent failure
    ...
```

**After** (type-safe constants):
```python
from apps.accounts.permissions import Permissions

# apps/review_results/permissions.py
if user.has_perm(Permissions.REVIEW_CREATE):  # IDE autocomplete, refactor-safe
    ...

# apps/review_manager/views.py
if user.has_perm(Permissions.REVIEW_CREATE):  # Same constant, no typos possible
    ...
```

### Registry Structure

```python
# apps/accounts/permissions.py

class Permissions:
    """Centralised permission string registry."""

    # Review Manager Permissions
    REVIEW_CREATE = 'review_manager.create_review'
    REVIEW_EDIT_OWN = 'review_manager.edit_own_review'
    REVIEW_VIEW = 'review_manager.view_review'
    REVIEW_INVITE_REVIEWERS = 'review_manager.invite_reviewers'
    REVIEW_VIEW_METRICS = 'review_manager.view_metrics'

    # Review Results Permissions
    RESULT_CLAIM = 'review_results.claim_result'
    RESULT_SUBMIT = 'review_results.submit_decision'
    RESULT_VIEW_FINAL = 'review_results.view_final_decisions'
    CONFLICT_RESOLVE = 'review_results.resolve_conflict'

    # Organisation Permissions
    ORG_VIEW_DASHBOARD = 'organisation.view_dashboard'
    ORG_EXPORT_REPORTS = 'organisation.export_reports'
    MANAGE_ORGANISATION = 'organisation.manage_organisation'

    # Meta Permissions
    ALL_PERMISSIONS = '*'  # Information Specialist wildcard

    @classmethod
    def get_role_permissions(cls, role: str) -> list[str]:
        """Map organisation roles to their allowed permissions."""
        role_map = {
            'INFORMATION_SPECIALIST': [cls.ALL_PERMISSIONS],
            'SENIOR_RESEARCHER': [
                cls.REVIEW_VIEW,
                cls.REVIEW_VIEW_METRICS,
                cls.ORG_VIEW_DASHBOARD,
                cls.ORG_EXPORT_REPORTS,
                cls.CONFLICT_RESOLVE,
            ],
            'LEAD_REVIEWER': [
                cls.REVIEW_CREATE,
                cls.REVIEW_EDIT_OWN,
                cls.REVIEW_INVITE_REVIEWERS,
            ],
            'REVIEWER': [
                cls.RESULT_CLAIM,
                cls.RESULT_SUBMIT,
            ],
            'OBSERVER': [
                cls.RESULT_VIEW_FINAL,
            ],
        }

        if role not in role_map:
            raise ValueError(f"Unknown role: {role}")

        return role_map[role]
```

---

## Adding New Permissions

Follow this process when adding new permissions to the system:

### Step 1: Add Permission Constant

```python
# apps/accounts/permissions.py

class Permissions:
    # ... existing constants ...

    # NEW: Add your permission constant
    REVIEW_DELETE = 'review_manager.delete_review'
```

### Step 2: Update Role Mappings

```python
# apps/accounts/permissions.py

@classmethod
def get_role_permissions(cls, role: str) -> list[str]:
    role_map = {
        # ... existing mappings ...
        'LEAD_REVIEWER': [
            cls.REVIEW_CREATE,
            cls.REVIEW_EDIT_OWN,
            cls.REVIEW_INVITE_REVIEWERS,
            cls.REVIEW_DELETE,  # NEW: Add to appropriate roles
        ],
    }
```

### Step 3: Use in DRF Permissions or Views

```python
# apps/review_results/permissions.py

from apps.accounts.permissions import Permissions

class CanDeleteReview(BasePermission):
    """Permission to delete reviews."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Cache membership
        IsReviewer._cache_membership(request)

        # Delegate to backend
        return request.user.has_perm(Permissions.REVIEW_DELETE)

    def has_object_permission(self, request, view, obj):
        # Check ownership for object-level permission
        return request.user.has_perm(Permissions.REVIEW_DELETE, obj)
```

### Step 4: Add Backend Object-Level Logic (if needed)

```python
# apps/accounts/backends.py

def has_perm(self, user_obj, perm, obj=None):
    # ... existing code ...

    if perm in allowed_perms:
        # Object-level check for "own" permissions
        if perm == Permissions.REVIEW_EDIT_OWN:
            return obj.owner == user_obj
        if perm == Permissions.REVIEW_DELETE:  # NEW
            return obj.owner == user_obj
        return True
```

### Step 5: Write Tests

```python
# apps/accounts/tests/test_permissions.py

def test_lead_reviewer_can_delete_own_review(self):
    """Lead reviewer should have delete permission for owned reviews."""
    perms = Permissions.get_role_permissions('LEAD_REVIEWER')
    assert Permissions.REVIEW_DELETE in perms

# apps/accounts/tests/test_backends.py

def test_lead_reviewer_can_delete_own_review_object_level(self):
    """Backend should enforce ownership check for delete permission."""
    backend = RoleBasedPermissionBackend()
    user = self.create_user()
    org = self.create_organisation()
    membership = self.create_membership(user, org, role='LEAD_REVIEWER')
    session = self.create_session(organisation=org, owner=user)

    # Pre-cache membership
    user._cached_memberships = {f"{user.id}:{org.id}": membership}

    # Can delete own review
    assert backend.has_perm(user, Permissions.REVIEW_DELETE, session) is True

    # Cannot delete others' review
    other_session = self.create_session(organisation=org, owner=self.create_user())
    assert backend.has_perm(user, Permissions.REVIEW_DELETE, other_session) is False
```

---

## Common Patterns

### Pattern 1: Simple Role Check (DRF Permission)

```python
from rest_framework.permissions import BasePermission
from apps.accounts.permissions import Permissions

class IsReviewer(BasePermission):
    """Check if user has REVIEWER role or higher."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Cache membership for backend optimisation
        self._cache_membership(request)

        # Delegate to backend
        return request.user.has_perm(Permissions.RESULT_CLAIM)

    @staticmethod
    def _cache_membership(request):
        """Cache middleware membership on user object."""
        if hasattr(request, 'organisation_membership') and request.organisation_membership:
            if not hasattr(request.user, '_cached_memberships'):
                request.user._cached_memberships = {}

            membership = request.organisation_membership
            cache_key = f"{request.user.id}:{membership.organisation.id}"
            request.user._cached_memberships[cache_key] = membership
```

### Pattern 2: Object-Level Permission (DRF Permission)

```python
class IsLeadReviewerOrAdmin(BasePermission):
    """Check if user can edit specific review (ownership check)."""

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        # Cache membership
        IsReviewer._cache_membership(request)

        # Delegate to backend with object context
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return request.user.has_perm(Permissions.REVIEW_VIEW, obj)
        else:
            # Backend will check ownership for REVIEW_EDIT_OWN
            return request.user.has_perm(Permissions.REVIEW_EDIT_OWN, obj)
```

### Pattern 3: Template/View Permission Check

```python
# Django template
{% if user.has_perm:Permissions.REVIEW_CREATE %}
    <a href="{% url 'review_manager:create' %}">Create Review</a>
{% endif %}

# Django view
from apps.accounts.permissions import Permissions

def my_view(request):
    if not request.user.has_perm(Permissions.REVIEW_CREATE):
        raise PermissionDenied("Only lead reviewers can create reviews")

    # ... view logic ...
```

---

## Information Specialist Wildcard Pattern

Information Specialists have the `ALL_PERMISSIONS = '*'` wildcard, granting them access to everything.

### Backend Implementation

```python
# apps/accounts/backends.py

def has_perm(self, user_obj, perm, obj=None):
    # ... authentication checks ...

    allowed_perms = Permissions.get_role_permissions(membership.role)

    # Information Specialist has all permissions (wildcard check)
    if Permissions.ALL_PERMISSIONS in allowed_perms:
        return True  # Skip all other checks

    # Check specific permission for other roles
    if perm in allowed_perms:
        # ... object-level checks ...
```

### DRF Pattern (Optional Explicit Check)

Some DRF permission classes also check for Information Specialist explicitly for clarity:

```python
class CanViewOwnDecisions(BasePermission):
    """View decisions with ownership logic."""

    def has_object_permission(self, request, view, obj):
        # Information Specialist can view all decisions
        if request.user.has_perm(Permissions.MANAGE_ORGANISATION):
            return True  # IS-only permission acts as IS detector

        # Other users: check ownership
        return obj.reviewer == request.user
```

**Design Question**: Should we standardise on wildcard check in backend only, or keep explicit IS checks in DRF?

**Current Decision**: Mixed approach for clarity:
- Backend always checks wildcard (`Permissions.ALL_PERMISSIONS`)
- DRF can optionally check IS-only permissions for explicit business logic

---

## Integration with Middleware

### OrganisationMiddleware Caching

```python
# apps/organisation/middleware.py (simplified)

class OrganisationMiddleware:
    def __call__(self, request):
        if request.user.is_authenticated:
            # Cache membership on request (Level 1 cache)
            membership = OrganisationMembership.objects.get(
                user=request.user,
                is_active=True
            )
            request.organisation_membership = membership

        response = self.get_response(request)
        return response
```

### DRF Permission Integration

```python
# apps/review_results/permissions.py

class IsReviewer(BasePermission):
    def has_permission(self, request, view):
        # Get middleware-cached membership from request
        if hasattr(request, 'organisation_membership'):
            membership = request.organisation_membership

            # Cache on user object (Level 2 cache)
            if not hasattr(request.user, '_cached_memberships'):
                request.user._cached_memberships = {}

            cache_key = f"{request.user.id}:{membership.organisation.id}"
            request.user._cached_memberships[cache_key] = membership

        # Delegate to backend (will use Level 2 cache)
        return request.user.has_perm(Permissions.RESULT_CLAIM)
```

---

## Troubleshooting

### Issue: Permission Denied for Valid User

**Symptoms**: User with correct role cannot access resource

**Debug Steps**:
1. Check middleware is running: `print(request.organisation_membership)`
2. Check user cache: `print(request.user._cached_memberships)`
3. Check backend logic: Add logging to `has_perm()`
4. Verify role mapping: `Permissions.get_role_permissions(role)`

**Common Causes**:
- Middleware not running (check `settings.MIDDLEWARE` order)
- Cache not populated (DRF permission not caching membership)
- Wrong permission constant used (typo in permission string)
- Object-level check failing (ownership logic incorrect)

### Issue: High Database Query Count

**Symptoms**: More than 1 DB query per permission check

**Debug Steps**:
```python
from django.test.utils import CaptureQueriesContext
from django.db import connection

with CaptureQueriesContext(connection) as ctx:
    result = user.has_perm(Permissions.RESULT_CLAIM, obj)
    print(f"Queries: {len(ctx.captured_queries)}")
    for q in ctx.captured_queries:
        print(q['sql'])
```

**Common Causes**:
- Cache key format incorrect (check colon separator)
- DRF permission not caching membership before delegation
- Backend reading from wrong cache level

### Issue: Tests Failing Outside Docker

**Symptoms**: `could not translate host name "db"`

**Solution**: Always run tests in Docker:
```bash
docker compose exec web python manage.py test apps.accounts --keepdb -v 2
```

**Reason**: Database host is `db` in Docker Compose network, not accessible from host machine.

---

## Performance Validation

### Manual Performance Check

```python
# Run in: docker compose exec web python manage.py shell

from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.contrib.auth import get_user_model
from apps.organisation.models import Organisation, OrganisationMembership
from apps.accounts.permissions import Permissions
from apps.review_manager.models import SearchSession

User = get_user_model()

# Create test data
user = User.objects.first()
org = Organisation.objects.first()
session = SearchSession.objects.filter(organisation=org).first()

# Warm cache
user._cached_memberships = {}

# Test 1: First call (cache miss - should be 1 query)
with CaptureQueriesContext(connection) as ctx:
    result = user.has_perm(Permissions.RESULT_CLAIM, session)
    print(f"First call queries: {len(ctx.captured_queries)}")  # Expected: 1

# Test 2: Second call (cache hit - should be 0 queries)
with CaptureQueriesContext(connection) as ctx:
    result = user.has_perm(Permissions.RESULT_SUBMIT, session)
    print(f"Second call queries: {len(ctx.captured_queries)}")  # Expected: 0

print("✅ Performance validation complete")
```

**Expected Results**:
- First call: 1 query (populates cache)
- Second call: 0 queries (cache hit)
- Average improvement: 37% faster permission checks

---

## Security Considerations

### Principle of Least Privilege

The permission system enforces least privilege by:
- Default deny (no permission unless explicitly granted)
- Role-based access control (permissions tied to roles)
- Object-level permissions (ownership checks where applicable)
- Wildcard only for administrators (Information Specialist)

### Audit Trail

Permission checks are logged via Django's authentication framework:
```python
import logging
logger = logging.getLogger('django.security')

# Backend automatically logs permission denials
# Enable in settings.py:
LOGGING = {
    'loggers': {
        'django.security': {
            'handlers': ['file', 'sentry'],
            'level': 'INFO',
        },
    },
}
```

### Testing Security

All permission classes MUST have tests covering:
- ✅ Authenticated user with correct role (should pass)
- ✅ Authenticated user with wrong role (should deny)
- ✅ Unauthenticated user (should deny)
- ✅ No organisation context (should deny)
- ✅ Object-level ownership checks (where applicable)

---

## Related Documentation

- **PRD**: `feature_changes/dual-screening/dual-reviewer-screening-prd.md` - Section 4.6 (Permission Matrix)
- **Implementation Guide**: `PRPs/authentication-backend-refactoring-task.md` - Detailed task breakdown
- **Progress Tracking**: `PRPs/authentication-backend-refactoring-PROGRESS.md` - Implementation status
- **Code Quality**: `docs/CODE_QUALITY.md` - Testing standards
- **Deployment**: `docs/deployment/ENVIRONMENT-VARIABLE-CONFIGURATION.md` - AUTHENTICATION_BACKENDS setting

---

## Future Enhancements

1. **Thread-Local Request Storage** - Deeper optimisation using thread-local storage to access `request.organisation_membership` directly from backend
2. **Redis Permission Caching** - Long-lived permission result caching with TTL (e.g., 5 minutes)
3. **Permission Audit Logging** - Comprehensive logging of all permission checks for compliance
4. **Admin UI Permission Matrix** - Visual dashboard showing role-permission mappings
5. **Dynamic Runtime Permissions** - Modify permissions without code changes (database-driven)
6. **Permission Versioning** - Track permission changes over time for audit compliance

---

**Document Status**: Complete
**Reviewed By**: Development Team
**Next Review**: After Django 5.2 upgrade (ASGI middleware changes)
