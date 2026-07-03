"""
Custom Prometheus metrics for Agent Grey business operations.

This module provides domain-specific metrics for monitoring:
- Session workflow state transitions
- Search execution performance
- Result processing efficiency
- Review decision velocity

All metrics use the 'agent_grey_' prefix and follow Prometheus naming conventions.
"""

from apps.core.metrics.registry import (  # Session metrics; Search metrics; Processing metrics; Review metrics
    deduplication_rate,
    processing_duration_seconds,
    results_processed_total,
    review_decisions_total,
    review_velocity_per_hour,
    search_api_errors_total,
    search_duration_seconds,
    search_queries_total,
    search_results_count,
    session_state_duration_seconds,
    session_state_gauge,
    session_transitions_total,
)

__all__ = [
    # Session metrics
    "session_state_gauge",
    "session_transitions_total",
    "session_state_duration_seconds",
    # Search metrics
    "search_queries_total",
    "search_duration_seconds",
    "search_results_count",
    "search_api_errors_total",
    # Processing metrics
    "processing_duration_seconds",
    "deduplication_rate",
    "results_processed_total",
    # Review metrics
    "review_decisions_total",
    "review_velocity_per_hour",
]
