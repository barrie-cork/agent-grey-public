"""
Logging context middleware for automatic metadata binding.

Enhances all logs within a request with useful contextual information.
"""

import os
import time

import structlog

logger = structlog.get_logger(__name__)


class LoggingContextMiddleware:
    """
    Logging context middleware.

    Tracks request timing, metadata, and response details.

    Features:
    - Request timing
    - Client IP address extraction
    - User agent tracking
    - Session information
    - Response status and metrics logging
    """

    # Paths to skip logging (health checks, monitoring endpoints)
    SKIP_LOGGING_PATHS = [
        "/health/",
        "/metrics/",
        "/ready/",
        "/live/",
        "/nginx-health",
        "/healthcheck",  # Flower health check
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Sync middleware path -- Django wraps this for ASGI automatically."""
        start_time = time.time()

        # Gather request metadata
        self._bind_request_context(request, start_time)

        # Process request
        try:
            response = self.get_response(request)
        except Exception as e:
            # Log exception with context
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "request_exception",
                exc_info=True,
                exception_type=type(e).__name__,
                exception_message=str(e),
                duration_ms=round(duration_ms, 2),
            )
            raise

        # Log response
        self._log_response(request, response, start_time)

        return response

    def _bind_request_context(self, request, start_time):
        """Bind request metadata to logging context."""
        # Extract client IP
        client_ip = self._get_client_ip(request)

        # Bind metadata to structlog
        structlog.contextvars.bind_contextvars(
            client_ip=client_ip,
            user_agent=request.META.get("HTTP_USER_AGENT", "unknown")[:200],
            referer=request.META.get("HTTP_REFERER", "")[:200],
            is_ajax=request.headers.get("X-Requested-With") == "XMLHttpRequest",
            request_time=start_time,
        )

        # Add session info if available
        if hasattr(request, "session") and request.session.session_key:
            structlog.contextvars.bind_contextvars(
                session_key=request.session.session_key[:8]  # First 8 chars only
            )

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP with proxy support."""
        # Check X-Forwarded-For (load balancer)
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

        # Check X-Real-IP (nginx)
        x_real_ip = request.META.get("HTTP_X_REAL_IP")
        if x_real_ip:
            return x_real_ip.strip()

        # Fall back to REMOTE_ADDR
        return request.META.get("REMOTE_ADDR", "unknown")

    def _log_response(self, request, response, start_time, duration=None):
        """Log response details."""
        # Skip logging for health check endpoints
        if any(request.path.startswith(path) for path in self.SKIP_LOGGING_PATHS):
            return

        if duration is None:
            duration = (time.time() - start_time) * 1000

        # Get logging mode from environment
        # Options: 'all', 'errors_only' (default), 'errors_and_slow'
        logging_mode = os.environ.get("DEV_REQUEST_LOGGING", "errors_only").lower()

        # Conditional logging based on mode
        if logging_mode == "errors_only":
            # Only log errors (4xx and 5xx status codes)
            if response.status_code < 400:
                return
        elif logging_mode == "errors_and_slow":
            # Log errors and slow requests (>500ms)
            if response.status_code < 400 and duration < 500:
                return
        # If 'all' or unrecognised mode, log everything (original behaviour)

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round(duration, 2),
            content_length=len(response.content) if hasattr(response, "content") else 0,
        )
