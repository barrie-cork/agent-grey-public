"""
Core logging utilities for the application.
Provides ServiceLoggerMixin for services and RequestIDMiddleware for request tracking.
"""

import logging
import uuid
from contextvars import ContextVar

# Context variable for request ID tracking across async boundaries
request_id_context = ContextVar("request_id", default="")


class RequestIDFilter(logging.Filter):
    """Logging filter that adds request ID to log records."""

    def filter(self, record):
        """Add request_id to the log record."""
        record.request_id = request_id_context.get() or "no-request"
        return True


class ServiceLoggerMixin:
    """
    Mixin to provide structured logging capabilities to service classes.

    Usage:
        class MyService(ServiceLoggerMixin):
            def my_method(self):
                self.log_info("Processing started", item_id=123)
    """

    @property
    def logger(self) -> logging.Logger:
        """Get logger instance for this service."""
        if not hasattr(self, "_logger"):
            # Use module path for logger name to maintain hierarchy
            logger_name = f"apps.{self.__module__}"
            self._logger = logging.getLogger(logger_name)
        return self._logger

    def log_debug(self, message, **context):
        """Log debug message with structured context.

        Args:
            message: Debug message text.
            **context: Additional context data for logging.
        """
        self._log_with_context("debug", message, **context)

    def log_info(self, message, **context):
        """Log info message with structured context.

        Args:
            message: Info message text.
            **context: Additional context data for logging.
        """
        self._log_with_context("info", message, **context)

    def log_warning(self, message, **context):
        """Log warning message with structured context.

        Args:
            message: Warning message text.
            **context: Additional context data for logging.
        """
        self._log_with_context("warning", message, **context)

    def log_error(self, message, error=None, **context):
        """
        Log error message with structured context.

        Args:
            message: Error message
            error:  exception to include in context
            **context: Additional context data
        """
        if error:
            context["error_type"] = type(error).__name__
            context["error_message"] = str(error)
            # Include traceback for debugging
            import traceback

            context["error_traceback"] = traceback.format_exc()

        self._log_with_context("error", message, **context)

    def _log_with_context(self, level, message, **context):
        """
        Internal method to log with structured context.

        Args:
            level: Log level (debug, info, warning, error)
            message: Log message
            **context: Context data to include
        """
        # Add service class name to context
        context["service"] = self.__class__.__name__

        # Create extra dict for structured logging
        extra = {"context": context}

        # Use appropriate log level method
        log_method = getattr(self.logger, level)
        log_method(message, extra=extra)


class RequestIDMiddleware:
    """
    Django middleware to generate and track request IDs throughout the request lifecycle.

    Adds X-Request-ID header to responses and makes request ID available
    for logging throughout the request processing.
    """

    def __init__(self, get_response):
        """Initialize middleware with the get_response callable."""
        self.get_response = get_response

    def __call__(self, request):
        """Process request and add request ID tracking."""
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Store on request object for easy access
        request.request_id = request_id

        # Set in context variable for logging
        request_id_context.set(request_id)

        # Log request start
        logger = logging.getLogger("apps.core.middleware")
        logger.info(
            f"Request started: {request.method} {request.path}",
            extra={
                "context": {
                    "method": request.method,
                    "path": request.path,
                    "user": (
                        getattr(request.user, "username", "anonymous")
                        if hasattr(request, "user")
                        else "anonymous"
                    ),
                    "remote_addr": request.META.get("REMOTE_ADDR", ""),
                }
            },
        )

        try:
            # Process request
            response = self.get_response(request)

            # Add request ID to response headers
            response["X-Request-ID"] = request_id

            # Log request completion
            logger.info(
                f"Request completed: {request.method} {request.path} - {response.status_code}",
                extra={
                    "context": {
                        "method": request.method,
                        "path": request.path,
                        "status_code": response.status_code,
                        "user": (
                            getattr(request.user, "username", "anonymous")
                            if hasattr(request, "user")
                            else "anonymous"
                        ),
                    }
                },
            )

            return response

        except Exception as e:
            # Log request error
            logger.error(
                f"Request failed: {request.method} {request.path}",
                extra={
                    "context": {
                        "method": request.method,
                        "path": request.path,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    }
                },
            )
            raise
        finally:
            # Clear context variable
            request_id_context.set("")
