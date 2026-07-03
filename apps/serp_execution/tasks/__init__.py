"""
SERP execution tasks module.

This module provides Celery tasks for search execution, monitoring, and retry operations.
The tasks have been decomposed from the original monolithic tasks.py file for better
maintainability and separation of concerns.

Backward compatibility is maintained - all original task names are preserved.
"""

from .execution import perform_serp_query_task, retry_failed_execution_task
from .helpers import (
    _send_execution_notification,
    _send_session_notification,
    _should_retry_execution,
    calculate_estimated_completion_time,
    format_progress_message,
    should_send_alert,
)

# Import all tasks from the decomposed modules
from .monitoring import monitor_session_completion_task

# Import simplified tasks (ultra-simple architecture)
from .simple_tasks import (
    execute_search_session_simple,
    initiate_search_session_execution_task,
    process_session_results_simple,
)

# Export all tasks for backward compatibility
__all__ = [
    # Monitoring tasks
    "monitor_session_completion_task",
    # Execution tasks
    "perform_serp_query_task",
    "retry_failed_execution_task",
    "initiate_search_session_execution_task",
    "execute_search_session_simple",
    "process_session_results_simple",
    # Helper functions (for internal use)
    "_should_retry_execution",
    "_send_execution_notification",
    "_send_session_notification",
    "format_progress_message",
    "calculate_estimated_completion_time",
    "should_send_alert",
]
