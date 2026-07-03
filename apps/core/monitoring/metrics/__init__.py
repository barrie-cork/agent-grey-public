"""
Metrics collection and aggregation for workflow monitoring.

This module provides backward-compatible imports for the refactored metrics system.
All metrics functionality has been organized into submodules for better maintainability.

Submodules:
- collectors: Core metric collection and transition tracking
- aggregators: Metric aggregation and statistics generation
- exporters: Prometheus metrics exporters (placeholder)

DEPRECATION NOTICE:
The cache-based metrics in this module will be deprecated in Phase 5.
Please use apps.core.metrics.session_metrics for new code.
"""

from .aggregators import (
    count_stuck_sessions,
    get_cached_stats,
    get_performance_summary,
    get_transition_stats,
    send_to_monitoring_service,
)
from .collectors import TransitionMetrics

__all__ = [
    "TransitionMetrics",
    "get_transition_stats",
    "get_cached_stats",
    "count_stuck_sessions",
    "get_performance_summary",
    "send_to_monitoring_service",
]
