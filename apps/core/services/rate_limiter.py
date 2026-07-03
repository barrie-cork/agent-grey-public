"""
Token Bucket Rate Limiter Service

Token bucket rate limiter using Redis for distributed coordination.
Implements 15 requests per minute limit with 20 burst capacity for Serper API.
"""

import logging
import time
from typing import TypedDict

from django.conf import settings

from apps.core.utils.redis_utils import get_safe_redis_connection

from .base import BaseService

logger = logging.getLogger(__name__)


class RateLimiterConfig(TypedDict):
    key_prefix: str
    rate: int
    burst: int
    period: int
    cache_timeout: int


class TokenBucketRateLimiter(BaseService[RateLimiterConfig]):
    """
    Token bucket rate limiter using Redis for distributed coordination.
    Implements 15 requests per minute limit with 20 burst capacity for Serper API.
    """

    SERVICE_NAME = "TokenBucketRateLimiter"
    SERVICE_VERSION = "2.0.0"

    def get_default_config(self) -> RateLimiterConfig:
        """Get default rate limiter configuration."""
        return {
            "key_prefix": "rate_limit",
            "rate": getattr(settings, "SERPER_RATE_LIMIT", 50),  # from settings
            "burst": getattr(settings, "SERPER_RATE_BURST", 60),  # from settings
            "period": getattr(settings, "SERPER_RATE_PERIOD", 60),  # from settings
            "cache_timeout": 300,
        }

    def _initialize(self) -> None:
        """Initialize Redis connection and Lua script."""
        self.redis = get_safe_redis_connection("default")

        # Lua script for atomic token bucket operations
        self.lua_script = """
        local key = KEYS[1]
        local rate = tonumber(ARGV[1])
        local burst = tonumber(ARGV[2])
        local period = tonumber(ARGV[3])
        local current_time = tonumber(ARGV[4])

        local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(bucket[1]) or burst
        local last_refill = tonumber(bucket[2]) or current_time

        local elapsed = current_time - last_refill
        local tokens_to_add = elapsed * (rate / period)
        tokens = math.min(burst, tokens + tokens_to_add)

        if tokens >= 1 then
            tokens = tokens - 1
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', current_time)
            redis.call('EXPIRE', key, period * 2)
            return 1
        else
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', current_time)
            redis.call('EXPIRE', key, period * 2)
            return 0
        end
        """

    def health_check(self) -> bool:
        """Check if rate limiter is healthy and Redis is available."""
        try:
            if not self.redis:
                return False

            # Test Redis connection with a simple ping
            self.redis.ping()
            return True

        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def can_proceed(self, user_id: str = "global") -> bool:
        """
        Check if request can proceed under rate limiting.

        Args:
            user_id: User identifier for per-user limiting

        Returns:
            True if request can proceed, False if rate limited
        """
        with self._measure_performance("can_proceed"):
            if not self.redis:
                # Fallback: allow request if Redis unavailable
                self.logger.warning("Redis unavailable, bypassing rate limiting")
                return True

            try:
                key = f"{self.config['key_prefix']}:{user_id}"
                current_time = time.time()

                # Try Lua script first (optimal path)
                try:
                    result = self.redis.eval(
                        self.lua_script,
                        1,
                        key,
                        self.config["rate"],
                        self.config["burst"],
                        self.config["period"],
                        current_time,
                    )

                    if result is None:
                        self.logger.debug(
                            "Redis eval returned None (likely fallback mode); using simple rate limit check"
                        )
                        return self._simple_rate_limit_check(user_id, current_time)

                    allowed = bool(result)
                    if not allowed:
                        self.logger.debug(f"Rate limit exceeded for user {user_id}")

                    return allowed

                except Exception as lua_error:
                    # Lua script failed (likely cache fallback mode)
                    self.logger.warning(
                        f"Lua script rate limiting failed, using fallback method: {lua_error}"
                    )
                    return self._simple_rate_limit_check(user_id, current_time)

            except Exception as e:
                self._handle_error(e, {"user_id": user_id}, "can_proceed")
                return True  # Fail open for reliability

    def _simple_rate_limit_check(self, user_id: str, current_time: float) -> bool:
        """
        Simple rate limiting fallback when Lua scripts are not available.
        Uses Django cache framework with fixed window approach.

        Args:
            user_id: User identifier
            current_time: Current timestamp

        Returns:
            True if request can proceed, False if rate limited
        """
        try:
            # Use Django cache framework instead of direct Redis
            from django.core.cache import cache

            window_key = f"{self.config['key_prefix']}:{user_id}:simple"
            window_start_key = f"{self.config['key_prefix']}:{user_id}:simple:start"

            # Get window start time
            window_start = cache.get(window_start_key)

            # Initialize new window if none exists
            if window_start is None:
                cache.set(window_start_key, current_time, timeout=self.config["period"])
                cache.set(window_key, 1, timeout=self.config["period"])
                self.logger.debug(
                    f"Rate limit check passed (new window): 1/{self.config['rate']} for user {user_id}"
                )
                return True

            # Check if window has expired
            if current_time - window_start >= self.config["period"]:
                # Reset window
                cache.set(window_start_key, current_time, timeout=self.config["period"])
                cache.set(window_key, 1, timeout=self.config["period"])
                self.logger.debug(
                    f"Rate limit check passed (window reset): 1/{self.config['rate']} for user {user_id}"
                )
                return True

            # Get current request count in the window
            current_count = cache.get(window_key, 0)
            window_age = current_time - window_start

            # Check if we're under the rate limit
            if current_count < self.config["rate"]:
                # Increment counter using incr to avoid race conditions
                try:
                    new_count = cache.incr(window_key)
                except ValueError:
                    # Key doesn't exist, set it
                    cache.set(
                        window_key, current_count + 1, timeout=self.config["period"]
                    )
                    new_count = current_count + 1

                self.logger.debug(
                    f"Rate limit check passed: {new_count}/{self.config['rate']} for user {user_id} "
                    f"(window age: {window_age:.1f}s/{self.config['period']}s)"
                )
                return True
            else:
                time_until_reset = self.config["period"] - window_age
                self.logger.warning(
                    f"Rate limit exceeded: {current_count}/{self.config['rate']} for user {user_id}. "
                    f"Window resets in {time_until_reset:.1f}s"
                )
                return False

        except Exception as e:
            self.logger.warning(
                f"Simple rate limit check failed: {e}, allowing request"
            )
            return True  # Fail open

    def get_retry_delay(self) -> int:
        """Get recommended delay before retry."""
        return 60  # 1 minute delay for rate limited requests
