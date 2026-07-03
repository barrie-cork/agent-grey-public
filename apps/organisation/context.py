"""Thread-safe, async-safe organisation context using contextvars.

Provides implicit organisation scoping for permission checks that lack
an explicit object reference. Set by OrganisationMiddleware on each
request; read by RoleBasedPermissionBackend as a fallback when has_perm()
is called without obj.

IMPORTANT: This is a fallback mechanism. Callers should still pass obj
to has_perm() whenever possible for explicit scoping.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from apps.organisation.models import Organisation

_current_org: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    "current_org", default=None
)


def set_current_org(org: Optional[Organisation]) -> contextvars.Token:
    """Set the current organisation for this context (request/task)."""
    return _current_org.set(org)


def get_current_org() -> Optional[Organisation]:
    """Get the current organisation for this context, or None."""
    return _current_org.get()


def clear_current_org() -> None:
    """Reset the current organisation context to None."""
    _current_org.set(None)
