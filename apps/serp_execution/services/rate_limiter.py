"""
Global rate limiter facade for serp_execution slice.
Provides backward compatibility while using the consolidated core rate limiter.
"""

import logging

from constance import config

from apps.core.services.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


class GlobalRateLimiter(TokenBucketRateLimiter):
    """
    Enhanced rate limiter extending the core implementation with legacy compatibility.

    Maintains backward compatibility while leveraging the consolidated core rate limiter.
    """

    def __init__(self, key_prefix: str = "rate_limit") -> None:
        """Initialize with legacy compatibility."""
        # TokenBucketRateLimiter doesn't take key_prefix, so we'll set it after
        super().__init__()
        self.key_prefix = key_prefix  # Store for backward compatibility
        logger.info("Initialized GlobalRateLimiter using core implementation")

    def is_allowed(self, identifier: str, rate=None, burst=None):
        """
        Legacy compatibility method for checking rate limits.

        Args:
            identifier: Unique identifier for rate limiting (e.g., 'serper_api')
            rate: Requests per minute (default from config)
            burst: Burst capacity (default from config)

        Returns:
            tuple: (allowed: bool, wait_time_or_remaining: float)
        """
        # Scope the identifier with key_prefix for per-provider isolation
        scoped_id = f"{self.key_prefix}:{identifier}"
        allowed = self.can_proceed(scoped_id)

        if allowed:
            # Return success with remaining tokens (approximation)
            return True, float(config.API_RATE_LIMIT_BURST - 1)
        else:
            # Return delay time
            delay = self.get_retry_delay()
            return False, float(delay)

    def wait_if_needed(self, identifier: str, max_wait: float = 30.0) -> bool:
        """
        Legacy compatibility method for waiting when rate limited.

        Args:
            identifier: Rate limit identifier
            max_wait: Maximum seconds to wait

        Returns:
            True if request can proceed, False if wait exceeded max
        """
        allowed, wait_time = self.is_allowed(identifier)

        if allowed:
            return True

        if wait_time > max_wait:
            logger.error(f"Rate limit wait time {wait_time}s exceeds max {max_wait}s")
            return False

        logger.info(f"Rate limited, waiting {wait_time:.2f} seconds")
        import time

        time.sleep(wait_time)

        # Try again after waiting
        allowed, _ = self.is_allowed(identifier)
        return allowed

    def get_status(self, identifier: str):
        """
        Legacy compatibility method for getting rate limiter status.

        Returns:
            dict: Dictionary with status information
        """
        # Simplified status using core implementation concepts
        try:
            allowed, remaining_or_delay = self.is_allowed(identifier)

            return {
                "tokens": remaining_or_delay if allowed else 0,
                "rate_limit": config.API_RATE_LIMIT_PER_MINUTE,
                "status": "active" if allowed else "limited",
            }
        except Exception as e:
            logger.error(f"Error getting rate limiter status: {e}")
            return {"error": str(e)}

    def reset(self, identifier: str) -> None:
        """
        Legacy compatibility method for resetting rate limiter.

        Args:
            identifier: Rate limit identifier
        """
        # Note: Core implementation doesn't expose reset method
        # This is mainly for testing compatibility
        logger.info(
            f"Rate limiter reset requested for {identifier} (core implementation)"
        )


# Global instance with lazy initialization
rate_limiter = None


def get_rate_limiter():
    """
    Get the global rate limiter instance with lazy initialization.
    This prevents Redis connection attempts during Django startup/build time.

    Returns:
        GlobalRateLimiter or MockRateLimiter: Rate limiter instance
    """
    global rate_limiter
    if rate_limiter is None:
        try:
            # Check if we should skip Redis configuration (during build)
            import os

            skip_redis = os.environ.get("SKIP_REDIS_CONFIG", "false").lower() in (
                "true",
                "1",
                "yes",
            )

            if skip_redis:
                # During build time, return a mock rate limiter that always allows
                rate_limiter = MockRateLimiter()
            else:
                rate_limiter = GlobalRateLimiter()
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to initialize rate limiter: {e}, using mock")
            rate_limiter = MockRateLimiter()

    return rate_limiter


class MockRateLimiter:
    """
    Mock rate limiter for build-time or when Redis is unavailable.
    Always allows requests and logs warnings.
    """

    def __init__(self) -> None:
        logger.info("Using mock rate limiter (Redis unavailable)")

    def is_allowed(self, identifier: str, rate=None, burst=None):
        """Always allow requests in mock mode.

        Returns:
            tuple: (True, 0.0) - always allows with no wait time
        """
        return True, 0.0

    def wait_if_needed(self, identifier: str, max_wait: float = 30.0) -> bool:
        """Never wait in mock mode."""
        return True

    def get_status(self, identifier: str):
        """Return mock status.

        Returns:
            dict: Mock status dictionary with tokens, rate_limit, status
        """
        return {"tokens": 100, "rate_limit": 100, "status": "mock"}

    def reset(self, identifier: str) -> None:
        """No-op in mock mode."""
        pass

    def can_proceed(self, user_id: str = "global") -> bool:
        """Mock implementation of core interface."""
        return True

    def get_retry_delay(self) -> int:
        """Mock implementation of core interface."""
        return 0


# Per-provider rate limiter cache
_provider_rate_limiters: dict[str, GlobalRateLimiter | MockRateLimiter] = {}


def get_rate_limiter_for_provider(
    provider_key: str,
) -> GlobalRateLimiter | MockRateLimiter:
    """Get a rate limiter scoped to a specific SERP provider.

    Each provider gets its own rate limiter with an isolated key prefix,
    so different providers have independent rate limit buckets in Redis.

    Args:
        provider_key: Provider key (e.g. 'serper', 'serpapi').

    Returns:
        Rate limiter instance scoped to the provider.
    """
    if provider_key not in _provider_rate_limiters:
        base = get_rate_limiter()
        if isinstance(base, MockRateLimiter):
            _provider_rate_limiters[provider_key] = base
        else:
            _provider_rate_limiters[provider_key] = GlobalRateLimiter(
                key_prefix=f"rate_limit:{provider_key}"
            )
    return _provider_rate_limiters[provider_key]
