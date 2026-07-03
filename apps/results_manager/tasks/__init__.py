"""
Results Manager tasks package.

This module maintains backward compatibility by re-exporting all tasks
from their new organized modules.
"""

from .monitoring import (
    check_stuck_executions,
    check_stuck_sessions,
    cleanup_orphaned_processing_sessions,
)

# Import all tasks to maintain backward compatibility
from .orchestration import create_processing_workflow, process_session_results_task
from .processing import (
    finalize_processing_task,
    process_batch_task,
    run_deduplication_task,
)

# Configuration constants - shared across modules
BATCH_SIZE = 50
MAX_RETRIES = 3
RETRY_DELAY = 60  # seconds

__all__ = [
    # Orchestration tasks
    "process_session_results_task",
    "create_processing_workflow",
    # Processing tasks
    "process_batch_task",
    "run_deduplication_task",
    "finalize_processing_task",
    # Monitoring tasks
    "check_stuck_sessions",
    "check_stuck_executions",
    "cleanup_orphaned_processing_sessions",
    # Constants
    "BATCH_SIZE",
    "MAX_RETRIES",
    "RETRY_DELAY",
]
