"""
Service Exception Classes

This module defines all exception classes used by the Agent Grey services.
These exceptions provide structured error handling for various service operations.
"""


class SerperError(Exception):
    """Base exception for Serper API errors."""

    pass


class SerperRateLimitError(SerperError):
    """Raised when rate limited by Serper API."""

    pass


class SerperAuthError(SerperError):
    """Raised for authentication errors."""

    pass


class SerperQuotaError(SerperError):
    """Raised when API quota is exceeded."""

    pass


class SerperTimeoutError(SerperError):
    """Raised for timeout errors."""

    pass


class SerperConnectionError(SerperError):
    """Raised for connection errors."""

    pass
