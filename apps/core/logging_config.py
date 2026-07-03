"""
Structured logging configuration for Agent Grey.

Provides JSON-formatted logs with correlation IDs and rich context.
"""

import structlog
from django.conf import settings


def configure_structlog():
    """
    Configure structlog with production-ready processors.

    Processors chain:
    1. Add correlation ID from context
    2. Add log level
    3. Add timestamp
    4. Add logger name
    5. Add stack info for errors
    6. Format exceptions
    7. Render as JSON
    """
    structlog.configure(
        processors=[
            # Add correlation ID from context
            structlog.contextvars.merge_contextvars,
            # Add log level
            structlog.processors.add_log_level,
            # Add timestamp in ISO format
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            # Add logger name
            structlog.stdlib.add_logger_name,
            # Add stack info for warnings and errors
            structlog.processors.StackInfoRenderer(),
            # Format exceptions properly
            structlog.processors.format_exc_info,
            # Render as JSON for production
            (
                structlog.processors.JSONRenderer()
                if not settings.DEBUG
                else structlog.dev.ConsoleRenderer()
            ),
        ],
        # Use contextvars for thread-safe context
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a configured structlog logger.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger

    Example:
        logger = get_logger(__name__)
        logger.info("user_login", user_id=user.id, email=user.email)
    """
    return structlog.get_logger(name)
