"""
Enhanced caching service for workflow performance optimization.

Provides intelligent caching strategies with automatic warming,
invalidation, and fallback mechanisms for workflow data.
"""

import logging
from typing import Any, Callable, Dict, List

from django.core.cache import caches
from redis.exceptions import ConnectionError as RedisConnectionError

# SearchSession imports moved to method level to avoid circular imports

logger = logging.getLogger(__name__)


class WorkflowCacheService:
    """
    Intelligent caching service for workflow data.

    Features:
    - Multiple TTL strategies based on data volatility
    - Pattern-based cache invalidation
    - Automatic cache warming
    - Graceful fallback on cache failures
    - Structured cache key management
    """

    # Cache TTL configurations (in seconds)
    TTL_SHORT = 60  # 1 minute - rapidly changing data
    TTL_MEDIUM = 300  # 5 minutes - moderate changes
    TTL_LONG = 3600  # 1 hour - slow changing data
    TTL_STATIC = 86400  # 24 hours - static data

    # Cache key prefixes for workflow data
    PREFIX_SESSION = "wf:session"
    PREFIX_STATS = "wf:stats"
    PREFIX_PROGRESS = "wf:progress"
    PREFIX_DASHBOARD = "wf:dashboard"
    PREFIX_MONITORING = "wf:monitor"

    @classmethod
    def _make_key(cls, prefix: str, *args) -> str:
        """
        Generate a structured cache key.

        Args:
            prefix: Cache key prefix
            *args: Additional key components

        Returns:
            str: Formatted cache key
        """
        parts = [prefix] + [str(arg) for arg in args if arg is not None]
        return ":".join(parts)

    @classmethod
    def get_or_set(
        cls,
        key: str,
        func: Callable,
        ttl: int = TTL_MEDIUM,
        cache_alias: str = "default",
    ) -> Any:
        """
        Get value from cache or compute and set it.

        Implements cache-aside pattern with automatic computation
        and error handling.

        Args:
            key: Cache key
            func: Function to compute value if not cached
            ttl: Time to live in seconds
            cache_alias: Cache backend to use

        Returns:
            Cached or computed value
        """
        try:
            # Get safe cache backend with validation
            from apps.core.cache_utils import get_safe_cache

            cache_backend = get_safe_cache()

            if not cache_backend:
                logger.debug(f"No valid cache backend, computing directly for {key}")
                return func()

            value = cache_backend.get(key)

            if value is None:
                logger.debug(f"Cache miss: {key}")
                value = func()
                if value is not None:
                    cache_backend.set(key, value, ttl)
                    logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
            else:
                logger.debug(f"Cache hit: {key}")

            return value

        except Exception as e:
            logger.warning(f"Cache operation failed for {key}: {str(e)}")
            # Fallback to direct computation
            return func()

    @classmethod
    def invalidate_session(cls, session_id: str, cache_alias: str = "default"):
        """
        Invalidate all caches related to a specific session.

        Uses pattern-based deletion for comprehensive cache clearing
        when session data changes.

        Args:
            session_id: UUID of the session
            cache_alias: Cache backend to use
        """
        patterns = [
            f"{cls.PREFIX_SESSION}:{session_id}:*",
            f"{cls.PREFIX_STATS}:{session_id}:*",
            f"{cls.PREFIX_PROGRESS}:{session_id}:*",
            f"{cls.PREFIX_DASHBOARD}:*:session:{session_id}",
        ]

        try:
            cache_backend = caches[cache_alias]

            # Use Redis SCAN for pattern deletion if available
            if hasattr(cache_backend, "_cache") and hasattr(
                cache_backend._cache, "get_client"
            ):
                redis_client = cache_backend._cache.get_client()
                cls._delete_by_pattern(redis_client, patterns)
            else:
                # Fallback for non-Redis backends - this is normal in dev
                logger.debug(
                    "Pattern-based deletion not available for this cache backend (using %s)",
                    type(cache_backend).__name__,
                )

        except Exception as e:
            logger.error(f"Failed to invalidate session cache {session_id}: {str(e)}")

    @classmethod
    def _delete_by_pattern(cls, redis_client, patterns: List[str]):
        """
        Delete Redis keys matching patterns using SCAN.

        More efficient than KEYS for production use.

        Args:
            redis_client: Redis client instance
            patterns: List of key patterns to delete
        """
        for pattern in patterns:
            cursor = 0
            while True:
                try:
                    cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
                    if keys:
                        redis_client.delete(*keys)
                        logger.debug(f"Deleted {len(keys)} keys matching {pattern}")
                    if cursor == 0:
                        break
                except RedisConnectionError:
                    logger.error(
                        f"Redis connection lost during pattern deletion: {pattern}"
                    )
                    break

    @classmethod
    def _compute_executing_progress(cls, session, session_id: str) -> Dict[str, Any]:
        """
        Compute progress for sessions in executing status.

        Args:
            session: SearchSession instance
            session_id: Session UUID

        Returns:
            Dict containing execution progress details
        """
        from apps.serp_execution.models import SearchExecution

        total_queries = session.search_queries_denorm.filter(is_active=True).count()

        if total_queries == 0:
            percentage = 0
            queries_completed = 0
        else:
            completed_queries = (
                SearchExecution.objects.filter(
                    query__session_id=session_id, status="completed"
                )
                .values("query")
                .distinct()
                .count()
            )
            percentage = int((completed_queries / total_queries * 100))
            queries_completed = completed_queries

        return {
            "status": session.status,
            "percentage": percentage,
            "queries_completed": queries_completed,
            "queries_total": total_queries,
            "last_updated": session.updated_at.isoformat(),
            "execution_details": {
                "started_at": (
                    session.started_at.isoformat() if session.started_at else None
                ),
                "estimated_completion": None,
            },
        }

    @classmethod
    def _compute_processing_progress(cls, session) -> Dict[str, Any]:
        """
        Compute progress for sessions processing results.

        Args:
            session: SearchSession instance

        Returns:
            Dict containing processing progress details
        """
        return {
            "status": session.status,
            "percentage": 60,  # Base percentage for this stage
            "results_found": session.total_results,
            "results_processed": getattr(session, "processed_results_count", 0),
            "last_updated": session.updated_at.isoformat(),
        }

    @classmethod
    def _compute_review_progress(cls, session) -> Dict[str, Any]:
        """
        Compute progress for sessions under review.

        Args:
            session: SearchSession instance

        Returns:
            Dict containing review progress details
        """
        percentage = (
            session.progress_percentage
            if hasattr(session, "progress_percentage")
            else 0
        )
        return {
            "status": session.status,
            "percentage": int(percentage),
            "reviewed": session.reviewed_results,
            "total": session.total_results,
            "included": session.included_results,
            "last_updated": session.updated_at.isoformat(),
        }

    @classmethod
    def _compute_simple_progress(cls, session) -> Dict[str, Any]:
        """
        Compute progress for sessions in simple states.

        Args:
            session: SearchSession instance

        Returns:
            Dict containing basic progress information
        """
        progress_map = {
            "draft": 0,
            "defining_search": 10,
            "ready_to_execute": 20,
            "ready_for_review": 80,
            "completed": 100,
            "archived": 100,
        }
        return {
            "status": session.status,
            "percentage": progress_map.get(session.status, 0),
            "last_updated": session.updated_at.isoformat(),
        }

    @classmethod
    def _determine_progress_ttl(cls, session_id: str) -> int:
        """
        Determine appropriate cache TTL based on session status.

        Args:
            session_id: Session UUID

        Returns:
            Cache TTL in seconds
        """
        from apps.review_manager.models import SearchSession

        try:
            session = SearchSession.objects.only("status").get(id=session_id)
            if session.status in ["completed", "archived"]:
                return cls.TTL_LONG
        except (SearchSession.DoesNotExist, Exception):
            pass
        return cls.TTL_SHORT

    @classmethod
    def get_session_progress(cls, session_id: str) -> Dict[str, Any]:
        """
        Get cached session progress data with automatic computation.

        Provides detailed progress information including:
        - Current status
        - Completion percentage
        - Query execution progress
        - Last update timestamp

        Args:
            session_id: UUID of the session

        Returns:
            Dict containing progress information
        """
        from apps.review_manager.models import SearchSession

        key = cls._make_key(cls.PREFIX_PROGRESS, session_id)

        def compute():
            try:
                session = SearchSession.objects.select_related("search_strategy").get(
                    id=session_id
                )

                # Calculate detailed progress based on status
                if session.status == "executing":
                    return cls._compute_executing_progress(session, session_id)
                elif session.status == "processing_results":
                    return cls._compute_processing_progress(session)
                elif session.status == "under_review":
                    return cls._compute_review_progress(session)
                else:
                    return cls._compute_simple_progress(session)

            except SearchSession.DoesNotExist:
                return {
                    "status": "not_found",
                    "percentage": 0,
                    "error": "Session not found",
                }
            except Exception as e:
                logger.error(
                    f"Error computing session progress for {session_id}: {str(e)}"
                )
                return {"status": "error", "percentage": 0, "error": str(e)}

        ttl = cls._determine_progress_ttl(session_id)
        return cls.get_or_set(key, compute, ttl)

    @classmethod
    def get_dashboard_stats(cls, user_id: str) -> Dict[str, Any]:
        """
        Get cached dashboard statistics for a user.

        Aggregates session statistics with single query.

        Args:
            user_id: User UUID

        Returns:
            Dict containing dashboard statistics
        """
        key = cls._make_key(cls.PREFIX_DASHBOARD, "stats", user_id)

        def compute():
            from apps.review_manager.models import SearchSession

            return SearchSession.objects.get_status_summary(user=user_id)

        return cls.get_or_set(key, compute, cls.TTL_MEDIUM)

    @classmethod
    def invalidate_user_dashboard(cls, user_id: str):
        """
        Invalidate all dashboard caches for a user.

        Called when user creates/modifies sessions.

        Args:
            user_id: User UUID
        """
        patterns = [
            f"{cls.PREFIX_DASHBOARD}:*:user:{user_id}",
            f"{cls.PREFIX_STATS}:user:{user_id}:*",
        ]

        try:
            cache_backend = caches["default"]
            if hasattr(cache_backend, "_cache") and hasattr(
                cache_backend._cache, "get_client"
            ):
                redis_client = cache_backend._cache.get_client()
                cls._delete_by_pattern(redis_client, patterns)
            else:
                # Fallback for non-Redis backends - this is normal in dev
                logger.debug(
                    "Pattern-based deletion not available for this cache backend (using %s)",
                    type(cache_backend).__name__,
                )
        except Exception as e:
            logger.error(
                f"Failed to invalidate user dashboard cache {user_id}: {str(e)}"
            )

    @classmethod
    def get_session_details(
        cls, session_id: str, include_activities: bool = True
    ) -> Dict[str, Any]:
        """
        Get comprehensive session details with related data.

        Optimized for detail views with prefetched relationships.

        Args:
            session_id: Session UUID
            include_activities: Whether to include recent activities

        Returns:
            Dict containing session details
        """
        key = cls._make_key(
            cls.PREFIX_SESSION,
            session_id,
            "details",
            "with_activities" if include_activities else "basic",
        )

        def compute():
            from apps.review_manager.models import SearchSession

            queryset = SearchSession.objects.select_related("owner", "search_strategy")

            if include_activities:
                queryset = queryset.prefetch_related("activities__user")

            try:
                session = queryset.get(id=session_id)

                data = {
                    "id": str(session.id),
                    "title": session.title,
                    "description": session.description,
                    "status": session.status,
                    "status_display": session.get_status_display(),
                    "owner": {
                        "id": str(session.owner.id),
                        "username": session.owner.username,
                        "email": session.owner.email,
                    },
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "statistics": {
                        "total_queries": session.total_queries,
                        "total_results": session.total_results,
                        "reviewed_results": session.reviewed_results,
                        "included_results": session.included_results,
                        "progress_percentage": getattr(
                            session, "progress_percentage", 0
                        ),
                        "inclusion_rate": getattr(session, "inclusion_rate", 0),
                    },
                }

                if include_activities:
                    data["recent_activities"] = [
                        {
                            "id": str(activity.id),
                            "type": activity.activity_type,
                            "type_display": activity.get_activity_type_display(),
                            "description": activity.description,
                            "user": (
                                activity.user.username if activity.user else "System"
                            ),
                            "created_at": activity.created_at.isoformat(),
                        }
                        for activity in session.activities.all()[:10]
                    ]

                return data

            except SearchSession.DoesNotExist:
                return None

        ttl = cls.TTL_MEDIUM
        return cls.get_or_set(key, compute, ttl)
