"""
Safe Redis connection utilities with fallback handling.

This module provides a centralized safe Redis connection wrapper that gracefully
handles Redis availability issues and provides consistent behavior across different
deployment environments.

Key Features:
- Drop-in replacement for get_redis_connection()
- Automatic fallback to Django cache when Redis unavailable
- Consistent API regardless of backend
- Connection pooling and error isolation
- Comprehensive logging for troubleshooting
"""

import logging
from typing import Any, Dict, Optional, Union

from django.core.cache import cache

logger = logging.getLogger(__name__)


class RedisConnectionError(Exception):
    """Raised when Redis connection cannot be established."""

    pass


class SafeRedisWrapper:
    """
    Safe Redis connection wrapper that falls back to Django cache.

    This wrapper provides Redis-like interface but uses Django's cache
    framework as fallback when Redis is not available.

    Features:
    - Same API as Redis client for drop-in replacement
    - Automatic backend detection and fallback
    - Connection reuse via singleton pattern
    - Transparent handling of bytes vs strings
    - Comprehensive error handling and logging
    """

    def __init__(self, connection_name: str = "default"):
        self.connection_name = connection_name
        self._redis_conn: Any = None
        self._use_fallback = False
        self._backend_type: str | None = None
        self._initialize_connection()

    def _initialize_connection(self):
        """Initialize Redis connection with fallback detection."""
        try:
            # First check if we should skip Redis (build time, etc.)
            import os

            if os.environ.get("SKIP_REDIS_CONFIG", "false").lower() in (
                "true",
                "1",
                "yes",
            ):
                logger.info(
                    "Skipping Redis connection (SKIP_REDIS_CONFIG=true), using cache fallback"
                )
                self._use_fallback = True
                self._backend_type = "build_skip"
                return

            # Check backend configuration to determine if Redis is available
            backend_info = self._get_cache_backend_info()

            if not backend_info["is_redis"]:
                logger.info(
                    f"Non-Redis backend detected ({backend_info['backend']}), using cache fallback"
                )
                self._use_fallback = True
                self._backend_type = backend_info["backend"]
                return

            # Try to establish Redis connection
            from django_redis import get_redis_connection

            self._redis_conn = get_redis_connection(self.connection_name)

            # Test the connection
            self._redis_conn.ping()
            logger.info(
                f"Redis connection '{self.connection_name}' established successfully"
            )
            self._backend_type = "redis"

        except ImportError:
            logger.warning("django_redis not available, using cache fallback")
            self._use_fallback = True
            self._backend_type = "django_redis_missing"
        except Exception as e:
            logger.warning(f"Redis connection failed, using Django cache fallback: {e}")
            self._use_fallback = True
            self._backend_type = f"redis_error_{type(e).__name__}"

    def _get_cache_backend_info(self) -> Dict[str, Any]:
        """Get information about current cache backend configuration."""
        try:
            from django.conf import settings

            cache_config = getattr(settings, "CACHES", {}).get("default", {})
            backend = cache_config.get("BACKEND", "")

            info = {
                "backend": backend,
                "is_redis": "redis" in backend.lower(),
                "is_dummy": "dummy" in backend.lower(),
                "is_db": "database" in backend.lower(),
                "is_memory": "memory" in backend.lower(),
                "location": cache_config.get("LOCATION", ""),
            }

            logger.debug(f"Cache backend info: {info}")
            return info

        except Exception as e:
            logger.error(f"Failed to get cache backend info: {e}")
            return {
                "backend": "unknown",
                "is_redis": False,
                "is_dummy": False,
                "is_db": False,
                "is_memory": False,
                "location": "",
            }

    def get(self, key: str) -> Optional[bytes]:
        """Get value from Redis or cache fallback."""
        try:
            if self._use_fallback:
                value = cache.get(key)
                # Django cache returns various types, Redis returns bytes
                if value is None:
                    return None
                elif isinstance(value, bytes):
                    return value
                else:
                    return str(value).encode("utf-8")
            else:
                return self._redis_conn.get(key)
        except Exception as e:
            logger.warning(f"Redis get failed for key '{key}': {e}")
            # Fallback to Django cache
            try:
                value = cache.get(key)
                if value is None:
                    return None
                elif isinstance(value, bytes):
                    return value
                else:
                    return str(value).encode("utf-8")
            except Exception as fallback_error:
                logger.error(f"Cache fallback also failed: {fallback_error}")
                return None

    def set(self, key: str, value: Union[str, bytes], ex: Optional[int] = None) -> bool:
        """Set value in Redis or cache fallback."""
        try:
            if self._use_fallback:
                timeout = ex if ex else 3600  # Default 1 hour
                cache.set(key, value, timeout)
                return True
            else:
                return self._redis_conn.set(key, value, ex=ex)
        except Exception as e:
            logger.warning(f"Redis set failed for key '{key}': {e}")
            # Fallback to Django cache
            try:
                timeout = ex if ex else 3600
                cache.set(key, value, timeout)
                return True
            except Exception as fallback_error:
                logger.error(f"Cache fallback also failed: {fallback_error}")
                return False

    def setex(self, key: str, timeout: int, value: Union[str, bytes]) -> bool:
        """Set value with expiration."""
        return self.set(key, value, ex=timeout)

    def delete(self, key: str) -> int:
        """Delete key from Redis or cache."""
        try:
            if self._use_fallback:
                cache.delete(key)
                return 1  # Assume success
            else:
                return self._redis_conn.delete(key)
        except Exception as e:
            logger.warning(f"Redis delete failed for key '{key}': {e}")
            try:
                cache.delete(key)
                return 1
            except Exception as fallback_error:
                logger.error(f"Cache fallback also failed: {fallback_error}")
                return 0

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            if self._use_fallback:
                return cache.get(key) is not None
            else:
                return bool(self._redis_conn.exists(key))
        except Exception as e:
            logger.warning(f"Redis exists check failed for key '{key}': {e}")
            try:
                return cache.get(key) is not None
            except Exception as fallback_error:
                logger.error(f"Cache fallback also failed: {fallback_error}")
                return False

    def ping(self) -> bool:
        """Test connection health."""
        try:
            if self._use_fallback:
                # Test Django cache
                test_key = "_redis_wrapper_health_check"
                cache.set(test_key, "ok", 1)
                return cache.get(test_key) == "ok"
            else:
                return self._redis_conn.ping()
        except Exception as e:
            logger.debug(f"Ping failed: {e}")
            return False

    def incr(self, key: str, amount: int = 1) -> int:
        """Increment counter."""
        try:
            if self._use_fallback:
                # Django cache doesn't have atomic increment in all backends
                # This is a race condition risk but better than failing
                current = cache.get(key, 0)
                try:
                    current_int = int(current)
                except (ValueError, TypeError):
                    current_int = 0
                new_value = current_int + amount
                cache.set(key, new_value, 3600)
                return new_value
            else:
                return self._redis_conn.incr(key, amount)
        except Exception as e:
            logger.warning(f"Redis incr failed for key '{key}': {e}")
            # Fallback increment
            try:
                current = cache.get(key, 0)
                try:
                    current_int = int(current)
                except (ValueError, TypeError):
                    current_int = 0
                new_value = current_int + amount
                cache.set(key, new_value, 3600)
                return new_value
            except Exception as fallback_error:
                logger.error(f"Cache fallback also failed: {fallback_error}")
                return amount  # Return the increment amount as best guess

    def expire(self, key: str, timeout: int) -> bool:
        """Set expiration on key."""
        try:
            if self._use_fallback:
                # For Django cache, we need to get and re-set with new timeout
                value = cache.get(key)
                if value is not None:
                    cache.set(key, value, timeout)
                    return True
                return False
            else:
                return bool(self._redis_conn.expire(key, timeout))
        except Exception as e:
            logger.warning(f"Redis expire failed for key '{key}': {e}")
            try:
                value = cache.get(key)
                if value is not None:
                    cache.set(key, value, timeout)
                    return True
                return False
            except Exception as fallback_error:
                logger.error(f"Cache fallback also failed: {fallback_error}")
                return False

    def scan_iter(self, match: str = "*", count: int = 1000):
        """Iterate over keys matching pattern."""
        try:
            if self._use_fallback:
                # Django cache doesn't support pattern scanning
                # This is a limitation of the fallback approach
                logger.warning(
                    f"Pattern scanning not supported in cache fallback mode: {match}"
                )
                return []
            else:
                return self._redis_conn.scan_iter(match=match, count=count)
        except Exception as e:
            logger.warning(f"Redis scan_iter failed for pattern '{match}': {e}")
            return []

    def hgetall(self, key: str) -> Dict[bytes, bytes]:
        """Get all hash fields and values."""
        try:
            if self._use_fallback:
                # Django cache doesn't support hash operations
                # Store as JSON-encoded dict
                value = cache.get(key)
                if isinstance(value, dict):
                    # Convert to bytes format like Redis
                    return {
                        k.encode("utf-8") if isinstance(k, str) else k: (
                            v.encode("utf-8") if isinstance(v, str) else v
                        )
                        for k, v in value.items()
                    }
                return {}
            else:
                return self._redis_conn.hgetall(key)
        except Exception as e:
            logger.warning(f"Redis hgetall failed for key '{key}': {e}")
            return {}

    def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        """Increment hash field by amount."""
        try:
            if self._use_fallback:
                # Django cache doesn't support hash operations
                # Simulate with JSON-encoded dict
                value = cache.get(key, {})
                if not isinstance(value, dict):
                    value = {}

                current = value.get(field, 0)
                try:
                    current_int = int(current)
                except (ValueError, TypeError):
                    current_int = 0

                new_value = current_int + amount
                value[field] = new_value
                cache.set(key, value, 3600)
                return new_value
            else:
                return self._redis_conn.hincrby(key, field, amount)
        except Exception as e:
            logger.warning(
                f"Redis hincrby failed for key '{key}', field '{field}': {e}"
            )
            return amount  # Return increment as best guess

    def hmget(self, key: str, *fields) -> list:
        """Get multiple hash fields."""
        try:
            if self._use_fallback:
                value = cache.get(key, {})
                if not isinstance(value, dict):
                    return [None] * len(fields)
                return [value.get(field) for field in fields]
            else:
                return self._redis_conn.hmget(key, *fields)
        except Exception as e:
            logger.warning(f"Redis hmget failed for key '{key}': {e}")
            return [None] * len(fields)

    def hmset(self, key: str, mapping: Dict) -> bool:
        """Set multiple hash fields."""
        try:
            if self._use_fallback:
                cache.set(key, mapping, 3600)
                return True
            else:
                return self._redis_conn.hmset(key, mapping)
        except Exception as e:
            logger.warning(f"Redis hmset failed for key '{key}': {e}")
            return False

    def lpush(self, key: str, *values) -> int:
        """Push values to left of list."""
        try:
            if self._use_fallback:
                # Django cache doesn't support list operations
                # Simulate with Python list
                current_list = cache.get(key, [])
                if not isinstance(current_list, list):
                    current_list = []

                # Add values to beginning
                for value in reversed(values):
                    current_list.insert(0, value)

                cache.set(key, current_list, 3600)
                return len(current_list)
            else:
                return self._redis_conn.lpush(key, *values)
        except Exception as e:
            logger.warning(f"Redis lpush failed for key '{key}': {e}")
            return 0

    def ltrim(self, key: str, start: int, end: int) -> bool:
        """Trim list to specified range."""
        try:
            if self._use_fallback:
                current_list = cache.get(key, [])
                if not isinstance(current_list, list):
                    current_list = []

                trimmed_list = current_list[start : end + 1]
                cache.set(key, trimmed_list, 3600)
                return True
            else:
                return self._redis_conn.ltrim(key, start, end)
        except Exception as e:
            logger.warning(f"Redis ltrim failed for key '{key}': {e}")
            return False

    def lrange(self, key: str, start: int, end: int) -> list:
        """Get list elements in range."""
        try:
            if self._use_fallback:
                current_list = cache.get(key, [])
                if not isinstance(current_list, list):
                    return []

                if end == -1:
                    return current_list[start:]
                else:
                    return current_list[start : end + 1]
            else:
                return self._redis_conn.lrange(key, start, end)
        except Exception as e:
            logger.warning(f"Redis lrange failed for key '{key}': {e}")
            return []

    def llen(self, key: str) -> int:
        """Get list length."""
        try:
            if self._use_fallback:
                current_list = cache.get(key, [])
                if isinstance(current_list, list):
                    return len(current_list)
                return 0
            else:
                return self._redis_conn.llen(key)
        except Exception as e:
            logger.warning(f"Redis llen failed for key '{key}': {e}")
            return 0

    @property
    def is_redis_available(self) -> bool:
        """Check if actual Redis connection is available."""
        return not self._use_fallback and self.ping()

    @property
    def backend_type(self) -> str:
        """Get the backend type being used."""
        return self._backend_type or "unknown"

    def register_script(self, script: str):
        """Register Lua script (Redis only)."""
        try:
            if self._use_fallback:
                logger.warning("Lua scripts not supported in cache fallback mode")
                return None
            else:
                return self._redis_conn.register_script(script)
        except Exception as e:
            logger.warning(f"Failed to register Lua script: {e}")
            return None

    def eval(self, script: str, numkeys: int, *keys_and_args):
        """Evaluate Lua script (Redis only)."""
        try:
            if self._use_fallback:
                logger.warning("Lua script eval not supported in cache fallback mode")
                return None
            else:
                return self._redis_conn.eval(script, numkeys, *keys_and_args)
        except Exception as e:
            logger.warning(f"Failed to eval Lua script: {e}")
            return None

    def get_info(self) -> Dict[str, Any]:
        """Get information about the connection."""
        return {
            "connection_name": self.connection_name,
            "is_redis_available": self.is_redis_available,
            "use_fallback": self._use_fallback,
            "backend_type": self.backend_type,
            "ping_success": self.ping(),
        }


