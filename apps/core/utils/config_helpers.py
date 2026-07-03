"""Configuration helper utilities.

This module provides reusable utility functions for configuration parsing
and validation to eliminate code duplication across settings files.

Created: 2025-10-17
Purpose: Phase 3 of Post-Deployment Refactoring Plan
"""

import logging
import ssl
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def parse_csv_env_var(
    value: str,
    separator: str = ",",
    strip_whitespace: bool = True,
    filter_empty: bool = True,
) -> List[str]:
    """Parse comma-separated environment variable into list.

    Args:
        value: Comma-separated string value
        separator: Character to split on (default: comma)
        strip_whitespace: Whether to strip whitespace from each item
        filter_empty: Whether to filter out empty strings

    Returns:
        List of parsed strings

    Examples:
        >>> parse_csv_env_var("localhost, 127.0.0.1, example.com")
        ['localhost', '127.0.0.1', 'example.com']

        >>> parse_csv_env_var("a,b,,c", filter_empty=True)
        ['a', 'b', 'c']

        >>> parse_csv_env_var("a,b,,c", filter_empty=False)
        ['a', 'b', '', 'c']
    """
    if not value:
        return []

    items = value.split(separator)

    if strip_whitespace:
        items = [item.strip() for item in items]

    if filter_empty:
        items = [item for item in items if item]

    return items


def is_empty_or_whitespace(value: Any) -> bool:
    """Check if value is None, empty string, or whitespace-only string.

    Args:
        value: Value to check

    Returns:
        True if value is empty/whitespace, False otherwise

    Examples:
        >>> is_empty_or_whitespace(None)
        True

        >>> is_empty_or_whitespace("")
        True

        >>> is_empty_or_whitespace("   ")
        True

        >>> is_empty_or_whitespace("hello")
        False

        >>> is_empty_or_whitespace(0)
        False
    """
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    return False


def validate_url_format(
    url: str, allowed_schemes: Optional[List[str]] = None
) -> tuple[bool, str]:
    """Validate URL format and scheme.

    Args:
        url: URL string to validate
        allowed_schemes: List of allowed schemes (e.g., ['http', 'https', 'redis', 'rediss'])
                        If None, allows all schemes

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_url_format("https://example.com")
        (True, "")

        >>> validate_url_format("invalid-url")
        (False, "Invalid URL format: ...")

        >>> validate_url_format("http://example.com", allowed_schemes=['https'])
        (False, "Invalid URL scheme 'http' (allowed: https)")
    """
    if is_empty_or_whitespace(url):
        return False, "URL is empty or None"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    if not parsed.scheme:
        return False, "URL missing scheme (e.g., http://, https://)"

    if allowed_schemes and parsed.scheme not in allowed_schemes:
        return (
            False,
            f"Invalid URL scheme '{parsed.scheme}' (allowed: {', '.join(allowed_schemes)})",
        )

    if not parsed.netloc:
        return False, "URL missing hostname"

    return True, ""


