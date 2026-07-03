"""
Redis configuration module for production optimization.

This module provides centralized Redis configuration for:
- Django caching backend
- Celery message broker
- Session storage
- Rate limiting
"""

import importlib.util
import logging
import ssl

from apps.core.env_config import get_env

# Import Redis classes for proper SSL connection configuration
try:
    import redis
    import redis.connection
except ImportError:
    redis = None

logger = logging.getLogger(__name__)


def get_redis_url():
    """
    Get Redis URL from environment.

    Returns:
        str or None: Redis connection URL, or None if not configured
    """
    redis_url = get_env("REDIS_URL", default=None)
    if not redis_url:
        logger.warning(
            "REDIS_URL environment variable not set - Redis features will be unavailable"
        )
    return redis_url


def _validate_redis_url(redis_url):
    """
    Validate Redis URL format and availability.

    Args:
        redis_url: Redis URL from environment

    Returns:
        tuple: (is_valid, error_message_if_invalid)
    """
    if not redis_url:
        return False, "Redis URL not configured"
    if not isinstance(redis_url, str):
        return False, f"Invalid Redis URL type: {type(redis_url)}"
    return True, ""


def _get_ssl_connection_kwargs(redis_url):
    """
    Get SSL connection pool kwargs for rediss:// URLs.

    Args:
        redis_url: Redis connection URL

    Returns:
        dict: SSL configuration or empty dict for non-SSL
    """
    if not redis_url.startswith("rediss://"):
        return {}

    if not redis or not hasattr(redis.connection, "SSLConnection"):
        return None  # Signal that SSL is required but unavailable

    logger.info("Using Redis SSL connection class for DigitalOcean managed Redis")
    return {
        "connection_class": redis.connection.SSLConnection,
        "ssl_cert_reqs": ssl.CERT_NONE,
        "ssl_ca_certs": None,
        "ssl_certfile": None,
        "ssl_keyfile": None,
    }


def _create_redis_cache_config(redis_url, connection_pool_kwargs):
    """
    Create the complete Redis cache configuration dict.

    Args:
        redis_url: Redis connection URL
        connection_pool_kwargs: Connection pool configuration

    Returns:
        dict: Dict with 'default', 'session', and 'query' cache configurations
    """
    return {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": redis_url,
            "OPTIONS": {
                "CONNECTION_POOL_KWARGS": connection_pool_kwargs,
                "SOCKET_CONNECT_TIMEOUT": 5,
                "SOCKET_TIMEOUT": 5,
                "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
                "IGNORE_EXCEPTIONS": True,  # Fallback gracefully if Redis is down
                # Note: hiredis parser is auto-detected if hiredis package is installed
            },
            "KEY_PREFIX": "greylit",
            "TIMEOUT": 300,  # Default cache timeout (5 minutes)
        },
        # Separate cache for sessions
        "session": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"{redis_url}/1",  # Use Redis database 1 for sessions
            "OPTIONS": {},
            "KEY_PREFIX": "session",
            "TIMEOUT": 86400,  # 24 hours for sessions
        },
        # Cache for expensive queries
        "query": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": f"{redis_url}/2",  # Use Redis database 2 for query cache
            "OPTIONS": {
                "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            },
            "KEY_PREFIX": "query",
            "TIMEOUT": 3600,  # 1 hour for query results
        },
    }