# Global connection instances for reuse
_connections: Dict[str, SafeRedisWrapper] = {}


def get_safe_redis_connection(connection_name: str = "default") -> SafeRedisWrapper:
    """
    Get a safe Redis connection wrapper.

    This is a drop-in replacement for django_redis.get_redis_connection() that
    provides graceful fallback handling when Redis is not available.

    Args:
        connection_name: Redis connection name from settings

    Returns:
        SafeRedisWrapper instance with fallback handling

    Example:
        # Replace this:
        from django_redis import get_redis_connection
        redis = get_redis_connection('default')

        # With this:
        from apps.core.utils.redis_utils import get_safe_redis_connection
        redis = get_safe_redis_connection('default')

        # Same API, but with fallback handling
        redis.set('key', 'value', ex=300)
        value = redis.get('key')
    """
    if connection_name not in _connections:
        _connections[connection_name] = SafeRedisWrapper(connection_name)
    return _connections[connection_name]


def is_redis_available(connection_name: str = "default") -> bool:
    """
    Quick check if Redis is available.

    Args:
        connection_name: Redis connection name

    Returns:
        True if Redis is working, False if using fallback
    """
    conn = get_safe_redis_connection(connection_name)
    return conn.is_redis_available


def get_redis_info(connection_name: str = "default") -> Dict[str, Any]:
    """
    Get detailed information about Redis connection status.

    Args:
        connection_name: Redis connection name

    Returns:
        Dictionary with connection information
    """
    conn = get_safe_redis_connection(connection_name)
    return conn.get_info()


def clear_connection_cache():
    """
    Clear the connection cache.

    Useful for testing or when you want to force re-initialization
    of connections.
    """
    global _connections
    _connections.clear()
    logger.info("Redis connection cache cleared")
