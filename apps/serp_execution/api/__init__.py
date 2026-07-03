"""
SERP Execution API modules.

Focused endpoint modules grouped by responsibility.
"""

from .diagnostic_endpoints import (
    create_test_session_api,
    diagnostic_api_test,
    update_test_session_api,
)
from .execution_endpoints import (
    execution_status_api,
    get_raw_results_count,
    retry_execution_api,
)

# Import key functions for backward compatibility
from .session_endpoints import (
    cancel_session_api,
    get_session_execution_stats,
    get_session_executions_data,
    session_diagnostic_api,
    session_progress_api,
    session_query_progress_api,
    session_quick_status_api,
)

__all__ = [
    # Session endpoints
    "get_session_executions_data",
    "session_progress_api",
    "session_diagnostic_api",
    "cancel_session_api",
    "session_quick_status_api",
    "session_query_progress_api",
    "get_session_execution_stats",
    # Execution endpoints
    "execution_status_api",
    "retry_execution_api",
    "get_raw_results_count",
    # Diagnostic endpoints
    "diagnostic_api_test",
    "create_test_session_api",
    "update_test_session_api",
]
