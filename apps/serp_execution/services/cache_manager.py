"""
Enhanced cache management facade for serp_execution slice.
Provides backward compatibility while using the consolidated core cache manager.
"""

import logging

from apps.core.services.cache_manager import RedisCacheManager

logger = logging.getLogger(__name__)


class CacheManager(RedisCacheManager):
    """Enhanced cache manager extending core functionality with SERP-specific features."""

    # Legacy cache settings for backward compatibility
    PREFIX_SEARCH = "serp_cache"  # Match core implementation
    DEFAULT_TTL = 3600  # 1 hour

    def __init__(self):
        """Initialize enhanced cache manager using core implementation."""
        super().__init__()

        # Legacy compatibility attributes
        self.enabled = self.config.get("enabled", True)
        self.ttl = self.default_ttl

    def _generate_cache_key(self, query_params: dict) -> str:
        """Legacy compatibility wrapper for cache key generation."""
        return self._generate_key(query_params)

    def get_search_results(self, query_params: dict):
        """Legacy compatibility wrapper for getting cached search results."""
        return super().get_search_results(query_params)

    def set_search_results(self, query_params: dict, results: dict) -> bool:
        """Legacy compatibility wrapper for caching search results."""
        return super().set_search_results(query_params, results)

    def invalidate_search_results(self, query_params: dict) -> bool:
        """Invalidate cached results for specific query."""
        if not self.enabled:
            return False

        try:
            cache_key = self._generate_cache_key(query_params)
            from django.core.cache import cache

            cache.delete(cache_key)
            return True
        except (ConnectionError, TimeoutError, OSError):
            logger.debug("Cache delete failed for %s", cache_key, exc_info=True)
            return False
