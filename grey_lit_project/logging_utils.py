"""
Logging Utilities for Agent Grey
=================================

This module provides utility functions and decorators for enhanced logging
throughout the application.
"""

import functools
import json
import logging
import time
from typing import Callable, Optional

from django.core.serializers.json import DjangoJSONEncoder


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: The logger name (usually __name__ from the calling module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def log_execution_time(
    logger: Optional[logging.Logger] = None, level: int = logging.INFO
):
    """
    Decorator to log the execution time of a function.

    Args:
        logger: Logger instance to use (creates one if None)
        level: Log level for the timing message

    Example:
        @log_execution_time()
        def slow_function():
            time.sleep(1)
    """

    def decorator(func: Callable) -> Callable:
        nonlocal logger
        if logger is None:
            logger = logging.getLogger(func.__module__)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.log(level, f"{func.__name__} completed in {duration:.3f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"{func.__name__} failed after {duration:.3f}s: {str(e)}")
                raise

        return wrapper

    return decorator


def log_api_call(service_name: str, logger: Optional[logging.Logger] = None):
    """
    Decorator to log API calls with request/response details.

    Args:
        service_name: Name of the API service being called
        logger: Logger instance to use

    Example:
        @log_api_call("Serper")
        def search_google(query):
            # API call logic
    """

    def decorator(func: Callable) -> Callable:
        nonlocal logger
        if logger is None:
            logger = logging.getLogger("api")

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            # Log the API call start
            logger.info(
                "API Call Started",
                extra={
                    "service": service_name,
                    "function": func.__name__,
                    "args": str(args)[:200],  # Truncate long args
                    "kwargs": str(kwargs)[:200],
                },
            )

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                # Log successful completion
                logger.info(
                    "API Call Completed",
                    extra={
                        "service": service_name,
                        "function": func.__name__,
                        "duration": duration,
                        "success": True,
                    },
                )

                return result
            except Exception as e:
                duration = time.time() - start_time

                # Log failure
                logger.error(
                    "API Call Failed",
                    extra={
                        "service": service_name,
                        "function": func.__name__,
                        "duration": duration,
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                raise

        return wrapper

    return decorator


def log_database_operation(operation: str, logger: Optional[logging.Logger] = None):
    """
    Decorator to log database operations.

    Args:
        operation: Type of database operation (e.g., "create", "update", "delete")
        logger: Logger instance to use
    """

    def decorator(func: Callable) -> Callable:
        nonlocal logger
        if logger is None:
            logger = logging.getLogger(func.__module__)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                logger.debug(
                    f"Database {operation} completed in {duration:.3f}s",
                    extra={
                        "operation": operation,
                        "function": func.__name__,
                        "duration": duration,
                    },
                )

                return result
            except Exception as e:
                duration = time.time() - start_time

                logger.error(
                    f"Database {operation} failed after {duration:.3f}s: {str(e)}",
                    extra={
                        "operation": operation,
                        "function": func.__name__,
                        "duration": duration,
                        "error": str(e),
                    },
                )
                raise

        return wrapper

    return decorator


def log_celery_task(logger: Optional[logging.Logger] = None):
    """
    Decorator to log Celery task execution.

    Args:
        logger: Logger instance to use
    """

    def decorator(func: Callable) -> Callable:
        nonlocal logger
        if logger is None:
            logger = logging.getLogger("celery.task")

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            task_id = self.request.id if hasattr(self, "request") else "unknown"
            start_time = time.time()

            logger.info(
                f"Task {func.__name__} started",
                extra={
                    "task_name": func.__name__,
                    "task_id": task_id,
                    "args": str(args)[:200],
                    "kwargs": str(kwargs)[:200],
                },
            )

            try:
                result = func(self, *args, **kwargs)
                duration = time.time() - start_time

                logger.info(
                    f"Task {func.__name__} completed",
                    extra={
                        "task_name": func.__name__,
                        "task_id": task_id,
                        "duration": duration,
                        "success": True,
                    },
                )

                return result
            except Exception as e:
                duration = time.time() - start_time

                logger.error(
                    f"Task {func.__name__} failed",
                    extra={
                        "task_name": func.__name__,
                        "task_id": task_id,
                        "duration": duration,
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
                raise

        return wrapper

    return decorator


class StructuredLogger:
    """
    A structured logger that outputs JSON-formatted logs.

    This is useful for log aggregation systems and analysis tools.
    """

    def __init__(self, name: str):
        """
        Initialize the structured logger.

        Args:
            name: Logger name
        """
        self.logger = logging.getLogger(name)
        self.encoder = DjangoJSONEncoder()

    def _log(self, level: int, message: str, **kwargs):
        """
        Internal method to log structured data.

        Args:
            level: Log level
            message: Log message
            **kwargs: Additional structured data
        """
        data = {"message": message, "timestamp": time.time(), **kwargs}

        # Convert to JSON string
        json_str = json.dumps(data, cls=DjangoJSONEncoder)

        # Log the JSON string
        self.logger.log(level, json_str)

    def debug(self, message: str, **kwargs):
        """Log a debug message with structured data."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log an info message with structured data."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log a warning message with structured data."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log an error message with structured data."""
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        """Log a critical message with structured data."""
        self._log(logging.CRITICAL, message, **kwargs)


class LogContext:
    """
    Context manager for adding contextual information to logs.

    Example:
        with LogContext(user_id=123, session_id="abc"):
            logger.info("Processing request")  # Will include user_id and session_id
    """

    def __init__(self, **context):
        """
        Initialize the log context.

        Args:
            **context: Key-value pairs to add to log context
        """
        self.context = context
        self._old_factory = None

    def __enter__(self):
        """Enter the context and set up logging."""
        import logging

        self._old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = self._old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context and restore logging."""
        import logging

        logging.setLogRecordFactory(self._old_factory)


def log_user_action(action: str, user=None, session=None, details: dict = None):
    """
    Log a user action for audit purposes.

    Args:
        action: The action being performed
        user: The user performing the action
        session: The session context
        details: Additional details about the action
    """
    logger = logging.getLogger("security")

    log_data = {
        "action": action,
        "user": str(user) if user else "anonymous",
        "user_id": user.id if user and hasattr(user, "id") else None,
        "session_id": str(session.id) if session and hasattr(session, "id") else None,
        "timestamp": time.time(),
    }

    if details:
        log_data.update(details)

    logger.info(f"User action: {action}", extra=log_data)


def setup_request_logging(get_response):
    """
    Middleware to add request logging.

    This should be added to MIDDLEWARE in settings.
    """

    def middleware(request):
        # Generate request ID
        import uuid

        request.id = str(uuid.uuid4())

        # Log request start
        logger = logging.getLogger("django.request")
        logger.info(
            f"Request started: {request.method} {request.path}",
            extra={
                "request_id": request.id,
                "method": request.method,
                "path": request.path,
                "user": str(request.user) if hasattr(request, "user") else None,
            },
        )

        # Process request
        response = get_response(request)

        # Log request completion
        logger.info(
            f"Request completed: {request.method} {request.path} - {response.status_code}",
            extra={
                "request_id": request.id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
            },
        )

        return response

    return middleware
