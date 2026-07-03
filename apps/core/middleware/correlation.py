"""
Correlation ID middleware for request tracking across services.

Generates or extracts correlation IDs from requests and binds them
to the logging context for the entire request lifecycle.
"""

import uuid

import structlog

logger = structlog.get_logger(__name__)


class CorrelationIDMiddleware:
    """
    Correlation ID middleware.

    Features:
    - Accepts existing X-Correlation-ID or X-Request-ID headers
    - Generates new UUID if no header present
    - Binds correlation ID to structlog context
    - Adds correlation ID to response headers
    - Thread-safe using context vars
    """

    # Header names to check (in order)
    CORRELATION_HEADER_NAMES = [
        "HTTP_X_CORRELATION_ID",
        "HTTP_X_REQUEST_ID",
    ]
    RESPONSE_HEADER_NAME = "X-Correlation-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Sync middleware path -- Django wraps this for ASGI automatically."""
        # Setup correlation ID and bind to context
        correlation_id = self._setup_correlation(request)

        # Process request through middleware chain
        try:
            response = self.get_response(request)
        except Exception as e:
            # Log exception with correlation context
            logger.error(
                "request_exception",
                exc_info=True,
                exception_type=type(e).__name__,
                exception_message=str(e),
            )
            raise

        # Add correlation ID to response headers
        response[self.RESPONSE_HEADER_NAME] = correlation_id

        return response

    def _setup_correlation(self, request):
        """Extract or generate correlation ID and bind to logging context."""
        # Try to extract from headers
        correlation_id = None
        for header_name in self.CORRELATION_HEADER_NAMES:
            correlation_id = request.META.get(header_name)
            if correlation_id:
                break

        # Generate new ID if not provided
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store on request for access in views
        request.correlation_id = correlation_id

        # Bind to structlog context (thread-safe with contextvars)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            request_path=request.path,
            request_method=request.method,
        )

        # Add user context if authenticated
        if hasattr(request, "user") and request.user.is_authenticated:
            structlog.contextvars.bind_contextvars(
                user_id=str(request.user.id),
                user_email=request.user.email,
                is_staff=request.user.is_staff,
            )

        return correlation_id
