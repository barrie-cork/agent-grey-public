"""
Cache warming tasks for performance optimization.

This module contains tasks that proactively warm caches
for active sessions and user dashboards.
"""

import logging
from typing import Any, Dict

from celery import shared_task

from apps.review_manager.services.cache_warmer import CacheWarmerService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def warm_session_cache(self, session_id: str) -> Dict[str, Any]:
    """
    Warm cache for a specific session.

    Pre-populates cache entries for session progress and details
    to improve dashboard performance.
    """
    try:
        service = CacheWarmerService()
        return service.warm_session_cache(session_id)
    except Exception as e:
        logger.error(f"Error warming cache for session {session_id}: {str(e)}")
        raise self.retry(exc=e)


@shared_task
def warm_active_session_caches() -> Dict[str, Any]:
    """
    Proactively warm caches for all active sessions.
    """
    try:
        service = CacheWarmerService()
        return service.warm_active_session_caches()
    except Exception as e:
        logger.error(f"Error warming active session caches: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task
def warm_user_dashboard_cache(user_id: str) -> Dict[str, Any]:
    """
    Warm dashboard cache for a specific user.
    """
    try:
        service = CacheWarmerService()
        return service.warm_user_dashboard_cache(user_id)
    except Exception as e:
        logger.error(
            f"Error warming dashboard cache for user {user_id}: {e}", exc_info=True
        )
        return {"status": "error", "error": str(e)}


@shared_task
def invalidate_stale_caches() -> Dict[str, Any]:
    """
    Clean up stale cache entries for inactive sessions.
    """
    try:
        service = CacheWarmerService()
        return service.invalidate_stale_caches()
    except Exception as e:
        logger.error(f"Error invalidating stale caches: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
