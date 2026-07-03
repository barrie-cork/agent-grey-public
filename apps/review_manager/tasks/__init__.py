"""
Review Manager tasks package.

This module maintains backward compatibility by re-exporting all tasks
from their organized modules.
"""

# Import from cache module
from .cache import (
    invalidate_stale_caches,
    warm_active_session_caches,
    warm_session_cache,
    warm_user_dashboard_cache,
)

# Import from maintenance module
from .maintenance import (  # check_stuck_sessions removed - functionality merged into recover_stuck_sessions
    cleanup_old_sessions,
    comprehensive_recovery,
    recover_stuck_sessions,
    update_session_statistics,
)

# Import from monitoring module
from .monitoring import diagnose_session_health, monitor_workflow_health

# Define all exported tasks
__all__ = [
    # Monitoring tasks
    "monitor_workflow_health",
    "diagnose_session_health",
    # Maintenance tasks
    "cleanup_old_sessions",
    "comprehensive_recovery",
    "update_session_statistics",
    "recover_stuck_sessions",
    # check_stuck_sessions removed - functionality merged into recover_stuck_sessions
    # Cache tasks
    "warm_session_cache",
    "warm_active_session_caches",
    "warm_user_dashboard_cache",
    "invalidate_stale_caches",
]
