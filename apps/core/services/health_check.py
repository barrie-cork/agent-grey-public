"""
Health check service for system monitoring.
"""

import logging

from celery import current_app
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)


def check_celery_health():
    """
    Check if Celery workers are responsive.

    Returns:
        bool: True if Celery is healthy
    """
    try:
        # Send a test task
        result = current_app.send_task("celery.ping")
        return result.get(timeout=5) == "pong"
    except Exception as e:
        logger.error(f"Celery health check failed: {str(e)}")
        return False


def check_database_health():
    """
    Check if database is responsive.

    Returns:
        bool: True if database is healthy
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return False


def check_cache_health():
    """
    Check if cache (Redis) is responsive.

    Returns:
        bool: True if cache is healthy
    """
    try:
        cache.set("health_check", "ok", 10)
        return cache.get("health_check") == "ok"
    except Exception as e:
        logger.error(f"Cache health check failed: {str(e)}")
        return False
