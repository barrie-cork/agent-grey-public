"""
Custom Logging Filters for Agent Grey
======================================

This module provides custom logging filters to protect sensitive data
and enhance log output.
"""

import logging
import re
from typing import Dict, List


class SensitiveDataFilter(logging.Filter):
    """
    Filter to redact sensitive information from log messages.

    This filter looks for patterns that might contain sensitive data
    like passwords, API keys, tokens, etc., and redacts them.
    """

    # Patterns to search for sensitive data
    SENSITIVE_PATTERNS = [
        (
            r'(password|passwd|pwd)[\s]*[=:]\s*["\']?([^"\'\s]+)["\']?',
            r"\1=***REDACTED***",
        ),
        (
            r'(api[_-]?key|apikey)[\s]*[=:]\s*["\']?([^"\'\s]+)["\']?',
            r"\1=***REDACTED***",
        ),
        (
            r'(token|access[_-]?token|auth[_-]?token)[\s]*[=:]\s*["\']?([^"\'\s]+)["\']?',
            r"\1=***REDACTED***",
        ),
        (
            r'(secret|client[_-]?secret)[\s]*[=:]\s*["\']?([^"\'\s]+)["\']?',
            r"\1=***REDACTED***",
        ),
        (r"(Bearer\s+)([A-Za-z0-9\-._~+/]+)", r"\1***REDACTED***"),
        (r"(Authorization:\s+)([^\s]+)", r"\1***REDACTED***"),
        # Email addresses (partial redaction)
        (r"([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", r"***@\2"),
        # Credit card numbers
        (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", r"****-****-****-****"),
        # Social Security Numbers
        (r"\b\d{3}-\d{2}-\d{4}\b", r"***-**-****"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter the log record to redact sensitive information.

        Args:
            record: The log record to filter

        Returns:
            True to allow the record through (always True for this filter)
        """
        # Redact sensitive data from the message
        if hasattr(record, "msg"):
            msg = str(record.msg)
            for pattern, replacement in self.SENSITIVE_PATTERNS:
                msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)
            record.msg = msg

        # Also redact from args if present (only redact string args to
        # preserve numeric types needed by format specifiers like %.3f)
        if hasattr(record, "args") and record.args:
            if isinstance(record.args, dict):
                cleaned_args = {}
                for key, arg in record.args.items():
                    if isinstance(arg, str):
                        for pattern, replacement in self.SENSITIVE_PATTERNS:
                            arg = re.sub(pattern, replacement, arg, flags=re.IGNORECASE)
                    cleaned_args[key] = arg
                record.args = cleaned_args
            else:
                cleaned_args = []
                for arg in record.args:
                    if isinstance(arg, str):
                        for pattern, replacement in self.SENSITIVE_PATTERNS:
                            arg = re.sub(pattern, replacement, arg, flags=re.IGNORECASE)
                    cleaned_args.append(arg)
                record.args = tuple(cleaned_args)

        return True


class PerformanceFilter(logging.Filter):
    """
    Filter to add performance metrics to log records.

    This filter can add timing information, memory usage, and other
    performance metrics to log records.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add performance metrics to the log record.

        Args:
            record: The log record to enhance

        Returns:
            True to allow the record through
        """
        import time

        import psutil

        # Add timestamp
        record.timestamp = time.time()

        # Add memory usage
        process = psutil.Process()
        record.memory_mb = process.memory_info().rss / 1024 / 1024

        # Add CPU usage
        record.cpu_percent = process.cpu_percent()

        return True


class RequestContextFilter(logging.Filter):
    """
    Filter to add request context to log records.

    This filter adds information about the current HTTP request
    to log records when available.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add request context to the log record.

        Args:
            record: The log record to enhance

        Returns:
            True to allow the record through
        """
        from django.core.handlers.wsgi import WSGIRequest

        # Try to get the request from the record
        request = getattr(record, "request", None)

        if request and isinstance(request, WSGIRequest):
            # Add request information
            record.request_method = request.method
            record.request_path = request.path
            record.request_user = (
                str(request.user) if hasattr(request, "user") else "Anonymous"
            )
            record.request_ip = self._get_client_ip(request)
            record.request_id = getattr(request, "id", None)
        else:
            # Set defaults when no request is available
            record.request_method = None
            record.request_path = None
            record.request_user = None
            record.request_ip = None
            record.request_id = None

        return True

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class ErrorAggregationFilter(logging.Filter):
    """
    Filter to aggregate similar errors and prevent log spam.

    This filter tracks similar errors and can suppress repeated
    occurrences within a time window.
    """

    def __init__(self, window_seconds: int = 60, max_duplicates: int = 5):
        """
        Initialize the error aggregation filter.

        Args:
            window_seconds: Time window for aggregation
            max_duplicates: Maximum duplicates to allow in window
        """
        super().__init__()
        self.window_seconds = window_seconds
        self.max_duplicates = max_duplicates
        self.error_cache: Dict[str, List[float]] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter out duplicate errors within the time window.

        Args:
            record: The log record to filter

        Returns:
            False to suppress the record, True to allow it through
        """
        import time

        # Only aggregate ERROR and above
        if record.levelno < logging.ERROR:
            return True

        # Create a key for this error
        error_key = f"{record.name}:{record.msg}:{record.funcName}"

        current_time = time.time()

        # Get or create the timestamp list for this error
        if error_key not in self.error_cache:
            self.error_cache[error_key] = []

        timestamps = self.error_cache[error_key]

        # Remove old timestamps outside the window
        timestamps[:] = [
            t for t in timestamps if current_time - t < self.window_seconds
        ]

        # Check if we've exceeded the duplicate limit
        if len(timestamps) >= self.max_duplicates:
            # Suppress this error
            return False

        # Add this occurrence
        timestamps.append(current_time)

        # Add aggregation info to the record
        record.occurrence_count = len(timestamps)
        record.is_duplicate = len(timestamps) > 1

        return True


class EnvironmentFilter(logging.Filter):
    """
    Filter to add environment information to log records.

    This filter adds information about the current environment
    (development, staging, production) to log records.
    """

    def __init__(self, environment: str = None):
        """
        Initialize the environment filter.

        Args:
            environment: The environment name (auto-detected if None)
        """
        super().__init__()
        if environment is None:
            from django.conf import settings

            if hasattr(settings, "DEBUG"):
                environment = "development" if settings.DEBUG else "production"
            else:
                environment = "unknown"
        self.environment = environment

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add environment information to the log record.

        Args:
            record: The log record to enhance

        Returns:
            True to allow the record through
        """
        record.environment = self.environment
        return True
