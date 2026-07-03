"""
Django SECRET_KEY generator utility.

Provides functions to generate secure SECRET_KEY values that meet
production requirements (minimum 32 characters).
"""

import secrets
import string
from typing import Optional


def generate_secret_key(length: int = 50) -> str:
    """
    Generate a secure Django SECRET_KEY.

    Args:
        length: Key length (default 50, minimum 32 for production)

    Returns:
        A cryptographically secure random string suitable for Django SECRET_KEY

    Example:
        >>> key = generate_secret_key()
        >>> len(key)
        50
        >>> key = generate_secret_key(64)
        >>> len(key)
        64
    """
    if length < 32:
        raise ValueError("SECRET_KEY must be at least 32 characters for production")

    # Use Django-safe characters (avoid quotes and backslashes)
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"

    # Generate cryptographically secure random key
    return "".join(secrets.choice(chars) for _ in range(length))


def get_or_generate_secret_key(
    existing_key: Optional[str] = None, min_length: int = 32
) -> str:
    """
    Return existing key if valid, otherwise generate a new one.

    Args:
        existing_key: Current SECRET_KEY value (if any)
        min_length: Minimum required length (default 32)

    Returns:
        Valid SECRET_KEY (existing if valid, new if not)

    Example:
        >>> key = get_or_generate_secret_key("short")
        >>> len(key) >= 32
        True
        >>> key = get_or_generate_secret_key("this-is-a-very-long-existing-key-that-meets-requirements")
        >>> key
        'this-is-a-very-long-existing-key-that-meets-requirements'
    """
    if existing_key and len(existing_key) >= min_length:
        return existing_key

    # Generate new key with some extra length for safety
    return generate_secret_key(max(50, min_length + 10))


def validate_secret_key(key: str, min_length: int = 32) -> tuple[bool, str]:
    """
    Validate a SECRET_KEY meets production requirements.

    Args:
        key: The SECRET_KEY to validate
        min_length: Minimum required length (default 32)

    Returns:
        Tuple of (is_valid, error_message)

    Example:
        >>> validate_secret_key("short-key")
        (False, 'SECRET_KEY must be at least 32 characters (current: 9)')
        >>> validate_secret_key("a" * 50)
        (True, '')
    """
    if not key:
        return False, "SECRET_KEY is not set"

    if len(key) < min_length:
        return (
            False,
            f"SECRET_KEY must be at least {min_length} characters (current: {len(key)})",
        )

    # Check for obviously insecure values
    insecure_patterns = [
        "django-insecure",
        "change-this",
        "your-secret-key",
        "placeholder",
        "example",
        "test-key",
    ]

    key_lower = key.lower()
    for pattern in insecure_patterns:
        if pattern in key_lower:
            return False, f"SECRET_KEY contains insecure pattern: '{pattern}'"

    return True, ""


if __name__ == "__main__":
    # Command-line utility
    import argparse

    parser = argparse.ArgumentParser(description="Generate secure Django SECRET_KEY")
    parser.add_argument(
        "--length", type=int, default=50, help="Key length (default: 50, minimum: 32)"
    )
    parser.add_argument("--validate", type=str, help="Validate an existing SECRET_KEY")

    args = parser.parse_args()

    if args.validate:
        is_valid, error = validate_secret_key(args.validate)
        if is_valid:
            print(f"✅ SECRET_KEY is valid ({len(args.validate)} characters)")
        else:
            print(f"❌ SECRET_KEY is invalid: {error}")
    else:
        try:
            key = generate_secret_key(args.length)
            print(f"Generated SECRET_KEY ({len(key)} characters):")
            print(key)
            print("\nAdd this to your .env file as:")
            print(f"SECRET_KEY={key}")
        except ValueError as e:
            print(f"Error: {e}")
