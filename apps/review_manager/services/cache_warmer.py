"""
Cache warming service for proactive performance optimization.

Implements service methods to pre-populate caches for active sessions,
reducing latency for user interactions.
"""

import logging
from datetime import timedelta
from typing import Any, Dict

from celery import group
from django.db.models import Q
from django.utils import timezone

# Import cache service directly, SearchSession will be imported lazily
from apps.core.services.cache_service import WorkflowCacheService

logger = logging.getLogger(__name__)


class CacheWarmerService:
    """Service for cache warming operations."""

    def warm_session_cache(self, session_id: str) -> Dict[str, Any]:
        """
        Warm cache for a specific session.

        Pre-loads commonly accessed session data into cache to
        improve response times for dashboard and detail views.

        Args:
            session_id: UUID of the session to warm

        Returns:
            Dict with warming results
        """
        try:
            logger.info(f"Warming cache for session {session_id}")

            # Warm session progress
            progress = WorkflowCacheService.get_session_progress(session_id)

            # Warm session details
            details = WorkflowCacheService.get_session_details(
                session_id, include_activities=True
            )

            # Check if session exists and is active
            if not details:
                logger.warning(f"Session {session_id} not found for cache warming")
                return {
                    "session_id": session_id,
                    "status": "not_found",
                    "warmed": False,
                }

            # Additional warming based on session status
            status = details.get("status")

            if status in ["executing", "processing_results"]:
                # These are the most dynamic states - warm more frequently
                logger.debug(f"Session {session_id} is in active state: {status}")

            return {
                "session_id": session_id,
                "status": status,
                "warmed": True,
                "progress_cached": bool(progress),
                "details_cached": bool(details),
            }

        except Exception as e:
            logger.error(f"Error warming cache for session {session_id}: {str(e)}")
            raise  # Let the task wrapper handle retry logic

    def warm_active_session_caches(self) -> Dict[str, Any]:
        """
        Proactively warm caches for all active sessions.

        Identifies sessions likely to be accessed and pre-populates
        their cache entries. Focuses on:
        - Currently executing sessions
        - Sessions being processed
        - Sessions under review
        - Recently updated sessions

        Returns:
            Dict with summary of warming results
        """
        # Lazy import to avoid Django initialization timing issues in Celery
        from apps.review_manager.models import SearchSession

        start_time = timezone.now()

        try:
            # Find active sessions that need cache warming
            # Priority 1: Currently executing or processing
            high_priority_sessions = SearchSession.objects.filter(
                status__in=["executing", "processing_results"]
            ).values_list("id", flat=True)

            # Priority 2: Under review or recently updated
            recent_cutoff = timezone.now() - timedelta(hours=2)
            medium_priority_sessions = (
                SearchSession.objects.filter(
                    Q(status="under_review") | Q(updated_at__gte=recent_cutoff)
                )
                .exclude(id__in=high_priority_sessions)
                .values_list("id", flat=True)[:20]
            )  # Limit to prevent overload

            # Import warm_session_cache task for queuing
            from apps.review_manager.tasks.cache import warm_session_cache

            # Warm high priority sessions asynchronously
            high_priority_count = 0
            for session_id in high_priority_sessions:
                try:
                    warm_session_cache.delay(str(session_id))
                    high_priority_count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to queue high priority session {session_id}: {str(e)}"
                    )

            # Warm medium priority sessions in parallel (fire and forget)
            medium_priority_count = 0
            if medium_priority_sessions:
                job = group(
                    warm_session_cache.s(str(session_id))
                    for session_id in medium_priority_sessions
                )
                # Fire and forget - don't wait for results
                job.apply_async()
                medium_priority_count = len(medium_priority_sessions)

            # Calculate summary statistics
            total_queued = high_priority_count + medium_priority_count

            duration = (timezone.now() - start_time).total_seconds()

            logger.info(
                f"Cache warming queued: {total_queued} sessions "
                f"({high_priority_count} high priority, {medium_priority_count} medium priority) "
                f"in {duration:.2f}s"
            )

            return {
                "total_sessions_queued": total_queued,
                "high_priority_count": high_priority_count,
                "medium_priority_count": medium_priority_count,
                "duration_seconds": duration,
                "timestamp": timezone.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error in cache warming service: {str(e)}")
            return {"error": str(e), "timestamp": timezone.now().isoformat()}

    def warm_user_dashboard_cache(self, user_id: str) -> Dict[str, Any]:
        """
        Warm dashboard cache for a specific user.

        Pre-loads dashboard statistics and session list for faster
        initial page loads.

        Args:
            user_id: UUID of the user

        Returns:
            Dict with warming results
        """
        # Lazy import to avoid Django initialization timing issues in Celery
        from apps.review_manager.models import SearchSession

        try:
            logger.info(f"Warming dashboard cache for user {user_id}")

            # Warm dashboard statistics
            stats = WorkflowCacheService.get_dashboard_stats(user_id)

            # Warm user's active sessions
            active_sessions = (
                SearchSession.objects.filter(owner_id=user_id)
                .active_only()
                .values_list("id", flat=True)[:10]
            )

            session_results = []
            for session_id in active_sessions:
                try:
                    WorkflowCacheService.get_session_progress(str(session_id))
                    session_results.append(
                        {"session_id": str(session_id), "warmed": True}
                    )
                except Exception as e:
                    logger.error(f"Failed to warm session {session_id}: {str(e)}")
                    session_results.append(
                        {
                            "session_id": str(session_id),
                            "warmed": False,
                            "error": str(e),
                        }
                    )

            return {
                "user_id": user_id,
                "stats_cached": bool(stats),
                "sessions_warmed": len([r for r in session_results if r["warmed"]]),
                "sessions_total": len(session_results),
                "timestamp": timezone.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error warming dashboard cache for user {user_id}: {str(e)}")
            return {
                "user_id": user_id,
                "error": str(e),
                "timestamp": timezone.now().isoformat(),
            }

    def invalidate_stale_caches(self) -> Dict[str, Any]:
        """
        Clean up stale cache entries for inactive sessions.

        Removes cache entries for sessions that haven't been updated
        in a significant time period to free up memory.

        Returns:
            Dict with cleanup results
        """
        # Lazy import to avoid Django initialization timing issues in Celery
        from apps.review_manager.models import SearchSession

        try:
            # Find stale sessions (not updated in 7 days)
            stale_cutoff = timezone.now() - timedelta(days=7)
            stale_sessions = SearchSession.objects.filter(
                updated_at__lt=stale_cutoff, status__in=["completed", "archived"]
            ).values_list("id", flat=True)

            invalidated_count = 0
            for session_id in stale_sessions:
                try:
                    WorkflowCacheService.invalidate_session(str(session_id))
                    invalidated_count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to invalidate cache for session {session_id}: {str(e)}"
                    )

            logger.info(f"Invalidated cache for {invalidated_count} stale sessions")

            return {
                "stale_sessions_found": len(stale_sessions),
                "invalidated": invalidated_count,
                "timestamp": timezone.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error invalidating stale caches: {str(e)}")
            return {"error": str(e), "timestamp": timezone.now().isoformat()}
