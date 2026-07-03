"""
Tests for the WorkflowCacheService.

Tests caching functionality including:
- Cache operations (get_or_set, invalidate)
- TTL strategies
- Session progress and dashboard stats
- Error handling
"""

from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.cache_utils import reset_cache_validation
from apps.core.services.cache_service import WorkflowCacheService
from apps.review_manager.models import SearchSession
from apps.core.tests.utils import create_test_user

User = get_user_model()


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
)
class WorkflowCacheServiceTests(TestCase):
    """Test WorkflowCacheService functionality."""

    def setUp(self):
        """Set up test data."""
        # Reset global cache validation state so override_settings takes effect
        reset_cache_validation()
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )
        # Clear cache before each test
        cache.clear()

    def test_get_or_set_cache_miss(self):
        """Test get_or_set when cache miss occurs."""

        def expensive_function():
            return {"data": "expensive result"}

        result = WorkflowCacheService.get_or_set(
            "miss_test_key", expensive_function, ttl=60
        )

        self.assertEqual(result, {"data": "expensive result"})

    def test_get_or_set_cache_hit(self):
        """Test get_or_set when cache hit occurs."""
        # First call populates the cache
        WorkflowCacheService.get_or_set("test_key", lambda: {"data": "cached"}, ttl=60)

        # Second call with different function should return cached value
        expensive_function = MagicMock(return_value={"data": "new"})

        result = WorkflowCacheService.get_or_set("test_key", expensive_function, ttl=60)

        self.assertEqual(result, {"data": "cached"})
        expensive_function.assert_not_called()

    def test_invalidate_session(self):
        """Test session cache invalidation (pattern-based)."""
        session_id = str(self.session.id)

        # With LocMemCache, pattern-based deletion is not available
        # but the method should not crash
        WorkflowCacheService.invalidate_session(session_id)
        # No exception = success

    def test_get_session_progress(self):
        """Test getting session progress data."""
        session_id = str(self.session.id)

        progress = WorkflowCacheService.get_session_progress(session_id)

        self.assertIsNotNone(progress)
        self.assertEqual(progress["status"], "draft")
        self.assertEqual(progress["percentage"], 0)

    def test_get_dashboard_stats(self):
        """Test getting dashboard stats for a user."""
        stats = WorkflowCacheService.get_dashboard_stats(str(self.user.id))

        # Should return some stats dict
        self.assertIsNotNone(stats)

    def test_ttl_strategies(self):
        """Test different TTL strategy constants exist."""
        self.assertEqual(WorkflowCacheService.TTL_SHORT, 60)
        self.assertEqual(WorkflowCacheService.TTL_MEDIUM, 300)
        self.assertEqual(WorkflowCacheService.TTL_LONG, 3600)
        self.assertEqual(WorkflowCacheService.TTL_STATIC, 86400)

    def test_error_handling(self):
        """Test error handling in cache operations."""

        # Test with function that raises exception
        def failing_function():
            raise ValueError("Test error")

        # get_or_set falls back to func() on cache error, but if func itself
        # raises, it propagates through the fallback too
        with self.assertRaises(ValueError):
            WorkflowCacheService.get_or_set("error_key", failing_function, ttl=60)

    def test_make_key(self):
        """Test cache key generation with prefixes."""
        key = WorkflowCacheService._make_key("wf:session", "abc123", "details")
        self.assertEqual(key, "wf:session:abc123:details")

        key2 = WorkflowCacheService._make_key("wf:stats", "user1")
        self.assertEqual(key2, "wf:stats:user1")

    def test_get_session_details(self):
        """Test getting comprehensive session details."""
        session_id = str(self.session.id)

        details = WorkflowCacheService.get_session_details(session_id)

        self.assertIsNotNone(details)
        self.assertEqual(details["title"], "Test Session")
        self.assertEqual(details["status"], "draft")
        self.assertIn("owner", details)
        self.assertEqual(details["owner"]["username"], self.user.username)


class WorkflowCacheServiceIntegrationTests(TestCase):
    """Integration tests for cache service with real models."""

    def setUp(self):
        """Set up test data."""
        reset_cache_validation()
        self.user = create_test_user()
        cache.clear()

    def test_concurrent_cache_access(self):
        """Test concurrent access to cache."""
        import time
        from threading import Thread

        call_count = 0

        def slow_function():
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)
            return {"count": call_count}

        results = []

        def worker():
            result = WorkflowCacheService.get_or_set(
                "concurrent_key", slow_function, ttl=60
            )
            results.append(result)

        threads = []
        for _ in range(5):
            t = Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All threads should get a result
        self.assertEqual(len(results), 5)

    def test_invalidate_session_cache_with_locmem(self):
        """Test invalidate_session works with LocMemCache backend."""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )
        session_id = str(session.id)

        # With LocMemCache, pattern deletion is not available
        # Should log at DEBUG level and not crash
        WorkflowCacheService.invalidate_session(session_id)
        # No exception = success

    def test_invalidate_user_dashboard_with_locmem(self):
        """Test user dashboard invalidation with LocMemCache."""
        user_id = str(self.user.id)

        # Should not crash with LocMemCache backend
        WorkflowCacheService.invalidate_user_dashboard(user_id)
        # No exception = success
