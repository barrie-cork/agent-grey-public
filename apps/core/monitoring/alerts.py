"""
Alerting system for workflow issues.

REFACTORED: This module has been reorganized into submodules for better maintainability.

This file now serves as a backward-compatibility layer, re-exporting from the new module structure:
- apps.core.monitoring.alerts.rules: Alert rule definitions
- apps.core.monitoring.alerts.notifications: Notification delivery
- apps.core.monitoring.alerts.handlers: Main alert manager

New code should import directly from the submodules, but existing code can continue
to import from this module without changes.
"""

# Re-export all public APIs from the refactored modules
from apps.core.monitoring.alerts.handlers import WorkflowAlertManager  # noqa: F401
from apps.core.monitoring.alerts.notifications import (  # noqa: F401
    AlertNotificationService,
)
from apps.core.monitoring.alerts.rules import AlertRules  # noqa: F401

__all__ = [
    "WorkflowAlertManager",
    "AlertRules",
    "AlertNotificationService",
]
