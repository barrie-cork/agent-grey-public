"""
Optimised caching for long-duration review sessions.

This service implements intelligent caching strategies for review sessions to reduce
database load during the manual review phase, which typically lasts weeks or months.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class ReviewCacheManager:
    """Optimised caching for long-duration review sessions"""

    # Cache TTL configurations
    REVIEW_SESSION_TTL = 3600 * 4  # 4 hours for active review sessions
    DORMANT_SESSION_TTL = 3600 * 24  # 24 hours for inactive sessions
    REVIEW_PROGRESS_TTL = 3600  # 1 hour for review progress data
    RESULTS_SUMMARY_TTL = 3600 * 2  # 2 hours for results summaries

    # Cache key prefixes
    KEY_PREFIX_SESSION = "review_session"
    KEY_PREFIX_PROGRESS = "review_progress"
    KEY_PREFIX_SUMMARY = "results_summary"
    KEY_PREFIX_ACTIVITY = "review_activity"

    @classmethod
    def get_session_cache_key(cls, session_id: str) -> str:
        """Generate cache key for review session data."""
        return f"{cls.KEY_PREFIX_SESSION}:{session_id}"

    @classmethod
    def get_progress_cache_key(cls, session_id: str) -> str:
        """Generate cache key for review progress."""
        return f"{cls.KEY_PREFIX_PROGRESS}:{session_id}"

    @classmethod
    def get_summary_cache_key(cls, session_id: str) -> str:
        """Generate cache key for results summary."""
        return f"{cls.KEY_PREFIX_SUMMARY}:{session_id}"

    @classmethod
    def get_activity_cache_key(cls, session_id: str) -> str:
        """Generate cache key for review activity timestamp."""
        return f"{cls.KEY_PREFIX_ACTIVITY}:{session_id}"

    @classmethod
    def cache_review_session(cls, session, force_refresh: bool = False) -> str:
        """
        Cache review session data with intelligent TTL.

        Args:
            session: SearchSession object
            force_refresh: Force cache refresh regardless of existing data

        Returns:
            Cache key where data was stored
        """
        session_id = str(session.id)
        cache_key = cls.get_session_cache_key(session_id)

        # Check if already cached and not forcing refresh
        if not force_refresh and cache.get(cache_key) is not None:
            logger.debug(f"Review session {session_id} already cached")
            return cache_key

        try:
            # Determine session activity level
            last_activity = cls._get_review_activity(session)
            ttl = cls._calculate_ttl(last_activity)

            # Build cache data
            cache_data = {
                "session_id": session_id,
                "title": session.title,
                "status": session.status,
                "total_results": session.total_results,
                "reviewed_results": session.reviewed_results,
                "included_results": session.included_results,
                "last_cached": timezone.now().isoformat(),
                "cache_ttl": ttl,
            }

            # Store in cache
            cache.set(cache_key, cache_data, timeout=ttl)

            logger.info(
                f"Cached review session {session_id} with TTL {ttl}s "
                f"(activity: {last_activity})"
            )

            return cache_key

        except Exception as e:
            logger.error(f"Failed to cache review session {session_id}: {e}")
            return cache_key

    @classmethod
    def cache_review_progress(cls, session) -> Optional[Dict[str, Any]]:
        """
        Cache review progress data.

        Args:
            session: SearchSession object

        Returns:
            Cached progress data or None if caching failed
        """
        session_id = str(session.id)
        cache_key = cls.get_progress_cache_key(session_id)

        try:
            progress_data = {
                "session_id": session_id,
                "progress_percentage": session.progress_percentage,
                "reviewed_results": session.reviewed_results,
                "total_results": session.total_results,
                "included_results": session.included_results,
                "inclusion_rate": session.inclusion_rate,
                "last_updated": timezone.now().isoformat(),
            }

            cache.set(cache_key, progress_data, timeout=cls.REVIEW_PROGRESS_TTL)

            logger.debug(f"Cached review progress for session {session_id}")

            return progress_data

        except Exception as e:
            logger.error(f"Failed to cache review progress for {session_id}: {e}")
            return None

    @classmethod
    def get_cached_review_session(cls, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached review session data.

        Args:
            session_id: UUID of the session

        Returns:
            Cached session data or None if not cached
        """
        cache_key = cls.get_session_cache_key(session_id)
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.debug(f"Cache hit for review session {session_id}")
        else:
            logger.debug(f"Cache miss for review session {session_id}")

        return cached_data

    @classmethod
    def get_cached_review_progress(cls, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached review progress data.

        Args:
            session_id: UUID of the session

        Returns:
            Cached progress data or None if not cached
        """
        cache_key = cls.get_progress_cache_key(session_id)
        return cache.get(cache_key)

    @classmethod
    def invalidate_review_cache(cls, session_id: str) -> None:
        """
        Invalidate all cached data for a review session.

        Args:
            session_id: UUID of the session
        """
        try:
            cache_keys = [
                cls.get_session_cache_key(session_id),
                cls.get_progress_cache_key(session_id),
                cls.get_summary_cache_key(session_id),
                cls.get_activity_cache_key(session_id),
            ]

            for key in cache_keys:
                cache.delete(key)

            logger.info(f"Invalidated all cache for review session {session_id}")

        except Exception as e:
            logger.error(f"Failed to invalidate cache for {session_id}: {e}")

    @classmethod
    def update_review_activity(cls, session_id: str) -> None:
        """
        Update the last review activity timestamp.

        This is called when a user makes a review decision, indicating active review.

        Args:
            session_id: UUID of the session
        """
        cache_key = cls.get_activity_cache_key(session_id)
        cache.set(cache_key, timezone.now(), timeout=cls.DORMANT_SESSION_TTL)

        logger.debug(f"Updated review activity for session {session_id}")

    @classmethod
    def _get_review_activity(cls, session) -> Optional[timedelta]:
        """
        Get time since last review activity.

        Args:
            session: SearchSession object

        Returns:
            Timedelta since last activity or None if no activity recorded
        """
        session_id = str(session.id)
        cache_key = cls.get_activity_cache_key(session_id)
        last_activity = cache.get(cache_key)

        if last_activity:
            return timezone.now() - last_activity

        # Check database for recent review decisions
        try:
            from apps.review_results.models import SimpleReviewDecision

            latest_decision = (
                SimpleReviewDecision.objects.filter(session=session)
                .order_by("-created_at")
                .values_list("created_at", flat=True)
                .first()
            )

            if latest_decision:
                time_since = timezone.now() - latest_decision
                # Cache this for future checks
                cache.set(cache_key, latest_decision, timeout=cls.DORMANT_SESSION_TTL)
                return time_since

        except Exception as e:
            logger.warning(f"Could not retrieve review activity: {e}")

        return None

    @classmethod
    def _calculate_ttl(cls, last_activity: Optional[timedelta]) -> int:
        """
        Calculate appropriate TTL based on activity level.

        Args:
            last_activity: Timedelta since last activity

        Returns:
            TTL in seconds
        """
        if last_activity is None:
            # No activity recorded, use long TTL
            return cls.DORMANT_SESSION_TTL

        # Active within 2 hours: short TTL
        if last_activity < timedelta(hours=2):
            return cls.REVIEW_SESSION_TTL

        # Dormant: long TTL
        return cls.DORMANT_SESSION_TTL

    @classmethod
    def cache_results_summary(cls, session) -> Optional[Dict[str, Any]]:
        """
        Cache results summary for a review session.

        Args:
            session: SearchSession object

        Returns:
            Cached summary data or None if caching failed
        """
        session_id = str(session.id)
        cache_key = cls.get_summary_cache_key(session_id)

        try:
            from django.db.models import Count

            from apps.results_manager.models import ProcessedResult

            # Get result counts by domain using aggregation (avoid N+1)
            domain_counts = list(
                ProcessedResult.objects.filter(session=session)
                .values("domain")
                .annotate(count=Count("domain"))
                .order_by("-count")[:10]
            )

            # Convert to format expected by consumers
            top_domains = [(d["domain"], d["count"]) for d in domain_counts]

            summary_data = {
                "session_id": session_id,
                "total_results": session.total_results,
                "unique_domains": ProcessedResult.objects.filter(session=session)
                .values("domain")
                .distinct()
                .count(),
                "top_domains": top_domains,
                "last_updated": timezone.now().isoformat(),
            }

            cache.set(cache_key, summary_data, timeout=cls.RESULTS_SUMMARY_TTL)

            logger.debug(f"Cached results summary for session {session_id}")

            return summary_data

        except Exception as e:
            logger.error(f"Failed to cache results summary for {session_id}: {e}")
            return None

    @classmethod
    def get_cached_results_summary(cls, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached results summary.

        Args:
            session_id: UUID of the session

        Returns:
            Cached summary data or None if not cached
        """
        cache_key = cls.get_summary_cache_key(session_id)
        return cache.get(cache_key)

    @classmethod
    def warm_review_cache(cls, session) -> Dict[str, bool]:
        """
        Warm the cache for a review session by pre-loading all relevant data.

        This should be called when a session transitions to under_review status.

        Args:
            session: SearchSession object

        Returns:
            Dictionary indicating which caches were successfully warmed
        """
        session_id = str(session.id)

        results = {
            "session_data": False,
            "progress_data": False,
            "results_summary": False,
        }

        try:
            # Cache session data
            cls.cache_review_session(session, force_refresh=True)
            results["session_data"] = True

            # Cache progress data
            if cls.cache_review_progress(session) is not None:
                results["progress_data"] = True

            # Cache results summary
            if cls.cache_results_summary(session) is not None:
                results["results_summary"] = True

            logger.info(
                f"Warmed cache for review session {session_id}: "
                f"{sum(results.values())}/3 successful"
            )

        except Exception as e:
            logger.error(f"Failed to warm cache for session {session_id}: {e}")

        return results

    @classmethod
    def get_cache_statistics(cls) -> Dict[str, Any]:
        """
        Get statistics about review cache usage.

        Returns:
            Dictionary with cache statistics
        """
        try:
            # This would need Redis introspection for detailed stats
            # For now, return basic configuration info
            return {
                "review_session_ttl": cls.REVIEW_SESSION_TTL,
                "dormant_session_ttl": cls.DORMANT_SESSION_TTL,
                "review_progress_ttl": cls.REVIEW_PROGRESS_TTL,
                "results_summary_ttl": cls.RESULTS_SUMMARY_TTL,
                "timestamp": timezone.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get cache statistics: {e}")
            return {"error": str(e), "timestamp": timezone.now().isoformat()}
