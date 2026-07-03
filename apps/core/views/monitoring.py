"""
Real-time workflow monitoring dashboard views.

REFACTORED: This module has been reorganized into submodules for better maintainability.

This file now serves as a backward-compatibility layer, re-exporting from the new module structure:
- apps.core.views.monitoring.dashboards: Dashboard views
- apps.core.views.monitoring.health: Health check views
- apps.core.views.monitoring.metrics_api: Connection metrics API

New code should import directly from the submodules, but existing code can continue
to import from this module without changes.
"""

# Re-export all public APIs from the refactored modules
from apps.core.views.monitoring.dashboards import (  # noqa: F401
    WorkflowMonitoringAPI,
    WorkflowMonitoringDashboard,
)
from apps.core.views.monitoring.health import HealthCheckView  # noqa: F401
from apps.core.views.monitoring.metrics_api import ConnectionMonitoringAPI  # noqa: F401

__all__ = [
    "ConnectionMonitoringAPI",
    "HealthCheckView",
    "WorkflowMonitoringAPI",
    "WorkflowMonitoringDashboard",
]
