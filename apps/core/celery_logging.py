"""
Celery task logging with correlation ID propagation.

Ensures Celery tasks inherit correlation IDs from originating requests
and bind task-specific context to logs.

Environment variables:
- CELERY_TASK_LOGGING_ENABLED: Enable full task lifecycle logging (default: true)
  Set to 'false' to disable task_started/task_completed logs
  Errors and retries are always logged regardless of this setting
"""

import os

import structlog
from celery import signals
from celery.utils.log import get_task_logger

logger = structlog.get_logger(__name__)
celery_logger = get_task_logger(__name__)

# Check if task logging is enabled (default: true, can be disabled via environment)
CELERY_TASK_LOGGING_ENABLED = os.environ.get(
    "CELERY_TASK_LOGGING_ENABLED", "true"
).lower() in ("true", "1", "yes")


@signals.task_prerun.connect
def bind_task_context(
    sender=None, task_id=None, task=None, args=None, kwargs=None, **extra
):
    """
    Bind task context before task execution.

    Args:
        sender: Task class
        task_id: Unique task ID
        task: Task instance
        args: Task positional arguments
        kwargs: Task keyword arguments
    """
    # Clear any existing context
    structlog.contextvars.clear_contextvars()

    # Bind task context
    structlog.contextvars.bind_contextvars(
        task_id=task_id,
        task_name=task.name if task else "unknown",
    )

    # Check for correlation ID in task request headers
    if task and hasattr(task.request, "correlation_id"):
        correlation_id = task.request.correlation_id
    elif kwargs and "correlation_id" in kwargs:
        correlation_id = kwargs["correlation_id"]
    else:
        # Generate new correlation ID for orphaned tasks
        import uuid

        correlation_id = str(uuid.uuid4())

    structlog.contextvars.bind_contextvars(
        correlation_id=correlation_id,
    )

    # Only log task_started if logging is enabled
    if CELERY_TASK_LOGGING_ENABLED:
        logger.info(
            "task_started",
            args_count=len(args) if args else 0,
            kwargs_keys=list(kwargs.keys()) if kwargs else [],
        )


@signals.task_postrun.connect
def log_task_completion(
    sender=None,
    task_id=None,
    task=None,
    args=None,
    kwargs=None,
    retval=None,
    state=None,
    **extra,
):
    """
    Log task completion with context.

    Args:
        sender: Task class
        task_id: Unique task ID
        task: Task instance
        args: Task positional arguments
        kwargs: Task keyword arguments
        retval: Task return value
        state: Task state (SUCCESS, FAILURE, etc.)
    """
    # Only log task_completed if logging is enabled
    if CELERY_TASK_LOGGING_ENABLED:
        logger.info(
            "task_completed",
            task_state=state,
            has_return_value=retval is not None,
        )


@signals.task_failure.connect
def log_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **extra,
):
    """
    Log task failure with exception details.

    Args:
        sender: Task class
        task_id: Unique task ID
        exception: The raised exception
        args: Task positional arguments
        kwargs: Task keyword arguments
        traceback: Exception traceback
        einfo: Exception info
    """
    logger.error(
        "task_failed",
        exception_type=type(exception).__name__ if exception else "Unknown",
        exception_message=str(exception) if exception else "Unknown",
        exc_info=einfo if einfo else True,
    )


@signals.task_retry.connect
def log_task_retry(sender=None, task_id=None, reason=None, einfo=None, **extra):
    """
    Log task retry attempts.

    Args:
        sender: Task class
        task_id: Unique task ID
        reason: Retry reason
        einfo: Exception info
    """
    logger.warning(
        "task_retrying",
        retry_reason=str(reason) if reason else "Unknown",
    )
