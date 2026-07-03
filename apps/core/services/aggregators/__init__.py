"""
Aggregator services for monitoring and dashboard data collection.

These services extract large view methods into focused, testable, and cacheable
service classes following the BaseService pattern.
"""

from .connection_metrics import ConnectionMetricsAggregator
from .system_health import SystemHealthAggregator
from .workflow_stats import WorkflowStatsAggregator

__all__ = [
    "WorkflowStatsAggregator",
    "ConnectionMetricsAggregator",
    "SystemHealthAggregator",
]
