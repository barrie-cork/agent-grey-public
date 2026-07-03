"""
Metric collection for workflow transitions.

This module provides the core metric collection functionality for tracking
workflow state transitions, performance, and success rates.

DEPRECATION NOTICE (Phase 3-5 Migration Plan):
==============================================
This module uses cache-based metrics which will be DEPRECATED and REMOVED.

Timeline:
1. Phase 3 (CURRENT): Dual tracking (cache + Prometheus) for comparison ✅
2. Phase 4: Validate Prometheus metrics accuracy over 2 weeks
3. Phase 4: Migrate all dashboards to Prometheus queries (1 week)
4. Phase 5: REMOVE cache-based metrics, keep only Prometheus

Recommended Migration Path:
- Replace TransitionMetrics calls with Prometheus queries
- Use PromQL for aggregations instead of cache counters
- Update monitoring dashboards to use Grafana
- Remove TransitionMetrics class usage from application code

For new code:
- Use apps.core.metrics.session_metrics.record_session_transition()
- Do NOT use this TransitionMetrics class
"""

import logging
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# Prometheus metrics integration (Phase 3)
try:
    from apps.core.metrics.session_metrics import (
        record_session_transition as record_prometheus_transition,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("Prometheus metrics not available - using cache-based metrics only")


class TransitionMetrics:
    """
    Collect and report workflow transition metrics.

    Features:
    - Transition counting and timing
    - Success rate calculation
    - Failure tracking and categorization
    - Performance metrics aggregation
    - Dual tracking with Prometheus (Phase 3)

    DEPRECATION WARNING: This class will be removed in Phase 5.
    Use apps.core.metrics.session_metrics instead.
    """

    def __init__(self):
        """Initialize metrics collector."""
        self.metric_prefix = "workflow.transition"
        self.cache_ttl = 3600  # 1 hour
        self.max_recent_failures = 100

    def record_transition(
        self,
        session_id: str,
        from_state: str,
        to_state: str,
        duration_ms: float,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a state transition event.

        DEPRECATION WARNING: This method will be removed in Phase 5.
        Use apps.core.metrics.session_metrics.record_session_transition() instead.

        Migration Example:
            # OLD (cache-based - to be removed)
            from apps.core.monitoring.metrics import TransitionMetrics
            metrics = TransitionMetrics()
            metrics.record_transition(session_id, 'draft', 'executing', 1500.0)

            # NEW (Prometheus-based - use this)
            from apps.core.metrics.session_metrics import record_session_transition
            record_session_transition(session, 'draft', 'executing',
                                    success=True, duration_seconds=1.5)

        Args:
            session_id: The session UUID
            from_state: Original state
            to_state: Target state
            duration_ms: Transition duration in milliseconds
            success: Whether transition succeeded
            metadata: Additional context data
        """
        try:
            metric_key = f"{self.metric_prefix}.{from_state}_to_{to_state}"

            # EXISTING: Cache-based metrics (keep for backward compatibility)
            # Increment counter
            self.increment_counter(f"{metric_key}.count")

            if success:
                self.increment_counter(f"{metric_key}.success")
                # Record timing for successful transitions
                self.record_timing(f"{metric_key}.duration", duration_ms)
            else:
                self.increment_counter(f"{metric_key}.failures")

            # Update success rate
            self._update_success_rate(from_state, to_state)

            # Track performance categories
            if duration_ms > 1000:  # Slow transitions (>1 second)
                self.increment_counter(f"{metric_key}.slow")
            elif duration_ms > 5000:  # Very slow transitions (>5 seconds)
                self.increment_counter(f"{metric_key}.very_slow")

            # Store transition details for analysis
            self._store_transition_detail(
                session_id, from_state, to_state, duration_ms, success, metadata
            )

            # Update aggregate metrics
            self._update_aggregates(from_state, to_state, duration_ms, success)

            # NEW: Prometheus metrics (parallel tracking - Phase 3)
            if PROMETHEUS_AVAILABLE:
                try:
                    from apps.review_manager.models import SearchSession

                    session = SearchSession.objects.get(id=session_id)
                    duration_seconds = duration_ms / 1000.0  # Convert to seconds
                    record_prometheus_transition(
                        session=session,
                        from_state=from_state,
                        to_state=to_state,
                        success=success,
                        duration_seconds=duration_seconds,
                    )
                except SearchSession.DoesNotExist:
                    logger.warning(
                        f"Session {session_id} not found for Prometheus metrics"
                    )
                except Exception as prom_error:
                    # Don't fail on Prometheus errors - cache-based metrics still work
                    logger.warning(
                        f"prometheus_transition_recording_failed: {str(prom_error)}",
                        extra={"from_state": from_state, "to_state": to_state},
                    )

        except Exception as e:
            logger.error(f"Failed to record transition metric: {str(e)}")

    def record_transition_failure(
        self,
        session_id: str,
        from_state: str,
        to_state: str,
        error: str,
        error_type: Optional[str] = None,
    ) -> None:
        """
        Record a failed transition attempt.

        Args:
            session_id: The session UUID
            from_state: Original state
            to_state: Attempted target state
            error: Error message
            error_type: Type of error (e.g., ValidationError)
        """
        try:
            metric_key = f"{self.metric_prefix}.{from_state}_to_{to_state}.failures"

            self.increment_counter(metric_key)

            # Categorize failure
            if error_type:
                self.increment_counter(f"{metric_key}.{error_type}")

            # Store recent failures for debugging
            failure_data = {
                "session_id": session_id,
                "from_state": from_state,
                "to_state": to_state,
                "error": error,
                "error_type": error_type or "Unknown",
                "timestamp": timezone.now().isoformat(),
            }

            self._store_recent_failure(failure_data)

        except Exception as e:
            logger.error(f"Failed to record transition failure: {str(e)}")

    def increment_counter(self, key: str) -> None:
        """
        Increment a metric counter.

        Args:
            key: The metric key
        """
        try:
            full_key = f"metrics:{key}"
            current = cache.get(full_key, 0)
            cache.set(full_key, current + 1, self.cache_ttl)
        except Exception as e:
            logger.warning(f"Failed to increment counter {key}: {str(e)}")

    def record_timing(self, key: str, value: float) -> None:
        """
        Record a timing metric.

        Args:
            key: The metric key
            value: The timing value in milliseconds
        """
        try:
            # Store in a list for percentile calculations
            timing_key = f"metrics:timings:{key}"
            timings = cache.get(timing_key, [])
            timings.append(value)

            # Keep last 1000 timings
            if len(timings) > 1000:
                timings = timings[-1000:]

            cache.set(timing_key, timings, self.cache_ttl)

            # Update running average
            avg_key = f"metrics:avg:{key}"
            count_key = f"metrics:count:{key}"

            current_avg = cache.get(avg_key, 0)
            current_count = cache.get(count_key, 0)

            new_count = current_count + 1
            new_avg = ((current_avg * current_count) + value) / new_count

            cache.set(avg_key, new_avg, self.cache_ttl)
            cache.set(count_key, new_count, self.cache_ttl)

        except Exception as e:
            logger.warning(f"Failed to record timing {key}: {str(e)}")

    def _update_success_rate(self, from_state: str, to_state: str) -> None:
        """
        Update success rate for a transition.

        Args:
            from_state: Original state
            to_state: Target state
        """
        try:
            metric_key = f"{self.metric_prefix}.{from_state}_to_{to_state}"

            total = cache.get(f"metrics:{metric_key}.count", 0)
            success = cache.get(f"metrics:{metric_key}.success", 0)

            if total > 0:
                success_rate = (success / total) * 100
                cache.set(
                    f"metrics:{metric_key}.success_rate", success_rate, self.cache_ttl
                )

        except Exception as e:
            logger.warning(f"Failed to update success rate: {str(e)}")

    def _store_transition_detail(
        self,
        session_id: str,
        from_state: str,
        to_state: str,
        duration_ms: float,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Store detailed transition information.

        Args:
            session_id: Session UUID
            from_state: Original state
            to_state: Target state
            duration_ms: Duration in milliseconds
            success: Whether successful
            metadata: Additional data
        """
        try:
            detail_key = "metrics:transitions:details"
            details = cache.get(detail_key, [])

            detail = {
                "session_id": session_id,
                "from_state": from_state,
                "to_state": to_state,
                "duration_ms": duration_ms,
                "success": success,
                "timestamp": timezone.now().isoformat(),
                "metadata": metadata or {},
            }

            details.append(detail)

            # Keep last 500 transitions
            if len(details) > 500:
                details = details[-500:]

            cache.set(detail_key, details, self.cache_ttl)

        except Exception as e:
            logger.warning(f"Failed to store transition detail: {str(e)}")

    def _store_recent_failure(self, failure_data: dict) -> None:
        """
        Store recent failure for debugging.

        Args:
            failure_data: Failure information
        """
        try:
            failures_key = "metrics:transitions:recent_failures"
            failures = cache.get(failures_key, [])

            failures.append(failure_data)

            # Keep limited history
            if len(failures) > self.max_recent_failures:
                failures = failures[-self.max_recent_failures :]

            cache.set(failures_key, failures, self.cache_ttl)

        except Exception as e:
            logger.warning(f"Failed to store recent failure: {str(e)}")

    def _update_aggregates(
        self, from_state: str, to_state: str, duration_ms: float, success: bool
    ) -> None:
        """
        Update aggregate statistics.

        Args:
            from_state: Original state
            to_state: Target state
            duration_ms: Duration in milliseconds
            success: Whether successful
        """
        try:
            agg_key = f"metrics:aggregates:{from_state}_to_{to_state}"
            aggregates = cache.get(
                agg_key,
                {
                    "count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "total_duration": 0,
                    "max_duration": 0,
                    "min_duration": float("inf"),
                    "slow_count": 0,
                    "very_slow_count": 0,
                },
            )

            aggregates["count"] += 1

            if success:
                aggregates["success_count"] += 1
                aggregates["total_duration"] += duration_ms
                aggregates["max_duration"] = max(
                    aggregates["max_duration"], duration_ms
                )
                aggregates["min_duration"] = min(
                    aggregates["min_duration"], duration_ms
                )

                if duration_ms > 1000:
                    aggregates["slow_count"] += 1
                if duration_ms > 5000:
                    aggregates["very_slow_count"] += 1
            else:
                aggregates["failure_count"] += 1

            # Calculate rates
            if aggregates["count"] > 0:
                aggregates["success_rate"] = (
                    aggregates["success_count"] / aggregates["count"]
                ) * 100
                aggregates["failure_rate"] = (
                    aggregates["failure_count"] / aggregates["count"]
                ) * 100

                if aggregates["success_count"] > 0:
                    aggregates["avg_duration"] = (
                        aggregates["total_duration"] / aggregates["success_count"]
                    )

            cache.set(agg_key, aggregates, self.cache_ttl)

        except Exception as e:
            logger.warning(f"Failed to update aggregates: {str(e)}")

    def get_transition_stats(self, time_window_hours: int = 1) -> Dict[str, Any]:
        """
        Get transition statistics for a time window.

        Args:
            time_window_hours: Number of hours to look back

        Returns:
            Dictionary with transition statistics
        """
        try:
            recent_failures = cache.get("metrics:recent_failures", [])
            return {
                "total_transitions": cache.get("metrics:total_transitions", 0),
                "stuck_sessions": cache.get("metrics:stuck_sessions", 0),
                "recent_failures": recent_failures[: self.max_recent_failures],
                "time_window_hours": time_window_hours,
            }
        except Exception as e:
            logger.warning(f"Failed to get transition stats: {str(e)}")
            return {
                "total_transitions": 0,
                "stuck_sessions": 0,
                "recent_failures": [],
                "time_window_hours": time_window_hours,
            }
