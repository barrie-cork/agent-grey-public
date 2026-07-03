"""
Core application Celery tasks.
"""

from apps.core.tasks.dynamic_scheduler import (
    adaptive_session_monitor,
    consolidated_maintenance_task,
    monitoring_statistics,
)
from apps.core.tasks.metric_updates import (
    update_review_metrics_task,
    update_session_metrics_task,
)

__all__ = [
    # Metric updates (Phase 3)
    "update_session_metrics_task",
    "update_review_metrics_task",
    # Adaptive monitoring (Activity-based monitoring PRP)
    "adaptive_session_monitor",
    "consolidated_maintenance_task",
    "monitoring_statistics",
]
