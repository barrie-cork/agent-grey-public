"""
Cache initialization helper for Celery and Channels compatibility.

This module ensures proper cache initialization in async contexts.
"""

import logging
from typing import Optional

from django.core.cache.backends.base import BaseCache

logger = logging.getLogger(__name__)


def _ensure_django_setup():
    """
    Ensure Django is fully set up before cache operations.

    Raises:
        Exception: If Django setup fails
    """
    import django

    try:
        from django.apps import apps

        if not apps.ready:
            django.setup()
    except Exception:
        # If apps is not available, try to setup Django anyway
        django.setup()


def _test_cache_backend(cache: BaseCache) -> bool:
    """
    Test if cache backend is functional by performing test operations.

    Args:
        cache: Cache backend to test

    Returns:
        True if cache is operational, False otherwise
    """
    try:
        cache.set("__init_test__", 1, 1)
        cache.delete("__init_test__")
        return True
    except Exception as e:
        logger.debug(f"Cache test failed: {e}")
        return False


def _initialize_redis_cache() -> Optional[BaseCache]:
    """
    Attempt to initialize Redis cache backend.

    Returns:
        Redis cache backend if successful, None otherwise
    """
    from django.core.cache import caches

    try:
        cache = caches["default"]
        if _test_cache_backend(cache):
            logger.info("Redis cache initialized successfully")
            return cache
        else:
            logger.warning("Redis initialization failed, falling back to database")
            return None
    except Exception as e:
        logger.warning(f"Redis initialization failed, falling back to database: {e}")
        return None


def _initialize_database_cache() -> Optional[BaseCache]:
    """
    Attempt to initialize database cache backend.

    Returns:
        Database cache backend if successful, None otherwise
    """
    from django.core.cache import caches

    try:
        cache = caches["default"]
        if _test_cache_backend(cache):
            logger.info("Database cache initialized successfully")
            return cache
        else:
            logger.error(
                "Database cache initialization failed. "
                "This usually means settings.DATABASES is not properly configured."
            )
            return None
    except Exception as e:
        logger.error(
            f"Database cache initialization failed: {e}. "
            "This usually means settings.DATABASES is not properly configured."
        )
        return None


def force_cache_initialization() -> Optional[BaseCache]:
    """
    Force cache backend initialization for Celery workers.

    This function explicitly initializes the cache backend to avoid
    ConnectionProxy lazy-loading issues in Celery/Channels contexts.

    Returns:
        Initialized cache backend or None if initialization fails
    """
    try:
        _ensure_django_setup()

        from django.conf import settings

        cache_config = settings.CACHES.get("default", {})
        backend = cache_config.get("BACKEND", "").lower()

        # Try Redis first if configured
        if "redis" in backend:
            cache = _initialize_redis_cache()
            if cache:
                return cache

        # Fallback to database cache
        return _initialize_database_cache()

    except Exception as e:
        logger.error(f"Cache initialization failed completely: {e}")
        return None


# Global cache instance for Celery workers
_worker_cache = None


def get_worker_cache() -> Optional[BaseCache]:
    """
    Get or create a cache instance for Celery workers.

    This maintains a single cache instance per worker process.

    Returns:
        Cache backend instance or None
    """
    global _worker_cache

    if _worker_cache is None:
        _worker_cache = force_cache_initialization()

    return _worker_cache
