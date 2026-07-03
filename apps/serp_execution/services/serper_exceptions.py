"""
Custom exceptions for Serper API operations.
Provides granular error handling for different failure scenarios.
"""


class SerperAPIError(Exception):
    """Base exception for Serper API errors."""

    def __init__(
        self, message: str, error_code: str | None = None, details: dict | None = None
    ):
        """
        Initialize the exception with additional context.

        Args:
            message: Error message
            error_code: Optional error code from API
            details: Optional dictionary with additional error details
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


class SerperRateLimitError(SerperAPIError):
    """Raised when API rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int | None = None, **kwargs):
        """
        Initialize rate limit error.

        Args:
            message: Error message
            retry_after: Seconds to wait before retrying
            **kwargs: Additional error details
        """
        super().__init__(message, error_code="RATE_LIMIT_EXCEEDED", **kwargs)
        self.retry_after = retry_after


class SerperAuthenticationError(SerperAPIError):
    """Raised when API authentication fails."""

    def __init__(self, message: str = "Authentication failed", **kwargs):
        """Initialize authentication error."""
        super().__init__(message, error_code="AUTH_FAILED", **kwargs)


class SerperAuthError(SerperAuthenticationError):
    """Alias for backward compatibility."""

    pass


class SerperQuotaError(SerperAPIError):
    """Raised when API quota is exceeded."""

    def __init__(self, message: str, remaining_quota: int | None = None, **kwargs):
        """
        Initialize quota error.

        Args:
            message: Error message
            remaining_quota: Remaining quota if available
            **kwargs: Additional error details
        """
        super().__init__(message, error_code="QUOTA_EXCEEDED", **kwargs)
        self.remaining_quota = remaining_quota


class SerperValidationError(SerperAPIError):
    """Raised when request validation fails."""

    def __init__(self, message: str, field: str | None = None, **kwargs):
        """
        Initialize validation error.

        Args:
            message: Error message
            field: Field that failed validation
            **kwargs: Additional error details
        """
        super().__init__(message, error_code="VALIDATION_FAILED", **kwargs)
        self.field = field


class SerperTimeoutError(SerperAPIError):
    """Raised when API request times out."""

    def __init__(
        self, message: str = "Request timed out", timeout: float | None = None, **kwargs
    ):
        """
        Initialize timeout error.

        Args:
            message: Error message
            timeout: Timeout value in seconds
            **kwargs: Additional error details
        """
        super().__init__(message, error_code="TIMEOUT", **kwargs)
        self.timeout = timeout


class SerperResponseError(SerperAPIError):
    """Raised when API response is invalid or unexpected."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
        **kwargs,
    ):
        """
        Initialize response error.

        Args:
            message: Error message
            status_code: HTTP status code
            response_body: Raw response body
            **kwargs: Additional error details
        """
        super().__init__(message, error_code="INVALID_RESPONSE", **kwargs)
        self.status_code = status_code
        self.response_body = response_body


class SerperConnectionError(SerperAPIError):
    """Raised when connection to API fails."""

    def __init__(self, message: str = "Connection failed", **kwargs):
        """Initialize connection error."""
        super().__init__(message, error_code="CONNECTION_FAILED", **kwargs)


class SerperCircuitBreakerError(SerperAPIError):
    """Raised when circuit breaker is open."""

    def __init__(
        self,
        message: str = "Circuit breaker is open",
        state: str | None = None,
        **kwargs,
    ):
        """
        Initialize circuit breaker error.

        Args:
            message: Error message
            state: Current circuit breaker state
            **kwargs: Additional error details
        """
        super().__init__(message, error_code="CIRCUIT_BREAKER_OPEN", **kwargs)
        self.state = state
