"""
Cache utilities for robust cache operations.

Provides safe wrappers around Django cache operations to prevent
'str' object is not callable errors in production.
"""

import logging
import os
import time
import uuid
from typing import Any, Optional, Tuple

from django.core.cache.backends.base import BaseCache

from apps.core.env_config import get_env_bool, get_env_float, get_env_int

logger = logging.getLogger(__name__)

# Global cache validation state to avoid repeated validation
_validated_cache: Optional[BaseCache] = None
_validation_attempted = False


def _get_redis_diagnostics(cache_backend: str) -> dict:
    """
    Get Redis connection diagnostics.

    Args:
        cache_backend: Cache backend class name

    Returns:
        dict: Diagnostic information
    """
    diagnostics = {
        "backend": cache_backend,
        "redis_available": False,
        "connection_info": None,
        "error": None,
    }

    try:
        # Check if this is a Redis backend
        if "Redis" not in cache_backend:
            diagnostics["error"] = "Not a Redis backend"
            return diagnostics

        # Try to get Redis connection info
        from django.core.cache import cache as default_cache

        if hasattr(default_cache, "_cache"):
            # django-redis specific
            client = default_cache._cache.get_client()
            connection_pool = client.connection_pool

            diagnostics["connection_info"] = {
                "max_connections": getattr(
                    connection_pool, "max_connections", "unknown"
                ),
                "created_connections": len(
                    getattr(connection_pool, "_created_connections", [])
                ),
                "connection_kwargs": {
                    k: v
                    for k, v in getattr(
                        connection_pool, "connection_kwargs", {}
                    ).items()
                    if k not in ["password", "username"]  # Don't log sensitive info
                },
            }

            # Try a ping
            try:
                client.ping()
                diagnostics["redis_available"] = True
            except Exception as e:
                diagnostics["error"] = f"Ping failed: {str(e)}"

    except Exception as e:
        diagnostics["error"] = f"Diagnostics failed: {str(e)}"

    return diagnostics