def parse_boolean(value: Any, strict: bool = False) -> bool:
    """Parse boolean value from various formats.

    Args:
        value: Value to parse (bool, str, int, etc.)
        strict: If True, only accept exact boolean strings

    Returns:
        Boolean value

    Examples:
        >>> parse_boolean(True)
        True

        >>> parse_boolean("true")
        True

        >>> parse_boolean("1")
        True

        >>> parse_boolean("yes")
        True

        >>> parse_boolean("no")
        False

        >>> parse_boolean("invalid", strict=True)
        False
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if not isinstance(value, str):
        return bool(value)

    # Case-insensitive string comparison
    value_lower = value.lower().strip()

    # Truthy values
    truthy = ("true", "1", "yes", "on", "t", "y", "enabled", "enable")
    if value_lower in truthy:
        return True

    # Falsy values
    falsy = ("false", "0", "no", "off", "f", "n", "disabled", "disable", "")
    if value_lower in falsy:
        return False

    # In strict mode, unrecognised values return False
    if strict:
        return False

    # In non-strict mode, use Python's truthiness rules
    return bool(value)


def parse_integer(
    value: Any,
    default: int = 0,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> int:
    """Parse integer value with validation.

    Args:
        value: Value to parse
        default: Default value if parsing fails
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)

    Returns:
        Integer value, or default if parsing fails or out of range

    Examples:
        >>> parse_integer("42")
        42

        >>> parse_integer("invalid", default=10)
        10

        >>> parse_integer("100", min_value=0, max_value=50)
        50

        >>> parse_integer("-10", min_value=0)
        0
    """
    try:
        result = int(value)
    except (ValueError, TypeError):
        return default

    # Apply min/max constraints
    if min_value is not None and result < min_value:
        logger.warning(f"Value {result} below minimum {min_value}, using minimum")
        return min_value

    if max_value is not None and result > max_value:
        logger.warning(f"Value {result} above maximum {max_value}, using maximum")
        return max_value

    return result


def parse_float(
    value: Any,
    default: float = 0.0,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> float:
    """Parse float value with validation.

    Args:
        value: Value to parse
        default: Default value if parsing fails
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)

    Returns:
        Float value, or default if parsing fails or out of range

    Examples:
        >>> parse_float("3.14")
        3.14

        >>> parse_float("invalid", default=1.0)
        1.0

        >>> parse_float("2.5", min_value=0.0, max_value=1.0)
        1.0
    """
    try:
        result = float(value)
    except (ValueError, TypeError):
        return default

    # Apply min/max constraints
    if min_value is not None and result < min_value:
        logger.warning(f"Value {result} below minimum {min_value}, using minimum")
        return min_value

    if max_value is not None and result > max_value:
        logger.warning(f"Value {result} above maximum {max_value}, using maximum")
        return max_value

    return result


def create_ssl_redis_config() -> Dict[str, Any]:
    """Create SSL configuration dictionary for Redis connections.

    Returns:
        Dictionary with SSL configuration for Redis

    Examples:
        >>> config = create_ssl_redis_config()
        >>> config['ssl_cert_reqs'] == ssl.CERT_NONE
        True
    """
    return {
        "ssl_cert_reqs": ssl.CERT_NONE,
        "ssl_ca_certs": None,
        "ssl_certfile": None,
        "ssl_keyfile": None,
    }


def get_redis_ssl_connection_kwargs() -> Dict[str, Any]:
    """Get Redis SSL connection pool kwargs.

    Returns:
        Dictionary with connection class and SSL parameters for Redis

    Examples:
        >>> kwargs = get_redis_ssl_connection_kwargs()
        >>> 'connection_class' in kwargs
        True
    """
    try:
        import redis.connection

        return {
            "connection_class": redis.connection.SSLConnection,
            **create_ssl_redis_config(),
        }
    except ImportError:
        logger.warning(
            "Redis library not available, cannot create SSL connection kwargs"
        )
        return {}


def validate_postgres_connection_string(
    conn_str: str, require_ssl: bool = True
) -> tuple[bool, str]:
    """Validate PostgreSQL connection string format.

    Args:
        conn_str: PostgreSQL connection string
        require_ssl: Whether to require SSL mode parameter

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_postgres_connection_string("postgresql://user:pass@host:5432/db?sslmode=require")
        (True, "")

        >>> validate_postgres_connection_string("postgresql://localhost/db", require_ssl=True)
        (False, "Missing SSL mode parameter")
    """
    if is_empty_or_whitespace(conn_str):
        return False, "Connection string is empty"

    # Validate basic URL format
    is_valid, error = validate_url_format(
        conn_str, allowed_schemes=["postgresql", "postgres", "psql"]
    )
    if not is_valid:
        return False, error

    # Check for SSL mode in production
    if require_ssl and "sslmode=" not in conn_str:
        return False, "Missing SSL mode parameter (recommended: ?sslmode=require)"

    return True, ""


def validate_redis_connection_string(
    conn_str: str, warn_non_ssl: bool = True
) -> tuple[bool, str]:
    """Validate Redis connection string format.

    Args:
        conn_str: Redis connection string
        warn_non_ssl: Whether to warn about non-SSL connections

    Returns:
        Tuple of (is_valid, warning_message)

    Examples:
        >>> validate_redis_connection_string("rediss://host:6379/0")
        (True, "")

        >>> validate_redis_connection_string("redis://host:6379/0", warn_non_ssl=True)
        (True, "Using non-SSL Redis connection")
    """
    if is_empty_or_whitespace(conn_str):
        return False, "Connection string is empty"

    # Validate basic URL format
    is_valid, error = validate_url_format(conn_str, allowed_schemes=["redis", "rediss"])
    if not is_valid:
        return False, error

    # Check for SSL
    is_ssl = conn_str.startswith("rediss://")
    if warn_non_ssl and not is_ssl:
        return True, "Using non-SSL Redis connection (consider using rediss://)"

    return True, ""


def merge_dict_settings(*dicts: Dict[str, Any]) -> Dict[str, Any]:
    """Merge multiple dictionaries, with later dicts overriding earlier ones.

    Args:
        *dicts: Variable number of dictionaries to merge

    Returns:
        Merged dictionary

    Examples:
        >>> merge_dict_settings({'a': 1, 'b': 2}, {'b': 3, 'c': 4})
        {'a': 1, 'b': 3, 'c': 4}
    """
    result = {}
    for d in dicts:
        if isinstance(d, dict):
            result.update(d)
    return result


def sanitize_secret_for_logging(value: str, reveal_chars: int = 4) -> str:
    """Sanitize secret values for safe logging.

    Args:
        value: Secret value to sanitize
        reveal_chars: Number of characters to reveal at start and end

    Returns:
        Sanitized string safe for logging

    Examples:
        >>> sanitize_secret_for_logging("my_secret_key_1234567890")
        'my_s...7890'

        >>> sanitize_secret_for_logging("short")
        '****'
    """
    if is_empty_or_whitespace(value):
        return "****"

    if len(value) <= reveal_chars * 2:
        return "****"

    return f"{value[:reveal_chars]}...{value[-reveal_chars:]}"


def format_bytes(bytes_count: int | float) -> str:
    """Format byte count as human-readable string.

    Args:
        bytes_count: Number of bytes

    Returns:
        Human-readable string (e.g., "1.5 MB")

    Examples:
        >>> format_bytes(1024)
        '1.0 KB'

        >>> format_bytes(1536)
        '1.5 KB'

        >>> format_bytes(1048576)
        '1.0 MB'
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} PB"
