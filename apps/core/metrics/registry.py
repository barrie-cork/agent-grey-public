"""
Central registry for all Agent Grey custom Prometheus metrics.

Metrics are defined here to avoid duplication and ensure
consistent naming/labelling across the application.
"""

from prometheus_client import Counter, Gauge, Histogram

# =============================================================================
# SESSION WORKFLOW METRICS
# =============================================================================

session_state_gauge = Gauge(
    "agent_grey_session_state",
    "Current number of sessions in each state",
    ["state"],
)

session_transitions_total = Counter(
    "agent_grey_session_transitions_total",
    "Total number of session state transitions",
    ["from_state", "to_state", "success"],
)

session_state_duration_seconds = Histogram(
    "agent_grey_session_state_duration_seconds",
    "Time spent in each session state",
    ["state"],
    buckets=[
        60,
        300,
        600,
        1800,
        3600,
        7200,
        14400,
        28800,
        86400,
        float("inf"),
    ],  # 1min to 1day
)

# =============================================================================
# SEARCH EXECUTION METRICS
# =============================================================================

search_queries_total = Counter(
    "agent_grey_search_queries_total",
    "Total number of search queries executed",
    ["status", "api_provider"],
)

search_duration_seconds = Histogram(
    "agent_grey_search_duration_seconds",
    "Search query execution time",
    ["api_provider"],
    buckets=[
        0.5,
        1.0,
        2.0,
        5.0,
        10.0,
        30.0,
        60.0,
        float("inf"),
    ],  # API calls: 0.5s to 60s
)

search_results_count = Histogram(
    "agent_grey_search_results_count",
    "Number of results returned per search query",
    ["api_provider"],
    buckets=[0, 10, 50, 100, 500, 1000, float("inf")],
)

search_api_errors_total = Counter(
    "agent_grey_search_api_errors_total",
    "Total number of search API errors",
    ["api_provider", "error_type"],
)

# =============================================================================
# RESULT PROCESSING METRICS
# =============================================================================

processing_duration_seconds = Histogram(
    "agent_grey_processing_duration_seconds",
    "Time spent processing search results",
    ["operation"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, float("inf")],
)

deduplication_rate = Gauge(
    "agent_grey_deduplication_rate",
    "Percentage of duplicate results detected (0-100)",
)

results_processed_total = Counter(
    "agent_grey_results_processed_total",
    "Total number of search results processed",
    ["status"],  # 'success', 'duplicate', 'error'
)

# =============================================================================
# REVIEW METRICS
# =============================================================================

review_decisions_total = Counter(
    "agent_grey_review_decisions_total",
    "Total number of review decisions made",
    ["decision"],  # 'include', 'exclude', 'undecided'
)

review_velocity_per_hour = Gauge(
    "agent_grey_review_velocity_per_hour",
    "Current review decisions per hour (rolling average)",
)
