"""Configuration builders for Django settings.

This module provides reusable configuration builders to eliminate duplicate
configuration code across production, staging, and local settings files.

Created: 2025-10-17
Purpose: Phase 2 of Post-Deployment Refactoring Plan
"""

import importlib.util
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class CacheConfigBuilder:
    """Build cache configuration for different environments.

    Eliminates 4 identical database cache configurations by providing
    a single source of truth for cache fallback patterns.
    """

    # Define once, reuse everywhere
    SAFE_DATABASE_CACHE = {
        "BACKEND": "apps.core.backends.safe_cache.SafeDatabaseCache",
        "LOCATION": "cache_table",
        "OPTIONS": {
            "MAX_ENTRIES": 2000,
            "CULL_FREQUENCY": 3,
            "CONNECTION_THRESHOLD": 18,
            "CONNECTION_THRESHOLD_PGBOUNCER": 80,
        },
    }

    # Standard database cache without SafeCache wrapper
    STANDARD_DATABASE_CACHE = {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_table",
        "OPTIONS": {
            "MAX_ENTRIES": 1000,
            "CULL_FREQUENCY": 3,
        },
    }

    @classmethod
    def build(cls, environment: str, skip_redis: bool = False) -> Dict[str, Any]:
        """Build cache configuration for environment.

        Args:
            environment: Environment name ('production', 'staging', 'local', 'test')
            skip_redis: Force database cache (useful during build phase)

        Returns:
            CACHES dictionary for Django settings
        """
        if environment == "test":
            return cls._build_test_cache()

        if skip_redis or not cls._redis_available():
            if not skip_redis:
                logger.info(
                    f"Redis libraries not available for {environment}, using database cache"
                )
            else:
                logger.info(
                    f"Redis configuration skipped for {environment} (SKIP_REDIS_CONFIG=true)"
                )

            # Use SafeCache for production, standard for others
            if environment == "production":
                return {"default": cls.SAFE_DATABASE_CACHE}
            else:
                return {"default": cls.STANDARD_DATABASE_CACHE}

        # Try to use Redis configuration
        try:
            from apps.core.redis_config import get_cache_config

            cache_config = get_cache_config()

            # Validate cache config structure
            if not isinstance(cache_config, dict) or "default" not in cache_config:
                logger.warning(
                    "Invalid cache config structure, falling back to database cache"
                )
                return {
                    "default": cls.SAFE_DATABASE_CACHE
                    if environment == "production"
                    else cls.STANDARD_DATABASE_CACHE
                }

            logger.info(f"Using Redis cache configuration for {environment}")
            return cache_config

        except Exception as e:
            logger.warning(
                f"Redis config failed for {environment}, falling back to database cache: {e}"
            )
            return {
                "default": cls.SAFE_DATABASE_CACHE
                if environment == "production"
                else cls.STANDARD_DATABASE_CACHE
            }

    @staticmethod
    def _redis_available() -> bool:
        """Check if Redis libraries are available.

        Returns:
            True if both redis and django_redis are importable
        """
        return bool(
            importlib.util.find_spec("redis")
            and importlib.util.find_spec("django_redis")
        )

    @staticmethod
    def _build_test_cache() -> Dict[str, Any]:
        """Build cache config for test environment.

        Uses in-memory cache for fast test execution.

        Returns:
            Test cache configuration
        """
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "test-cache",
            }
        }
