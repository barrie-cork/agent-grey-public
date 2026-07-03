"""
Production environment configuration utilities.
Handles DigitalOcean-specific settings and environment variable validation.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ProductionConfigError(Exception):
    """Raised when production configuration is invalid."""

    pass


def parse_csv_env_var(
    env_var_name: str, default: Optional[List[str]] = None
) -> List[str]:
    """
    Safely parse comma-separated environment variables.

    Args:
        env_var_name: Environment variable name
        default: Default value if not set or empty

    Returns:
        List of strings from CSV parsing
    """
    default = default or []

    raw_value = os.environ.get(env_var_name, "").strip()

    if not raw_value:
        logger.info(
            f"Environment variable {env_var_name} not set, using default: {default}"
        )
        return default

    # Handle single value without commas
    if "," not in raw_value:
        result = [raw_value.strip()]
        logger.info(f"Parsed {env_var_name} as single value: {result}")
        return result

    # Parse CSV with proper handling of whitespace and empty values
    result = [
        item.strip()
        for item in raw_value.split(",")
        if item.strip()  # Filter out empty strings
    ]

    logger.info(f"Parsed {env_var_name} as CSV: {result}")
    return result


def validate_required_env_vars() -> Dict[str, Any]:
    """
    Validate that all required production environment variables are set.

    Returns:
        Dictionary of validation results
    """
    required_vars = {
        "SECRET_KEY": {"required": True, "min_length": 32},
        "DATABASE_URL": {"required": True, "format": "url"},
        "ALLOWED_HOSTS": {"required": False, "format": "csv"},
        "CSRF_TRUSTED_ORIGINS": {"required": False, "format": "csv"},
        "SENTRY_DSN": {"required": False, "format": "url"},
    }

    results = {"valid": True, "errors": [], "warnings": [], "variables": {}}

    for var_name, config in required_vars.items():
        value = os.environ.get(var_name)
        var_result = {"name": var_name, "set": value is not None, "valid": True}

        if config["required"] and not value:
            results["valid"] = False
            results["errors"].append(
                f"Required environment variable {var_name} is not set"
            )
            var_result["valid"] = False
        elif value:
            # Validate format
            if config.get("format") == "url":
                try:
                    parsed = urlparse(value)
                    if not parsed.scheme or not parsed.netloc:
                        results["warnings"].append(f"{var_name} may not be a valid URL")
                except Exception:
                    results["warnings"].append(f"{var_name} URL parsing failed")

            # Validate length
            min_length = config.get("min_length", 0)
            if len(value) < min_length:
                results["valid"] = False
                results["errors"].append(
                    f"{var_name} must be at least {min_length} characters"
                )
                var_result["valid"] = False

        results["variables"][var_name] = var_result

    return results


def get_redis_config_for_digitalocean() -> Dict[str, Any]:
    """
    Generate Redis configuration optimized for DigitalOcean Managed Redis.

    Returns:
        Redis configuration dictionary
    """
    redis_url = os.environ.get("REDIS_URL", "")

    if not redis_url:
        logger.info("No REDIS_URL provided, Redis will be disabled")
        return {
            "enabled": False,
            "backend": "django.core.cache.backends.db.DatabaseCache",
            "location": "django_cache_table",
            "reason": "no_redis_url",
        }

    parsed_url = urlparse(redis_url)

    # Check for SSL Redis (DigitalOcean Managed Redis)
    if parsed_url.scheme == "rediss":
        logger.info("SSL Redis URL detected (DigitalOcean Managed Redis)")

        return {
            "enabled": True,
            "backend": "django_redis.cache.RedisCache",
            "location": redis_url,
            "options": {
                "CONNECTION_POOL_KWARGS": {
                    "ssl_cert_reqs": None,  # DigitalOcean doesn't require cert validation
                    "ssl_check_hostname": False,
                    "socket_timeout": 30,
                    "socket_connect_timeout": 30,
                    "retry_on_timeout": True,
                    "max_connections": 50,
                },
                "SERIALIZER": "django_redis.serializers.json.JSONSerializer",
                "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            },
            "key_prefix": "grey_lit",
            "reason": "digitalocean_ssl_redis",
        }

    # Standard Redis configuration
    elif parsed_url.scheme == "redis":
        logger.info("Standard Redis URL detected")

        return {
            "enabled": True,
            "backend": "django_redis.cache.RedisCache",
            "location": redis_url,
            "options": {
                "CONNECTION_POOL_KWARGS": {
                    "socket_timeout": 10,
                    "socket_connect_timeout": 10,
                    "retry_on_timeout": True,
                    "max_connections": 20,
                },
                "SERIALIZER": "django_redis.serializers.json.JSONSerializer",
            },
            "key_prefix": "grey_lit",
            "reason": "standard_redis",
        }

    else:
        logger.warning(f"Unrecognized Redis URL scheme: {parsed_url.scheme}")
        return {
            "enabled": False,
            "backend": "django.core.cache.backends.db.DatabaseCache",
            "location": "django_cache_table",
            "reason": "invalid_redis_url",
        }


def get_cache_configuration() -> Dict[str, Any]:
    """
    Get appropriate cache configuration for production environment.

    Returns:
        Cache configuration for Django CACHES setting
    """
    skip_redis = os.environ.get("SKIP_REDIS_CONFIG", "").lower() in ("true", "1", "yes")

    if skip_redis:
        logger.info("SKIP_REDIS_CONFIG enabled, using database cache")
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                "LOCATION": "django_cache_table",
                "TIMEOUT": 3600,  # 1 hour default
                "OPTIONS": {
                    "MAX_ENTRIES": 10000,
                    "CULL_FREQUENCY": 10,
                },
            }
        }

    redis_config = get_redis_config_for_digitalocean()

    if redis_config["enabled"]:
        cache_config = {
            "default": {
                "BACKEND": redis_config["backend"],
                "LOCATION": redis_config["location"],
                "TIMEOUT": 3600,
                "KEY_PREFIX": redis_config.get("key_prefix", ""),
                "OPTIONS": redis_config.get("options", {}),
            }
        }

        logger.info(f"Redis cache enabled: {redis_config['reason']}")
        return cache_config

    else:
        # Fallback to database cache
        logger.info(
            f"Redis cache disabled, using database cache: {redis_config['reason']}"
        )
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                "LOCATION": "django_cache_table",
                "TIMEOUT": 3600,
                "OPTIONS": {
                    "MAX_ENTRIES": 10000,
                    "CULL_FREQUENCY": 10,
                },
            }
        }


def get_cors_and_csrf_config() -> Dict[str, Any]:
    """
    Get CORS and CSRF configuration for production.

    Returns:
        Dictionary with CORS and CSRF settings including ALLOWED_CIDR_NETS
    """
    # Parse allowed hosts
    allowed_hosts = parse_csv_env_var("ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

    # Remove invalid "10.244.*" pattern if present (Django doesn't support shell-style globs)
    allowed_hosts = [h for h in allowed_hosts if not h.startswith("10.244.")]

    # Parse CSRF trusted origins with validation
    csrf_origins = parse_csv_env_var("CSRF_TRUSTED_ORIGINS", [])

    # If no CSRF origins provided, generate from allowed hosts
    if not csrf_origins and allowed_hosts:
        csrf_origins = []
        for host in allowed_hosts:
            if host not in ("localhost", "127.0.0.1", "*"):
                # Add both HTTP and HTTPS variants for production
                csrf_origins.extend(
                    [f"https://{host}", f"http://{host}"]  # For development/testing
                )

        logger.info(
            f"Generated CSRF_TRUSTED_ORIGINS from ALLOWED_HOSTS: {csrf_origins}"
        )

    # CORS origins - typically same as CSRF origins
    cors_origins = parse_csv_env_var("CORS_ALLOWED_ORIGINS", csrf_origins)

    # ALLOWED_CIDR_NETS for IP range validation (Django 4.1+)
    # Required for DigitalOcean Kubernetes health check probes
    allowed_cidr_nets = parse_csv_env_var("ALLOWED_CIDR_NETS", ["10.244.0.0/16"])

    return {
        "ALLOWED_HOSTS": allowed_hosts,
        "ALLOWED_CIDR_NETS": allowed_cidr_nets,
        "CSRF_TRUSTED_ORIGINS": csrf_origins,
        "CORS_ALLOWED_ORIGINS": cors_origins,
        "CORS_ALLOW_CREDENTIALS": True,
        "CSRF_COOKIE_SECURE": True,
        "SESSION_COOKIE_SECURE": True,
    }


def get_database_config() -> Dict[str, Any]:
    """
    Get database configuration with DigitalOcean optimizations.

    Returns:
        Database configuration
    """
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise ProductionConfigError("DATABASE_URL environment variable is required")

    # Parse database URL
    try:
        import dj_database_url

        db_config = dj_database_url.parse(database_url)

        # DigitalOcean optimizations
        db_config.update(
            {
                "CONN_MAX_AGE": 600,  # Connection pooling
                "OPTIONS": {
                    "sslmode": "require",  # DigitalOcean requires SSL
                    "connect_timeout": 30,
                    "application_name": "grey_lit_production",
                },
            }
        )

        logger.info("Database configuration loaded with DigitalOcean optimizations")
        return {"default": db_config}

    except Exception as e:
        raise ProductionConfigError(f"Invalid DATABASE_URL: {e}")


def get_logging_config() -> Dict[str, Any]:
    """
    Get production logging configuration.

    Returns:
        Logging configuration dictionary
    """
    log_level = os.environ.get("DJANGO_LOG_LEVEL", "INFO")

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "production": {
                "format": "[{levelname}] {asctime} {name} {message}",
                "style": "{",
            },
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(levelname)s %(asctime)s %(name)s %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "production",
                "level": log_level,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": "/app/logs/django.log",
                "maxBytes": 1024 * 1024 * 10,  # 10MB
                "backupCount": 5,
                "formatter": "json",
                "level": log_level,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
            "apps": {
                "handlers": ["console"],
                "level": log_level,
                "propagate": False,
            },
        },
    }