def _validate_cache_config_structure(cache_config):
    """
    Validate the structure of the cache configuration.

    Args:
        cache_config: Cache configuration dict to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not isinstance(cache_config, dict) or "default" not in cache_config:
        logger.error(
            f"Invalid cache config structure: {type(cache_config)}, using database cache"
        )
        return False

    default_config = cache_config.get("default", {})
    if not isinstance(default_config, dict) or "BACKEND" not in default_config:
        logger.error("Invalid default cache config, using database cache")
        return False

    return True


def get_cache_config():
    """
    Get Django cache configuration for Redis.

    Returns:
        dict: Django CACHES configuration or database cache fallback
    """
    import logging

    logger = logging.getLogger(__name__)

    # Default database cache configuration as fallback
    database_cache_config = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "cache_table",
            "OPTIONS": {
                "MAX_ENTRIES": 1000,
                "CULL_FREQUENCY": 3,
            },
        }
    }

    # Get and validate Redis URL
    try:
        redis_url = get_redis_url()
        is_valid, error_msg = _validate_redis_url(redis_url)
        if not is_valid:
            logger.warning(f"{error_msg}, using database cache")
            return database_cache_config
    except Exception as e:
        logger.warning(f"Failed to get Redis URL: {e}, using database cache")
        return database_cache_config

    # Check for django_redis availability
    if not importlib.util.find_spec("django_redis"):
        logger.error("django_redis not available, using database cache")
        return database_cache_config

    # Build connection pool kwargs with SSL if needed
    connection_pool_kwargs = {
        "max_connections": 50,
        "retry_on_timeout": True,
    }

    ssl_kwargs = _get_ssl_connection_kwargs(redis_url)
    if ssl_kwargs is None:
        logger.warning(
            "Redis SSL classes not available, falling back to database cache"
        )
        return database_cache_config
    connection_pool_kwargs.update(ssl_kwargs)

    # Create and validate cache configuration
    try:
        cache_config = _create_redis_cache_config(redis_url, connection_pool_kwargs)

        if not _validate_cache_config_structure(cache_config):
            return database_cache_config

        return cache_config
    except Exception as e:
        logger.error(f"Error creating Redis cache config: {e}, using database cache")
        return database_cache_config


def get_celery_config():
    """
    Get Celery configuration for Redis broker.

    Returns:
        dict: Celery configuration settings, or None if Redis not configured
    """
    redis_url = get_redis_url()

    if not redis_url:
        logger.warning(
            "Redis URL not available - Celery will use database broker as fallback"
        )
        return None

    return {
        "broker_url": redis_url,
        "result_backend": redis_url,
        "broker_connection_retry_on_startup": True,
        "broker_connection_retry": True,
        "broker_connection_max_retries": 10,
        "worker_prefetch_multiplier": 4,
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "UTC",
        "enable_utc": True,
        "result_expires": 3600,  # Results expire after 1 hour
        "task_track_started": True,
        "task_time_limit": 300,  # 5 minutes max per task
        "task_soft_time_limit": 240,  # 4 minutes soft limit
        "worker_max_tasks_per_child": 100,  # Restart worker after 100 tasks
        "worker_disable_rate_limits": False,
        "task_compression": "gzip",  # Compress task payloads
    }


def get_session_config():
    """
    Get session configuration for Redis backend.

    Returns:
        dict: Session configuration settings
    """
    return {
        "SESSION_ENGINE": "django.contrib.sessions.backends.cache",
        "SESSION_CACHE_ALIAS": "session",
        "SESSION_COOKIE_AGE": 86400,  # 24 hours
        "SESSION_EXPIRE_AT_BROWSER_CLOSE": False,
        "SESSION_SAVE_EVERY_REQUEST": False,  # Only save on changes
    }


def get_rate_limit_config():
    """
    Get rate limiting configuration using Redis.

    Returns:
        dict: Rate limiting settings
    """
    return {
        "RATELIMIT_USE_CACHE": "default",
        "RATELIMIT_ENABLE": True,
        "RATELIMIT_VIEW": "100/h",  # Default rate limit
        "RATELIMIT_API": "1000/h",  # API rate limit
        "RATELIMIT_SEARCH": "10/m",  # Search execution rate limit
    }


def get_channels_config():
    """
    Get Django Channels configuration for WebSocket support.

    Returns:
        dict: Django CHANNEL_LAYERS configuration
    """
    import logging

    logger = logging.getLogger(__name__)

    # Default in-memory channel layer (fallback)
    in_memory_config = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

    try:
        redis_url = get_redis_url()
        if not redis_url or not isinstance(redis_url, str):
            logger.warning(
                f"Invalid Redis URL for Channels: {redis_url}, using in-memory channel layer"
            )
            return in_memory_config
    except Exception as e:
        logger.warning(
            f"Failed to get Redis URL for Channels: {e}, using in-memory channel layer"
        )
        return in_memory_config

    # Parse Redis URL to get host and port
    try:
        from urllib.parse import urlparse

        parsed = urlparse(redis_url)

        # Extract host and port
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379

        # Use database 2 for Channels (0 for cache, 1 for sessions)
        # Note: DigitalOcean Managed Redis might not support multiple databases
        db_num = 2
        if "digitalocean" in host or "rediss://" in redis_url:
            # DigitalOcean Managed Redis typically uses database 0 only
            db_num = 0

        # Configure for SSL if using rediss://
        if redis_url.startswith("rediss://"):
            # For SSL connections, channels_redis handles SSL internally
            # Just pass the URL with SSL parameters
            # Extract password from URL if present
            password = parsed.password if parsed.password else None
            username = parsed.username if parsed.username else "default"

            # Build connection string with credentials
            if password:
                connection_string = (
                    f"rediss://{username}:{password}@{host}:{port}/{db_num}"
                )
            else:
                connection_string = f"rediss://{host}:{port}/{db_num}"

            # For SSL connections, the rediss:// URL handles SSL automatically
            # No need for connection_kwargs with SSL URLs
            channel_config = {
                "default": {
                    "BACKEND": "channels_redis.core.RedisChannelLayer",
                    "CONFIG": {
                        "hosts": [connection_string],
                        "capacity": 1500,
                        "expiry": 10,
                    },
                },
            }
        else:
            # For non-SSL connections
            channel_config = {
                "default": {
                    "BACKEND": "channels_redis.core.RedisChannelLayer",
                    "CONFIG": {
                        "hosts": [(host, port, db_num)],
                        "capacity": 1500,
                        "expiry": 10,
                    },
                },
            }

        logger.info(
            f"Configured Channels with Redis at {host}:{port} (database {db_num})"
        )
        return channel_config

    except Exception as e:
        logger.error(
            f"Failed to configure Channels with Redis: {e}, using in-memory channel layer"
        )
        return in_memory_config


def _create_redis_client(redis_url):
    """
    Create a Redis client with appropriate SSL settings.

    Args:
        redis_url: Redis connection URL

    Returns:
        redis.Redis or None: Redis client or None if creation fails
    """
    try:
        import redis
    except ImportError:
        return None

    try:
        if redis_url.startswith("rediss://"):
            client = redis.from_url(
                redis_url,
                socket_connect_timeout=2,
                ssl_cert_reqs=ssl.CERT_NONE,
                ssl_ca_certs=None,
                ssl_certfile=None,
                ssl_keyfile=None,
            )
        else:
            client = redis.from_url(redis_url, socket_connect_timeout=2)
        return client
    except Exception:
        return None


def _gather_redis_diagnostics(client):
    """
    Test connection and gather diagnostic information.

    Args:
        client: Redis client instance

    Returns:
        tuple: (is_connected, message_with_diagnostics)
    """
    try:
        from redis.exceptions import ConnectionError, TimeoutError

        # Test connection
        client.ping()

        # Get Redis info
        info = client.info()
        version = info.get("redis_version", "unknown")
        used_memory = info.get("used_memory_human", "unknown")
        connected_clients = info.get("connected_clients", 0)

        return (
            True,
            f"Redis {version} connected. Memory: {used_memory}, Clients: {connected_clients}",
        )
    except (ConnectionError, TimeoutError) as e:
        return False, f"Redis connection failed: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error checking Redis: {str(e)}"


def check_redis_connection():
    """
    Check if Redis is accessible.

    Returns:
        tuple: (bool, str) - (is_connected, message)
    """
    # Check if redis library is available
    if not importlib.util.find_spec("redis"):
        return False, "Redis library not installed"

    try:
        import redis  # noqa: F401
        from redis.exceptions import ConnectionError, TimeoutError  # noqa: F401
    except ImportError as e:
        return False, f"Redis library import failed: {e}"

    # Get and validate Redis URL
    try:
        redis_url = get_redis_url()
        if not redis_url or not isinstance(redis_url, str):
            return False, f"Invalid Redis URL: {redis_url}"
    except Exception as e:
        return False, f"Failed to get Redis URL: {e}"

    # Create Redis client
    client = _create_redis_client(redis_url)
    if client is None:
        return False, "Failed to create Redis client"

    # Test connection and gather diagnostics
    return _gather_redis_diagnostics(client)


# Cache key patterns for different types of data
CACHE_KEYS = {
    "session_list": "sessions:user:{user_id}:list",
    "session_detail": "sessions:{session_id}:detail",
    "search_results": "search:{session_id}:results:page:{page}",
    "statistics": "stats:{session_id}:overview",
    "report": "report:{session_id}:{format}",
    "query_count": "queries:{session_id}:count",
    "user_activity": "activity:user:{user_id}:recent",
}


def get_cache_key(key_type, **kwargs):
    """
    Generate a cache key based on pattern.

    Args:
        key_type: Type of cache key from CACHE_KEYS
        **kwargs: Parameters to format the key

    Returns:
        str: Formatted cache key
    """
    pattern = CACHE_KEYS.get(key_type)
    if not pattern:
        raise ValueError(f"Unknown cache key type: {key_type}")

    return pattern.format(**kwargs)
