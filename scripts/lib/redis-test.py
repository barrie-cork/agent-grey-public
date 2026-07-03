#!/usr/bin/env python3
"""Unified Redis connection test for startup scripts.

This script consolidates the 95% duplicate Redis connection testing code
from celery_startup.sh and celery_beat_startup.sh into a single reusable
utility.

Supports:
- SSL Redis (rediss://) for DigitalOcean Managed Redis
- Non-SSL Redis (redis://) for local development
- Configurable timeouts
- Proper error reporting

Exit codes:
- 0: Redis connection successful
- 1: Redis connection failed or error
"""

import os
import sys
from urllib.parse import urlparse


def test_redis_connection(broker_url=None, timeout=5):
    """
    Test Redis connection with SSL support.

    Args:
        broker_url: Redis connection URL (defaults to CELERY_BROKER_URL env var)
        timeout: Connection timeout in seconds

    Returns:
        bool: True if connection successful, False otherwise
    """
    broker_url = broker_url or os.environ.get("CELERY_BROKER_URL", "")

    if not broker_url or not broker_url.strip():
        print("✗ CELERY_BROKER_URL not set or empty")
        return False

    try:
        import redis
    except ImportError:
        print("✗ redis library not installed")
        return False

    parsed = urlparse(broker_url)

    if not parsed.hostname:
        print(f"✗ Invalid Redis URL: {broker_url}")
        return False

    try:
        # Determine if SSL is required
        use_ssl = broker_url.startswith("rediss://")

        if use_ssl:
            # DigitalOcean Managed Redis with SSL
            # Use default port 25061 for DigitalOcean
            port = parsed.port or 25061

            r = redis.Redis(
                host=parsed.hostname,
                port=port,
                password=parsed.password,
                ssl=True,
                ssl_cert_reqs="none",
                decode_responses=True,
                socket_timeout=timeout,
                socket_connect_timeout=timeout,
            )
        else:
            # Local Redis without SSL
            port = parsed.port or 6379

            r = redis.Redis(
                host=parsed.hostname,
                port=port,
                password=parsed.password,
                decode_responses=True,
                socket_timeout=timeout,
                socket_connect_timeout=timeout,
            )

        # Test connection with ping
        r.ping()
        print(f"✓ Redis connection OK ({parsed.hostname}:{port})")

        # Test read/write
        test_key = "redis_test_key"
        test_value = "test_value"
        r.set(test_key, test_value, ex=10)
        value = r.get(test_key)

        if value == test_value:
            print("✓ Redis read/write test OK")
            return True
        else:
            print(f"✗ Redis read/write test failed (expected '{test_value}', got '{value}')")
            return False

    except redis.exceptions.ConnectionError as e:
        print(f"✗ Redis connection failed: {e}")
        return False
    except redis.exceptions.TimeoutError as e:
        print(f"✗ Redis connection timeout: {e}")
        return False
    except redis.exceptions.AuthenticationError as e:
        print(f"✗ Redis authentication failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Redis test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point for standalone script execution."""
    # Support optional timeout argument
    timeout = 5
    if len(sys.argv) > 1:
        try:
            timeout = int(sys.argv[1])
        except ValueError:
            print(f"Warning: Invalid timeout '{sys.argv[1]}', using default: 5 seconds")
            timeout = 5

    success = test_redis_connection(timeout=timeout)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
