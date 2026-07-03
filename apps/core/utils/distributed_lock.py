"""
Reusable distributed lock implementation for Redis-based locking.

This module provides a robust distributed lock mechanism that can be used
across different apps to ensure exclusive access to shared resources.
Extracted from apps/results_manager/tasks/orchestration.py for reusability.
"""

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Optional

from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class LockAcquisitionError(Exception):
    """Raised when a lock cannot be acquired."""

    pass


class LockConfig(BaseModel):
    """Configuration for distributed lock."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    timeout: int = Field(300, description="Lock timeout in seconds")
    retry_count: int = Field(3, description="Number of acquisition attempts")
    retry_delay: float = Field(1.0, description="Initial retry delay in seconds")
    use_exponential_backoff: bool = Field(
        True, description="Use exponential backoff for retries"
    )
    timeout_buffer: int = Field(3, description="Buffer time before timeout expires")


class DistributedLock:
    """
    Reusable distributed lock implementation using Redis cache backend.

    This class provides a robust locking mechanism for distributed systems,
    ensuring that only one process can hold a lock at a time.

    Usage:
        lock = DistributedLock()
        with lock.acquire('my_resource'):
            # Critical section code here
            pass
    """

    def __init__(self, config: Optional[LockConfig] = None):
        """
        Initialize the distributed lock.

        Args:
            config: Optional configuration for the lock behavior
        """
        self.config = config or LockConfig()

    @contextmanager
    def acquire(self, key: str, timeout: Optional[int] = None):
        """
        Acquire a distributed lock.

        Args:
            key: Unique identifier for the lock
            timeout: Optional override for lock timeout

        Yields:
            None when lock is acquired

        Raises:
            LockAcquisitionError: If lock cannot be acquired
        """
        timeout = timeout or self.config.timeout
        lock_acquired = False
        lock_value = f"lock_{timezone.now().timestamp()}"
        timeout_at = time.monotonic() + timeout - self.config.timeout_buffer

        try:
            # Try to acquire the lock
            lock_acquired = self._try_acquire(key, lock_value, timeout)

            if not lock_acquired:
                raise LockAcquisitionError(f"Could not acquire lock: {key}")

            logger.debug(f"Acquired distributed lock: {key}")

            # Yield control to the caller
            yield

        except Exception as e:
            if not isinstance(e, LockAcquisitionError):
                logger.error(f"Error during locked operation for key '{key}': {str(e)}")
            raise

        finally:
            # Release the lock if we acquired it and it hasn't expired
            if lock_acquired:
                self._release(key, timeout_at)

    def _try_acquire(self, key: str, value: str, timeout: int) -> bool:
        """
        Try to acquire lock with retries.

        Args:
            key: Lock key
            value: Lock value
            timeout: Lock timeout

        Returns:
            True if lock was acquired, False otherwise
        """
        retry_delay = self.config.retry_delay

        for attempt in range(self.config.retry_count):
            try:
                # Try to acquire lock using cache.add (atomic operation)
                if self._safe_cache_add(key, value, timeout):
                    logger.debug(f"Acquired lock '{key}' on attempt {attempt + 1}")
                    return True

                # Check if lock exists and log details
                existing_lock = self._safe_cache_get(key)
                if existing_lock:
                    logger.info(f"Lock '{key}' is held by: {existing_lock}")
                else:
                    logger.warning(
                        f"Lock '{key}' acquisition failed but no existing lock found"
                    )

                # Retry with backoff if not the last attempt
                if attempt < self.config.retry_count - 1:
                    logger.info(
                        f"Retrying lock acquisition for '{key}' in {retry_delay}s "
                        f"(attempt {attempt + 1}/{self.config.retry_count})"
                    )
                    time.sleep(retry_delay)

                    if self.config.use_exponential_backoff:
                        retry_delay *= 2  # Exponential backoff

            except Exception as e:
                logger.error(
                    f"Error acquiring lock '{key}': {type(e).__name__}: {str(e)}"
                )
                if attempt < self.config.retry_count - 1:
                    time.sleep(retry_delay)
                    if self.config.use_exponential_backoff:
                        retry_delay *= 2

        logger.error(
            f"Failed to acquire lock '{key}' after {self.config.retry_count} attempts"
        )
        return False

    def _release(self, key: str, timeout_at: float) -> None:
        """
        Release a lock if it hasn't expired.

        Args:
            key: Lock key
            timeout_at: Time when lock expires
        """
        try:
            if time.monotonic() < timeout_at:
                self._safe_cache_delete(key)
                logger.debug(f"Released distributed lock: {key}")
            else:
                logger.warning(
                    f"Lock {key} expired before release - may have been auto-deleted"
                )
        except Exception as e:
            # Don't let lock release errors propagate
            logger.warning(f"Error releasing lock {key}: {str(e)}")

    def _get_cache_instance(self, operation: str):
        """
        Get cache instance with proper fallback handling.

        Args:
            operation: The operation name for logging (e.g., 'add', 'get', 'delete')

        Returns:
            Cache instance or None if all fallbacks fail
        """
        # Check if we're in a Celery worker context
        if os.environ.get("WORKER_TYPE") == "celery":
            from apps.core.cache_init import get_worker_cache

            cache = get_worker_cache()
            if not cache:
                logger.error("Worker cache not available")
                return None
            return cache

        # Try standard cache access
        try:
            from django.core.cache import caches

            return caches["default"]
        except Exception as e:
            logger.error(f"Failed to get cache from caches['default']: {e}")
            return self._get_database_cache_fallback(operation)

    def _get_database_cache_fallback(self, operation: str):
        """
        Get database cache as emergency fallback.

        Args:
            operation: The operation name for logging

        Returns:
            DatabaseCache instance or None if creation fails
        """
        try:
            from django.core.cache.backends.db import DatabaseCache

            cache = DatabaseCache("cache_table", {})
            logger.warning(f"Using emergency database cache for {operation} operation")
            return cache
        except Exception as fallback_error:
            logger.error(
                f"Emergency cache creation also failed for {operation}: {fallback_error}"
            )
            return None

    def _validate_cache_method(self, cache, method_name: str, key: str):
        """
        Validate that cache method is callable and return fallback if not.

        Args:
            cache: Cache instance
            method_name: Name of the method to validate
            key: Cache key for logging

        Returns:
            Valid cache instance with callable method, or None if all fallbacks fail
        """
        if callable(getattr(cache, method_name, None)):
            return cache

        logger.error(
            f"Cache.{method_name} is not callable - cache type: {type(cache)}, "
            f"attempting direct database cache"
        )

        # Try direct database cache as last resort
        try:
            from django.core.cache.backends.db import DatabaseCache

            fallback_cache = DatabaseCache("cache_table", {})
            if callable(getattr(fallback_cache, method_name, None)):
                return fallback_cache
        except Exception as e:
            logger.error(f"Direct database cache also failed for key {key}: {e}")

        return None

    def _handle_cache_type_error(self, error: TypeError, key: str, operation: str):
        """
        Handle TypeError from cache operations, typically from misconfigured cache backend.

        Args:
            error: The TypeError that was raised
            key: Cache key for logging
            operation: Operation name for logging

        Returns:
            DatabaseCache instance or None if fallback fails
        """
        if "'str' object is not callable" in str(error):
            logger.error(
                f"Cache backend is a string, attempting database cache fallback "
                f"for {operation} on key {key}"
            )
            try:
                from django.core.cache.backends.db import DatabaseCache

                return DatabaseCache("cache_table", {})
            except Exception as fallback_error:
                logger.error(f"Database cache fallback failed: {fallback_error}")
                return None
        else:
            logger.error(f"Cache {operation} TypeError for key {key}: {str(error)}")
            return None

    def _safe_cache_add(self, key: str, value: str, timeout: int) -> bool:
        """
        Safely add a cache entry (atomic operation).

        Args:
            key: Cache key
            value: Cache value
            timeout: Timeout in seconds

        Returns:
            True if added successfully, False if key already exists
        """
        try:
            # Get cache instance with fallback handling
            cache = self._get_cache_instance("add")
            if not cache:
                return False

            # Validate cache method is callable
            cache = self._validate_cache_method(cache, "add", key)
            if not cache:
                return False

            # cache.add returns True if the key was added, False if it already exists
            return cache.add(key, value, timeout)

        except TypeError as e:
            # Handle misconfigured cache backend
            fallback_cache = self._handle_cache_type_error(e, key, "add")
            if fallback_cache:
                try:
                    return fallback_cache.add(key, value, timeout)
                except Exception as fallback_error:
                    logger.error(f"Fallback cache add failed: {fallback_error}")
            return False

        except Exception as e:
            logger.error(f"Cache add failed for key {key}: {str(e)}")
            return False

    def _safe_cache_get(self, key: str) -> Optional[Any]:
        """
        Safely get a cache entry.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        try:
            # Get cache instance with fallback handling
            cache = self._get_cache_instance("get")
            if not cache:
                return None

            # Validate cache method is callable
            cache = self._validate_cache_method(cache, "get", key)
            if not cache:
                return None

            return cache.get(key)

        except TypeError as e:
            # Handle misconfigured cache backend
            fallback_cache = self._handle_cache_type_error(e, key, "get")
            if fallback_cache:
                try:
                    return fallback_cache.get(key)
                except Exception as fallback_error:
                    logger.error(f"Fallback cache get failed: {fallback_error}")
            return None

        except Exception as e:
            logger.error(f"Cache get failed for key {key}: {str(e)}")
            return None

    def _safe_cache_delete(self, key: str) -> None:
        """
        Safely delete a cache entry.

        Args:
            key: Cache key
        """
        try:
            # Get cache instance with fallback handling
            cache = self._get_cache_instance("delete")
            if not cache:
                return

            # Validate cache method is callable
            cache = self._validate_cache_method(cache, "delete", key)
            if not cache:
                return

            cache.delete(key)

        except TypeError as e:
            # Handle misconfigured cache backend
            fallback_cache = self._handle_cache_type_error(e, key, "delete")
            if fallback_cache:
                try:
                    fallback_cache.delete(key)
                except Exception as fallback_error:
                    logger.error(f"Fallback cache delete failed: {fallback_error}")

        except Exception as e:
            logger.error(f"Cache delete failed for key {key}: {str(e)}")

    def is_locked(self, key: str) -> bool:
        """
        Check if a lock is currently held.

        Args:
            key: Lock key

        Returns:
            True if lock is held, False otherwise
        """
        return self._safe_cache_get(key) is not None

    def force_release(self, key: str) -> bool:
        """
        Force release a lock (use with caution).

        Args:
            key: Lock key

        Returns:
            True if lock was released, False if it didn't exist
        """
        if self.is_locked(key):
            self._safe_cache_delete(key)
            logger.warning(f"Force released lock: {key}")
            return True
        return False
