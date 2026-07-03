"""
Transition metrics collection for workflow state changes.

REFACTORED: This module has been reorganized into submodules for better maintainability.

This file now serves as a backward-compatibility layer, re-exporting from the new module structure:
- apps.core.monitoring.metrics.collectors: Core metric collection
- apps.core.monitoring.metrics.aggregators: Metric aggregation and statistics
- apps.core.monitoring.metrics.exporters: Prometheus exporters (placeholder)

New code should import directly from the submodules, but existing code can continue
to import from this module without changes.

DEPRECATION NOTICE (Phase 3-5 Migration Plan):
==============================================
This module uses cache-based metrics which will be DEPRECATED and REMOVED.

Timeline:
1. Phase 3 (CURRENT): Dual tracking (cache + Prometheus) for comparison ✅
2. Phase 4: Validate Prometheus metrics accuracy over 2 weeks
3. Phase 4: Migrate all dashboards to Prometheus queries (1 week)
4. Phase 5: REMOVE cache-based metrics, keep only Prometheus

Recommended Migration Path:
- Replace get_transition_stats() calls with Prometheus queries
- Use PromQL for aggregations instead of cache counters
- Update monitoring dashboards to use Grafana
- Remove TransitionMetrics class usage from application code

For new code:
- Use apps.core.metrics.session_metrics.record_session_transition()
- Do NOT use this TransitionMetrics class
"""

# Re-export all public APIs from the refactored modules
from apps.core.monitoring.metrics.aggregators import (  # noqa: F401
    count_stuck_sessions,
    get_cached_stats,
    get_performance_summary,
    get_transition_stats,
    send_to_monitoring_service,
)
from apps.core.monitoring.metrics.collectors import (  # noqa: F401
    TransitionMetrics,
)

__all__ = [
    "TransitionMetrics",
    "get_transition_stats",
    "get_cached_stats",
    "count_stuck_sessions",
    "get_performance_summary",
    "send_to_monitoring_service",
]
