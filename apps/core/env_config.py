"""
Centralized environment configuration utility.

This module provides a unified interface for accessing environment variables
that works correctly in both development (with .env files) and production
(with direct environment variables).

This resolves the decouple library import conflicts that cause TypeErrors
in production environments.
"""

import os
from typing import Any, Optional, Type


def _is_debug_mode() -> bool:
    """
    Safely check if running in debug mode.

    Returns False if Django settings are not yet configured.
    """
    try:
        from django.conf import settings

        # Check if settings are configured before accessing DEBUG
        if settings.configured:
            return getattr(settings, "DEBUG", False)
        return False
    except (ImportError, Exception):
        # Django not available or settings not configured yet
        return False


def _cast_to_bool(value: Any) -> bool:
    """
    Cast value to boolean following Django/decouple conventions.

    Accepts common truthy string representations: true, 1, yes, on, t, y
    (case-insensitive). All other string values are considered False.

    Args:
        value: Value to cast to boolean

    Returns:
        Boolean representation of the value
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on", "t", "y")
    return bool(value)


def _get_from_decouple(key: str, default: Any, cast: Optional[Type]) -> Any:
    """
    Get value from python-decouple if available.

    Attempts to use the decouple library for .env file support in development.
    Returns None if decouple is not available, allowing caller to fall back
    to os.environ.

    Args:
        key: Environment variable name
        default: Default value if not found
        cast: Type to cast the value to

    Returns:
        Value from decouple, or None if decouple not available
    """
    try:
        from decouple import config

        # The decouple library's config() function doesn't accept None as a cast parameter
        # It expects either a callable (like int, bool) or no cast parameter at all
        # This conditional ensures compatibility with decouple's API requirements
        if cast is not None:
            return config(key, default=default, cast=cast)
        else:
            return config(key, default=default)
    except ImportError:
        return None  # Caller will fall back to os.environ


def _apply_cast(value: Any, cast: Optional[Type], default: Any) -> Any:
    """
    Apply type casting to value with fallback to default on error.

    Handles boolean casting specially using _cast_to_bool() for proper
    string-to-bool conversion. For other types, attempts to call the cast
    function and returns default if casting fails or returns None.

    Args:
        value: Value to cast
        cast: Type or callable to cast the value to
        default: Default value to return on casting failure

    Returns:
        Cast value, or default if casting fails
    """
    if cast is None:
        return value

    # Handle boolean casting specially
    if cast is bool:
        return _cast_to_bool(value)

    # Cast to specified type
    try:
        if callable(cast):
            result = cast(value)
            # Return default if cast returns None
            if result is None:
                return default
            return result
        else:
            # Handle built-in types (int, float, str, etc.)
            # These are types, not functions, but can be called as constructors
            if cast in (int, float, str):
                return cast(value)
            # Fallback - return value as-is if cast is not recognized
            return value
    except (ValueError, TypeError, Exception):
        # Return default on any casting failure
        return default


def get_env(key: str, default: Any = None, cast: Optional[Type] = None) -> Any:
    """
    Get environment variable with optional type casting.

    In development (DEBUG=True), uses python-decouple to read from .env files.
    In production (DEBUG=False), reads directly from os.environ.

    Args:
        key: Environment variable name
        default: Default value if not found
        cast: Type to cast the value to (int, float, bool, str)

    Returns:
        The environment variable value, cast to the specified type

    Examples:
        >>> timeout = get_env("CACHE_TIMEOUT", default=60, cast=int)
        >>> debug = get_env("DEBUG", default=False, cast=bool)
        >>> api_key = get_env("API_KEY", default="")
    """
    # In development, try to use decouple for .env file support
    if _is_debug_mode():
        decouple_value = _get_from_decouple(key, default, cast)
        if decouple_value is not None:
            return decouple_value

    # In production or if decouple not available, use os.environ directly
    value = os.environ.get(key)

    # If no value found, handle default with optional casting
    if value is None:
        # If we have a cast function and a default, apply cast to default
        if cast is not None and callable(cast) and default is not None:
            try:
                return cast(default)
            except (ValueError, TypeError, Exception):
                # If casting the default fails, return it as-is
                pass
        return default

    # Apply casting to the retrieved value
    return _apply_cast(value, cast, default)


def get_env_bool(key: str, default: bool = False) -> bool:
    """
    Get environment variable as boolean.

    Convenience wrapper for boolean environment variables.

    Args:
        key: Environment variable name
        default: Default boolean value

    Returns:
        Boolean value
    """
    return get_env(key, default=default, cast=bool)


def get_env_int(key: str, default: int = 0) -> int:
    """
    Get environment variable as integer.

    Convenience wrapper for integer environment variables.

    Args:
        key: Environment variable name
        default: Default integer value

    Returns:
        Integer value
    """
    return get_env(key, default=default, cast=int)


def get_env_float(key: str, default: float = 0.0) -> float:
    """
    Get environment variable as float.

    Convenience wrapper for float environment variables.

    Args:
        key: Environment variable name
        default: Default float value

    Returns:
        Float value
    """
    return get_env(key, default=default, cast=float)


def get_env_str(key: str, default: str = "") -> str:
    """
    Get environment variable as string.

    Convenience wrapper for string environment variables.

    Args:
        key: Environment variable name
        default: Default string value

    Returns:
        String value
    """
    return get_env(key, default=default, cast=str)


def get_env_list(key: str, default: str = "", separator: str = ",") -> list[str]:
    """
    Get environment variable as list by splitting on separator.

    Convenience wrapper for environment variables containing comma-separated
    (or other delimiter-separated) values. Strips whitespace from each item.

    Args:
        key: Environment variable name
        default: Default comma-separated string value
        separator: Character to split on (default: comma)

    Returns:
        List of string values with whitespace stripped

    Examples:
        >>> hosts = get_env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
        >>> # Returns: ["localhost", "127.0.0.1"]

        >>> origins = get_env_list("CORS_ORIGINS", "http://a.com, http://b.com")
        >>> # Returns: ["http://a.com", "http://b.com"]  (spaces stripped)

        >>> paths = get_env_list("INCLUDE_PATHS", "/a:/b:/c", separator=":")
        >>> # Returns: ["/a", "/b", "/c"]
    """
    value = get_env(key, default=default, cast=str)
    # Split on separator and strip whitespace from each item
    # Filter out empty strings in case of trailing separators
    return [item.strip() for item in value.split(separator) if item.strip()]


# Environment detection helpers
def is_production() -> bool:
    """Check if running in production environment."""
    return not _is_debug_mode()


def is_development() -> bool:
    """Check if running in development environment."""
    return _is_debug_mode()


def is_digitalocean() -> bool:
    """Check if running on DigitalOcean App Platform."""
    # DigitalOcean sets specific environment variables
    return bool(os.environ.get("DIGITALOCEAN_APP_ID")) or bool(
        os.environ.get("DIGITALOCEAN_ACCESS_TOKEN")
    )


# Feature flags for gradual rollout
USE_UNIFIED_MONITORING = get_env_bool("USE_UNIFIED_MONITORING", default=False)