def _validate_cache_with_retry(  # noqa: C901 - Cache validation with retry logic and fallbacks
    cache: BaseCache, cache_backend: str
) -> Tuple[bool, str]:
    """
    Validate cache operations with retry logic.

    Args:
        cache: Cache backend instance
        cache_backend: Cache backend class name

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Get validation parameters from environment
    validation_timeout = get_env_int("CACHE_VALIDATION_TIMEOUT", default=60)
    validation_delay = get_env_float("CACHE_VALIDATION_DELAY", default=0.5)
    max_attempts = get_env_int("CACHE_VALIDATION_MAX_ATTEMPTS", default=3)

    # Generate unique test key to avoid conflicts
    test_key = f"cache_test_{uuid.uuid4().hex[:8]}_{int(time.time())}"
    test_value = f"test_value_{uuid.uuid4().hex[:8]}"
    retry_delay = 0.5  # Start with 500ms

    validation_start = time.time()
    errors = []

    for attempt in range(max_attempts):
        attempt_start = time.time()
        try:
            # Critical check: Ensure cache.set is callable before using it
            if not callable(getattr(cache, "set", None)):
                logger.warning(
                    f"Cache validation skipped: 'set' method is not callable on {cache_backend}. "
                    "This may be a ConnectionProxy initialization issue."
                )
                # Skip validation but allow cache to work
                return True, "Validation skipped due to non-callable methods"

            # Set with configurable timeout for distributed systems
            cache.set(test_key, test_value, validation_timeout)

            # Configurable delay to allow for replication in distributed systems
            time.sleep(validation_delay)

            # Check get method is callable
            if not callable(getattr(cache, "get", None)):
                logger.warning(
                    f"Cache validation skipped: 'get' method is not callable on {cache_backend}. "
                    "This may be a ConnectionProxy initialization issue."
                )
                return True, "Validation skipped due to non-callable get method"

            # Try to retrieve the value
            retrieved_value = cache.get(test_key)

            if retrieved_value == test_value:
                # Success! Clean up and return
                try:
                    cache.delete(test_key)
                except Exception:
                    pass  # Ignore deletion errors

                validation_time = time.time() - validation_start
                logger.debug(
                    f"Cache validation successful for {cache_backend} after {validation_time:.2f}s"
                )
                return True, ""
            else:
                attempt_time = time.time() - attempt_start
                error_msg = (
                    f"Cache validation failed on attempt {attempt + 1}/{max_attempts}: "
                    f"Expected {test_value!r}, got {retrieved_value!r} "
                    f"(attempt took {attempt_time:.2f}s)"
                )
                logger.warning(error_msg)
                errors.append(error_msg)

                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

        except TypeError as e:
            # Handle the specific 'str' object is not callable error
            if "'str' object is not callable" in str(e):
                logger.warning(
                    f"Cache validation failed due to ConnectionProxy issue: {e}. "
                    "Skipping validation to allow cache operations to proceed."
                )
                return True, "Validation skipped due to ConnectionProxy TypeError"
            else:
                # Other TypeErrors should still be logged
                attempt_time = time.time() - attempt_start
                error_msg = (
                    f"Cache operation failed on attempt {attempt + 1}/{max_attempts}: "
                    f"TypeError: {str(e)} "
                    f"(attempt took {attempt_time:.2f}s)"
                )
                logger.warning(error_msg)
                errors.append(error_msg)

        except Exception as e:
            attempt_time = time.time() - attempt_start
            error_msg = (
                f"Cache operation failed on attempt {attempt + 1}/{max_attempts}: "
                f"{type(e).__name__}: {str(e)} "
                f"(attempt took {attempt_time:.2f}s)"
            )
            logger.warning(error_msg)
            errors.append(error_msg)

            if attempt < max_attempts - 1:
                time.sleep(retry_delay)
                retry_delay *= 2

    # All attempts failed - try to clean up test key
    try:
        cache.delete(test_key)
    except Exception:
        pass

    # Provide detailed failure information
    total_time = time.time() - validation_start
    detailed_error = (
        f"Cache validation failed after {max_attempts} attempts in {total_time:.2f}s. "
        f"Backend: {cache_backend}. "
        f"Errors: {'; '.join(errors[-2:])}"  # Include last 2 errors
    )

    return False, detailed_error


def _get_cache_instance() -> Optional[BaseCache]:
    """Get initial cache instance from Django."""
    if os.environ.get("WORKER_TYPE") == "celery":
        # For Celery workers, force immediate initialization
        from apps.core.cache_init import get_worker_cache

        cache = get_worker_cache()
        if cache:
            logger.debug("Using worker cache instance")
            return cache
        else:
            raise Exception("Worker cache initialization failed")
    else:
        # Normal Django context - use caches['default']
        from django.core.cache import caches

        cache = caches["default"]
        # Force initialization by attempting a simple operation
        cache.get("__init_test__", None)  # noqa: F841
        logger.debug(
            f"Got cache backend from caches['default']: {type(cache).__name__}"
        )
        return cache


def _create_database_cache() -> BaseCache:
    """Create a database cache as fallback."""
    # Ensure cache table exists
    from django.core.management import call_command

    try:
        call_command("createcachetable", "cache_table", verbosity=0)
        logger.info("Cache table created or verified")
    except Exception as table_error:
        logger.debug(f"Cache table creation attempt: {table_error}")

    # Create database cache backend
    from django.core.cache.backends.db import DatabaseCache

    cache = DatabaseCache("cache_table", {})
    logger.info("Using database cache backend")
    return cache


def _validate_cache_instance(cache) -> BaseCache:
    """Validate cache instance and fix common issues."""
    # Handle string cache (misconfiguration)
    if isinstance(cache, str):
        logger.error(f"Cache is string: {cache}")
        return _create_database_cache()

    # Validate required methods
    if not hasattr(cache, "set") or not hasattr(cache, "get"):
        logger.error(f"Cache missing methods. Type: {type(cache)}")
        return _create_database_cache()

    return cache


def _should_skip_validation(cache_backend: str, skip_validation: bool) -> bool:
    """Determine if cache validation should be skipped."""
    if "DatabaseCache" in cache_backend:
        logger.info("Using DatabaseCache, skipping validation")
        return True

    if skip_validation:
        logger.info("Cache validation skipped via setting")
        return True

    if (
        "ConnectionProxy" in cache_backend
        or os.environ.get("SKIP_CACHE_VALIDATION") == "true"
    ):
        logger.info(f"Skipping validation for {cache_backend}")
        return True

    return False


def get_safe_cache() -> Optional[BaseCache]:
    """
    Get a validated cache backend instance.

    Returns:
        BaseCache instance if valid, None if not available
    """
    global _validated_cache, _validation_attempted

    # Return cached result if already attempted
    if _validation_attempted:
        return _validated_cache

    try:
        skip_validation = get_env_bool("CACHE_SKIP_VALIDATION", default=False)

        # Get cache instance
        try:
            cache = _get_cache_instance()
        except Exception as e:
            logger.error(f"Cache initialization failed: {e}")
            cache = _create_database_cache()
            _validated_cache = cache
            _validation_attempted = True
            return cache

        # Validate and fix cache instance
        cache = _validate_cache_instance(cache)
        cache_backend = cache.__class__.__name__
        logger.debug(f"Cache backend: {cache_backend}")

        # Check if validation should be skipped
        if _should_skip_validation(cache_backend, skip_validation):
            _validated_cache = cache
            _validation_attempted = True
            return cache

        # Validate cache operations
        is_valid, error_msg = _validate_cache_with_retry(cache, cache_backend)

        if not is_valid:
            logger.error(f"Cache validation failed: {error_msg}")

            if "Redis" in cache_backend:
                diagnostics = _get_redis_diagnostics(cache_backend)
                logger.error(f"Redis diagnostics: {diagnostics}")

            if get_env_bool("CACHE_ALLOW_FAILED_VALIDATION", default=False):
                logger.warning("Continuing with faulty cache")
                _validated_cache = cache
                _validation_attempted = True
                return cache
            return None

        logger.info(f"Cache validation successful: {cache_backend}")
        _validated_cache = cache
        _validation_attempted = True
        return cache

    except Exception as e:
        logger.error(f"Failed to get cache: {type(e).__name__}: {str(e)}")
        _validation_attempted = True
        return None


def safe_cache_add(  # noqa: C901 - Safe cache operation with extensive error handling
    key: str, value: Any, timeout: Optional[int] = None
) -> bool:
    """
    Safely add a value to cache with error handling.

    Args:
        key: Cache key
        value: Value to cache
        timeout: Timeout in seconds

    Returns:
        True if added successfully, False otherwise
    """
    try:
        cache = get_safe_cache()
        if not cache:
            logger.debug(f"Cache not available for add operation on key: {key}")
            return False

        # Critical fix: Ensure cache.add is callable before using it
        if not callable(getattr(cache, "add", None)):
            raise TypeError(
                f"Cache backend {type(cache).__name__} has non-callable 'add' method"
            )

        # Try to call the add method
        # For ConnectionProxy, this might trigger lazy initialization
        try:
            result = cache.add(key, value, timeout)
            return result
        except TypeError as te:
            # If it's a "str object is not callable" error, try emergency fallback
            if "'str' object is not callable" in str(te):
                logger.error(
                    f"Cache backend returned string instead of method for key {key}"
                )
                raise
            else:
                # Re-raise other TypeErrors
                raise

    except (TypeError, AttributeError) as e:
        # Emergency fallback: create database cache directly
        logger.error(f"Cache add error for key {key}, using emergency fallback: {e}")
        try:
            from django.core.cache.backends.db import DatabaseCache

            emergency_cache = DatabaseCache("cache_table", {})
            result = emergency_cache.add(key, value, timeout)
            logger.info(f"Emergency cache add succeeded for key {key}")
            return result
        except Exception as fallback_error:
            logger.error(f"Emergency cache add also failed: {fallback_error}")
            return False
    except Exception as e:
        logger.error(f"Cache add failed for key {key}: {type(e).__name__}: {str(e)}")
        return False


def safe_cache_set(  # noqa: C901 - Safe cache operation with extensive error handling
    key: str, value: Any, timeout: Optional[int] = None
) -> bool:
    """
    Safely set a value in cache with error handling.

    Args:
        key: Cache key
        value: Value to cache
        timeout: Timeout in seconds

    Returns:
        True if set successfully, False otherwise
    """
    try:
        cache = get_safe_cache()
        if not cache:
            logger.warning(f"Cache not available for set operation on key: {key}")
            return False

        # Critical fix: Ensure cache.set is callable before using it
        if not callable(getattr(cache, "set", None)):
            raise TypeError(
                f"Cache backend {type(cache).__name__} has non-callable 'set' method"
            )

        # Try to call the set method
        # For ConnectionProxy, this might trigger lazy initialization
        try:
            cache.set(key, value, timeout)
            return True
        except TypeError as te:
            # If it's a "str object is not callable" error, try emergency fallback
            if "'str' object is not callable" in str(te):
                logger.error(
                    f"Cache backend returned string instead of method for key {key}"
                )
                raise
            else:
                # Re-raise other TypeErrors
                raise

    except (TypeError, AttributeError) as e:
        # Emergency fallback: create database cache directly
        logger.error(f"Cache set error for key {key}, using emergency fallback: {e}")
        try:
            from django.core.cache.backends.db import DatabaseCache

            emergency_cache = DatabaseCache("cache_table", {})
            emergency_cache.set(key, value, timeout)
            logger.info(f"Emergency cache set succeeded for key {key}")
            return True
        except Exception as fallback_error:
            logger.error(f"Emergency cache set also failed: {fallback_error}")
            return False
    except Exception as e:
        logger.error(f"Cache set failed for key {key}: {type(e).__name__}: {str(e)}")
        return False


def safe_cache_get(  # noqa: C901 - Safe cache operation with extensive error handling
    key: str, default: Any = None
) -> Any:
    """
    Safely get a value from cache with error handling.

    Args:
        key: Cache key
        default: Default value if not found or error

    Returns:
        Cached value or default
    """
    try:
        cache = get_safe_cache()
        if not cache:
            logger.debug(f"Cache not available for get operation on key: {key}")
            return default

        # Critical fix: Ensure cache.get is callable before using it
        if not callable(getattr(cache, "get", None)):
            raise TypeError(
                f"Cache backend {type(cache).__name__} has non-callable 'get' method"
            )

        # Try to call the get method
        # For ConnectionProxy, this might trigger lazy initialization
        try:
            result = cache.get(key, default)
            return result
        except TypeError as te:
            # If it's a "str object is not callable" error, try emergency fallback
            if "'str' object is not callable" in str(te):
                logger.error(
                    f"Cache backend returned string instead of method for key {key}"
                )
                raise
            else:
                # Re-raise other TypeErrors
                raise

    except (TypeError, AttributeError) as e:
        # Emergency fallback: create database cache directly
        logger.error(f"Cache get error for key {key}, using emergency fallback: {e}")
        try:
            from django.core.cache.backends.db import DatabaseCache

            emergency_cache = DatabaseCache("cache_table", {})
            result = emergency_cache.get(key, default)
            logger.debug(f"Emergency cache get succeeded for key {key}")
            return result
        except Exception as fallback_error:
            logger.error(f"Emergency cache get also failed: {fallback_error}")
            return default
    except Exception as e:
        logger.error(f"Cache get failed for key {key}: {type(e).__name__}: {str(e)}")
        return default


def safe_cache_delete(key: str) -> bool:
    """
    Safely delete a value from cache with error handling.

    Args:
        key: Cache key

    Returns:
        True if deleted successfully, False otherwise
    """
    cache = get_safe_cache()
    if not cache:
        logger.warning(f"Cache not available for delete operation on key: {key}")
        return False

    try:
        cache.delete(key)
        return True
    except Exception as e:
        logger.error(f"Cache delete failed for key {key}: {type(e).__name__}: {str(e)}")
        return False


def reset_cache_validation():
    """
    Reset the cache validation state.

    Useful for testing or when cache backend configuration changes.
    """
    global _validated_cache, _validation_attempted
    _validated_cache = None
    _validation_attempted = False
    logger.info("Cache validation state reset")


def is_cache_available() -> bool:
    """
    Check if cache is available.

    Returns:
        True if cache is available, False otherwise
    """
    return get_safe_cache() is not None
