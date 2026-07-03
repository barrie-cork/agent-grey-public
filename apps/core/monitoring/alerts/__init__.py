"""
Alert system for workflow monitoring.

This module provides backward-compatible imports for the refactored alert system.
All alert functionality has been organized into submodules for better maintainability.

Submodules:
- rules: Alert rule definitions and threshold management
- notifications: Multi-channel notification delivery
- handlers: Main alert manager coordinating rules and notifications
"""

from .handlers import WorkflowAlertManager
from .notifications import AlertNotificationService
from .rules import AlertRules

__all__ = [
    "WorkflowAlertManager",
    "AlertRules",
    "AlertNotificationService",
]
