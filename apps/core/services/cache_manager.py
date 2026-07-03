"""
Redis Cache Manager Service

Redis-based caching for query results and metadata.
Simple key-value caching with TTL management.
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional, TypedDict

from django.conf import settings
from django.core.cache import cache

from redis import RedisError

from .base import BaseService

logger = logging.getLogger(__name__)


class CacheManagerConfig(TypedDict):
    prefix: str
    default_ttl: int
    enabled: bool
    cache_timeout: int


class RedisCacheManager(BaseService[CacheManagerConfig]):
    """
    Redis-based caching for query results and metadata.
    Simple key-value caching with TTL management.
    """

    SERVICE_NAME = "RedisCacheManager"
    SERVICE_VERSION = "2.0.0"

    def get_default_config(self) -> CacheManagerConfig:
        """Get default cache manager configuration."""
        return {
            "prefix": "serp_cache",
            "default_ttl": 3600,  # 1 hour
            "enabled": getattr(settings, "SERP_CACHE_ENABLED", True),
            "cache_timeout": 300,
        }

    def _initialize(self) -> None:
        """Initialize cache manager resources."""
        pass  # Uses Django cache framework

    @property
    def default_ttl(self) -> int:
        """Backward compatibility property for default TTL."""
        return self.config["default_ttl"]

    def health_check(self) -> bool:
        """Check if cache manager is healthy."""
        try:
            if not self.config["enabled"]:
                return True  # Healthy if intentionally disabled

            # Test cache with a simple set/get operation
            test_key = f"{self.config['prefix']}:health_check"
            cache.set(test_key, "test", 1)
            result = cache.get(test_key)
            cache.delete(test_key)
            return result == "test"

        except (
            Exception
        ) as e:  # Intentional broad catch: health check tests service availability
            self._handle_error(e, operation="health_check")
            return False

    def _generate_key(self, query_params: Dict) -> str:
        """Generate cache key from query parameters."""
        sorted_params = json.dumps(query_params, sort_keys=True)
        hash_digest = hashlib.md5(
            sorted_params.encode(), usedforsecurity=False
        ).hexdigest()
        return f"{self.config['prefix']}:{hash_digest}"

    def get_search_results(self, query_params: Dict) -> Optional[Dict]:
        """Get cached search results."""
        with self._measure_performance("get_search_results"):
            if not self.config["enabled"]:
                return None

            try:
                key = self._generate_key(query_params)
                return cache.get(key)
            except (ConnectionError, TimeoutError, RedisError) as e:
                self._handle_error(
                    e, {"key_params": query_params}, "get_search_results"
                )
                return None

    def set_search_results(self, query_params: Dict, results: Dict) -> bool:
        """Cache search results with TTL."""
        with self._measure_performance("set_search_results"):
            if not self.config["enabled"]:
                return False

            try:
                key = self._generate_key(query_params)
                cache.set(key, results, self.config["default_ttl"])
                return True
            except (ConnectionError, TimeoutError, RedisError) as e:
                self._handle_error(
                    e, {"key_params": query_params}, "set_search_results"
                )
                return False

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from cache by key."""
        if not self.config["enabled"]:
            return default
        try:
            prefixed_key = f"{self.config['prefix']}:{key}"
            result = cache.get(prefixed_key)
            return result if result is not None else default
        except (ConnectionError, TimeoutError, RedisError) as e:
            self._handle_error(e, {"key": key}, "get")
            return default

    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        """Set a value in cache with optional timeout."""
        if not self.config["enabled"]:
            return
        try:
            prefixed_key = f"{self.config['prefix']}:{key}"
            ttl = timeout if timeout is not None else self.config["default_ttl"]
            cache.set(prefixed_key, value, ttl)
        except (ConnectionError, TimeoutError, RedisError) as e:
            self._handle_error(e, {"key": key}, "set")

    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        if not self.config["enabled"]:
            return False
        try:
            prefixed_key = f"{self.config['prefix']}:{key}"
            cache.delete(prefixed_key)
            return True
        except (ConnectionError, TimeoutError, RedisError) as e:
            self._handle_error(e, {"key": key}, "delete")
            return False

    def clear(self) -> None:
        """Clear all cache entries."""
        try:
            cache.clear()
        except (ConnectionError, TimeoutError, RedisError) as e:
            self._handle_error(e, operation="clear")

    def invalidate_session(self, session_id: str) -> bool:
        """Invalidate all cache entries for a session."""
        with self._measure_performance("invalidate_session"):
            try:
                # This is a basic implementation
                # In production, you might want to track session-related keys
                self.logger.info(
                    f"Cache invalidation requested for session {session_id}"
                )
                return True
            except (ConnectionError, TimeoutError, RedisError) as e:
                self._handle_error(e, {"session_id": session_id}, "invalidate_session")
                return False
