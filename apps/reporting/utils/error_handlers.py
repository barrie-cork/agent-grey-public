"""
Error handling utilities for the reporting app.

This module provides decorators and functions for consistent error handling
across the reporting app, especially for PRISMA-related operations.
"""

import logging
from functools import wraps
from typing import Any, Callable

from django.contrib import messages

logger = logging.getLogger(__name__)


def handle_prisma_errors(default_return: Any = None):
    """
    Decorator to handle common PRISMA-related errors gracefully.

    Args:
        default_return: The value to return when an error occurs (default: None)

    Returns:
        Decorated function that handles errors gracefully

    Example:
        @handle_prisma_errors(default_return={})
        def get_prisma_data(self):
            # Method implementation that might raise errors
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (ValueError, TypeError) as e:
                # Handle data validation errors
                if hasattr(args[0], "request"):
                    messages.error(
                        args[0].request, f"Error loading PRISMA data: {str(e)}"
                    )
                logger.error(f"PRISMA data error in {func.__name__}: {str(e)}")
                return default_return if default_return is not None else {}
            except AttributeError as e:
                # Handle missing attributes
                logger.error(f"Missing attribute in {func.__name__}: {str(e)}")
                return default_return if default_return is not None else {}
            except Exception:
                # Handle unexpected errors
                logger.exception(f"Unexpected error in {func.__name__}")
                if hasattr(args[0], "request"):
                    messages.error(
                        args[0].request,
                        "An unexpected error occurred while processing PRISMA data",
                    )
                return default_return if default_return is not None else {}

        return wrapper

    return decorator


def handle_report_generation_errors(func: Callable) -> Callable:
    """
    Decorator specifically for report generation error handling.

    This decorator is designed for methods that generate reports and need
    specific error handling for file generation issues.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ImportError as e:
            # Handle missing dependencies
            logger.error(f"Missing dependency in {func.__name__}: {str(e)}")
            if "weasyprint" in str(e).lower():
                error_msg = "PDF generation requires WeasyPrint. Please install it."
            elif "docx" in str(e).lower():
                error_msg = "DOCX generation requires python-docx. Please install it."
            else:
                error_msg = f"Missing required dependency: {str(e)}"

            # Try to notify user if possible
            if hasattr(args[0], "request"):
                messages.error(args[0].request, error_msg)

            raise  # Re-raise to handle at higher level
        except (IOError, OSError) as e:
            # Handle file system errors
            logger.error(f"File system error in {func.__name__}: {str(e)}")
            if hasattr(args[0], "request"):
                messages.error(
                    args[0].request, "Error saving report file. Please try again."
                )
            raise
        except Exception:
            # Log unexpected errors
            logger.exception(f"Unexpected error in report generation: {func.__name__}")
            raise

    return wrapper


class ReportingErrorContext:
    """
    Context manager for handling errors in reporting operations.

    Example:
        with ReportingErrorContext(request, "loading PRISMA data"):
            # Code that might raise errors
            pass
    """

    def __init__(self, request, operation: str, default_return: Any = None):
        """
        Initialize error context.

        Args:
            request: Django request object for user messages
            operation: Description of the operation being performed
            default_return: Value to return if an error occurs
        """
        self.request = request
        self.operation = operation
        self.default_return = default_return
        self.error_occurred = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return False

        self.error_occurred = True

        # Log the error
        logger.error(
            f"Error during {self.operation}: {exc_type.__name__}: {exc_val}",
            exc_info=True,
        )

        # Show user message if request is available
        if self.request:
            if exc_type in (ValueError, TypeError):
                messages.error(
                    self.request, f"Invalid data while {self.operation}: {str(exc_val)}"
                )
            elif exc_type is AttributeError:
                messages.error(self.request, f"Missing data while {self.operation}")
            else:
                messages.error(
                    self.request, f"An error occurred while {self.operation}"
                )

        # Suppress the exception
        return True


def log_and_return_default(
    error: Exception, operation: str, default_return: Any = None
) -> Any:
    """
    Log an error and return a default value.

    This is useful for simple error handling where you just want to log
    and continue with a default value.

    Args:
        error: The exception that occurred
        operation: Description of what was being attempted
        default_return: Value to return (default: None)

    Returns:
        The default_return value
    """
    logger.error(f"Error during {operation}: {type(error).__name__}: {str(error)}")
    return default_return
