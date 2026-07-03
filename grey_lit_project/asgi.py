"""
ASGI config for grey_lit_project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import logging
import os

import django
from django.core.asgi import get_asgi_application

# Django standard ASGI configuration - no Environment Manager needed
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "grey_lit_project.settings.local")

# Basic environment detection without complex override logic
settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "")
if not os.environ.get("ENVIRONMENT"):
    if "production" in settings_module:
        os.environ.setdefault("ENVIRONMENT", "production")
    elif "staging" in settings_module:
        os.environ.setdefault("ENVIRONMENT", "staging")
    else:
        os.environ.setdefault("ENVIRONMENT", "development")

print(f"[ASGI] Settings: {settings_module}")
print(f"[ASGI] Environment: {os.environ.get('ENVIRONMENT', 'unknown')}")

# Setup Django before importing apps
django.setup()


def test_cache_operations(cache, logger):
    """Test individual cache operations to isolate failures."""
    logger.info(f"Testing cache backend: {type(cache).__name__}")
    logger.info(f"Cache backend module: {type(cache).__module__}")

    # Test cache.set
    logger.info("Testing cache.set...")
    cache.set("__asgi_init_test__", 1, 1)
    logger.info("✓ cache.set successful")

    # Test cache.get
    logger.info("Testing cache.get...")
    test_value = cache.get("__asgi_init_test__", None)
    logger.info(f"✓ cache.get successful, value: {test_value}")

    # Test cache.delete
    logger.info("Testing cache.delete...")
    cache.delete("__asgi_init_test__")
    logger.info("✓ cache.delete successful")

    # Test cache.clear if available
    if hasattr(cache, "clear"):
        try:
            logger.info("Testing cache.clear...")
            cache.clear()
            logger.info("✓ cache.clear successful")
        except Exception as clear_test_error:
            logger.warning(f"Cache clear test failed: {clear_test_error}")


def force_database_cache_older_django(caches, logger):
    """Force database cache for older Django versions."""
    from django.core.cache.backends.db import DatabaseCache

    caches._caches["default"] = DatabaseCache("cache_table", {})
    logger.info("Forced database cache (older Django)")


def force_database_cache_newer_django(caches, logger):
    """Force database cache for newer Django versions."""
    from django.conf import settings

    # Update the cache configuration
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "cache_table",
            "OPTIONS": {
                "MAX_ENTRIES": 1000,
                "CULL_FREQUENCY": 3,
            },
        }
    }

    # Clear cache instances to force re-initialization
    try:
        if hasattr(caches, "all"):
            # Try with clear parameter first (newer Django)
            try:
                caches.all().clear()
            except TypeError:
                # Fallback for older Django versions - no clear parameter
                caches.all()
        # Clear individual cache instance
        if hasattr(caches, "_caches"):
            caches._caches.clear()
    except Exception as clear_error:
        logger.warning(f"Cache clearing failed, continuing: {clear_error}")

    cache = caches["default"]
    logger.info("Reconfigured cache settings to use database cache")
    return cache


def handle_cache_test_failure(caches, logger, test_error):
    """Handle cache test failure by forcing database cache."""
    logger.error(f"Cache test failed: {test_error}, forcing database cache")

    # Check if caches object has the _caches attribute (varies by Django version)
    if hasattr(caches, "_caches"):
        # Override with database cache directly (older Django versions)
        force_database_cache_older_django(caches, logger)
    else:
        # For newer Django versions, try to reconfigure the cache
        try:
            force_database_cache_newer_django(caches, logger)
        except Exception as reconfig_error:
            logger.error(f"Cache reconfiguration also failed: {reconfig_error}")

    logger.info("Forced database cache initialization in ASGI")


# CRITICAL: Initialize cache backend early to avoid LazyObject issues
# This ensures the cache is ready before any requests are handled
try:
    from django.core.cache import caches

    logger = logging.getLogger(__name__)

    # Log Django version for debugging DigitalOcean environment differences
    logger.info(f"Django version in DigitalOcean environment: {django.get_version()}")

    # Force cache initialization by accessing it
    cache = caches["default"]

    # Test if cache is properly initialized with detailed error tracking
    try:
        test_cache_operations(cache, logger)
        logger.info(f"Cache initialized successfully: {type(cache).__name__}")
    except Exception as test_error:
        handle_cache_test_failure(caches, logger, test_error)

except Exception as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to initialize cache in ASGI: {e}")
    # Continue anyway - cache will be initialized on first use

# Create the basic Django ASGI application
application = get_asgi_application()
