"""
SafeDatabaseCache backend that monitors connection usage and gracefully degrades.

This cache backend extends Django's DatabaseCache to add connection monitoring
capabilities. It prevents cache operations from exhausting database connections
by checking connection usage before performing operations.
"""

import logging

from django.core.cache import caches
from django.core.cache.backends.db import DatabaseCache
from django.db import connections

logger = logging.getLogger(__name__)


class SafeDatabaseCache(DatabaseCache):
    """
    Database cache that refuses to work when connections are scarce.

    This prevents cache operations from exhausting our database connections
    when the system is under heavy load. It gracefully degrades by returning
    default values rather than failing.
    """

    def __init__(self, table, params):
        """Initialize SafeDatabaseCache with connection threshold."""
        super().__init__(table, params)
        # Safe threshold for db-s-2vcpu-4gb tier (22 usable connections)
        # With pgBouncer, this would be 80 out of 97 total
        self.connection_threshold = params.get("OPTIONS", {}).get(
            "CONNECTION_THRESHOLD", 18
        )
        self.connection_threshold_pgbouncer = params.get("OPTIONS", {}).get(
            "CONNECTION_THRESHOLD_PGBOUNCER", 80
        )

    def _check_connection_safety(self):
        """
        Check if it's safe to use database cache.

        Returns:
            tuple: (is_safe, active_connections, max_connections)
        """
        try:
            with connections["default"].cursor() as cursor:
                # Get current connection count
                cursor.execute(
                    """
                    SELECT count(*) as active,
                           current_setting('max_connections')::int as max_conn
                    FROM pg_stat_activity
                    WHERE state != 'idle'
                    AND pid != pg_backend_pid()
                """
                )
                result = cursor.fetchone()

                if result:
                    active_connections = result[0]
                    max_connections = result[1]

                    # Determine appropriate threshold based on max connections
                    # pgBouncer provides ~97 connections, direct provides ~22
                    if max_connections > 50:
                        # Using pgBouncer
                        threshold = self.connection_threshold_pgbouncer
                    else:
                        # Direct connection
                        threshold = self.connection_threshold

                    is_safe = active_connections < threshold

                    if not is_safe:
                        logger.warning(
                            f"Database cache skipped - high connection usage: "
                            f"{active_connections}/{max_connections} (threshold: {threshold})"
                        )

                    return is_safe, active_connections, max_connections

        except Exception as e:
            logger.error(f"Error checking database connections: {e}")
            # Err on the side of caution - skip cache if we can't check
            return False, 0, 0

        # Default to safe if we can't determine
        return True, 0, 0

    def get(self, key, default=None, version=None):
        """
        Get cache value with connection safety check.

        Args:
            key: Cache key
            default: Default value if not found or unsafe
            version: Cache key version

        Returns:
            Cached value or default
        """
        is_safe, active, max_conn = self._check_connection_safety()

        if not is_safe:
            return default

        try:
            return super().get(key, default, version)
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return default

    def set(self, key, value, timeout=None, version=None):
        """
        Set cache value with connection safety check.

        Args:
            key: Cache key
            value: Value to cache
            timeout: Cache timeout in seconds
            version: Cache key version
        """
        is_safe, active, max_conn = self._check_connection_safety()

        if not is_safe:
            # Silently skip cache set when connections are scarce
            return

        try:
            super().set(key, value, timeout, version)
        except Exception as e:
            logger.error(f"Cache set error: {e}")

    def delete(self, key, version=None):
        """
        Delete cache value with connection safety check.

        Args:
            key: Cache key to delete
            version: Cache key version
        """
        is_safe, active, max_conn = self._check_connection_safety()

        if not is_safe:
            # Skip delete when connections are scarce
            return

        try:
            super().delete(key, version)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")

    def clear(self):
        """
        Clear cache with connection safety check.

        This operation is expensive and should be avoided
        when connections are scarce.
        """
        is_safe, active, max_conn = self._check_connection_safety()

        if not is_safe:
            logger.warning("Cache clear skipped due to high connection usage")
            return

        try:
            super().clear()
        except Exception as e:
            logger.error(f"Cache clear error: {e}")

    def get_many(self, keys, version=None):
        """
        Get multiple cache values with connection safety check.

        Args:
            keys: List of cache keys
            version: Cache key version

        Returns:
            Dictionary of found cache entries
        """
        is_safe, active, max_conn = self._check_connection_safety()

        if not is_safe:
            # Return empty dict when unsafe
            return {}

        try:
            return super().get_many(keys, version)
        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            return {}

    def set_many(self, data, timeout=None, version=None):
        """
        Set multiple cache values with connection safety check.

        Args:
            data: Dictionary of key-value pairs
            timeout: Cache timeout in seconds
            version: Cache key version
        """
        is_safe, active, max_conn = self._check_connection_safety()

        if not is_safe:
            # Skip bulk set when connections are scarce
            return

        try:
            super().set_many(data, timeout, version)
        except Exception as e:
            logger.error(f"Cache set_many error: {e}")

    def delete_many(self, keys, version=None):
        """
        Delete multiple cache values with connection safety check.

        Args:
            keys: List of cache keys to delete
            version: Cache key version
        """
        is_safe, active, max_conn = self._check_connection_safety()

        if not is_safe:
            # Skip bulk delete when connections are scarce
            return

        try:
            super().delete_many(keys, version)
        except Exception as e:
            logger.error(f"Cache delete_many error: {e}")


def get_safe_cache():
    """
    Get the safe cache backend instance.

    This utility function provides easy access to the safe cache
    backend throughout the application.

    Returns:
        SafeDatabaseCache instance or default cache
    """
    try:
        # Try to get the safe cache if configured
        # Note: caches is a CacheHandler, use __getitem__ not .get()
        try:
            cache = caches["safe_db"]
        except Exception:
            # safe_db not configured, fall back to default
            cache = caches["default"]

        if isinstance(cache, SafeDatabaseCache):
            return cache
        return caches["default"]
    except Exception as e:
        logger.error(f"Error getting safe cache: {e}")
        return caches["default"]
