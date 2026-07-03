"""
Tests for ReviewCacheManager service.

Tests intelligent caching strategies for review sessions.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.services.review_cache_manager import ReviewCacheManager
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ReviewCacheManagerTest(TestCase):
    """Test ReviewCacheManager caching strategies"""

    def setUp(self):
        """Set up test data"""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            status="under_review",
            total_results=100,
            reviewed_results=50,
            included_results=30,
        )

        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests"""
        cache.clear()

    def test_cache_review_session_with_activity(self):
        """Test caching session with recent activity"""
        # Set recent activity
        ReviewCacheManager.update_review_activity(str(self.session.id))

        # Cache session
        cache_key = ReviewCacheManager.cache_review_session(self.session)

        # Verify cached
        cached_data = cache.get(cache_key)
        self.assertIsNotNone(cached_data)
        self.assertEqual(cached_data["session_id"], str(self.session.id))
        self.assertEqual(cached_data["title"], self.session.title)
        self.assertEqual(cached_data["total_results"], 100)

    def test_cache_review_session_force_refresh(self):
        """Test force refresh overwrites existing cache"""
        # Cache session first time
        cache_key = ReviewCacheManager.cache_review_session(self.session)
        cached_data1 = cache.get(cache_key)
        first_cached_time = cached_data1["last_cached"]

        # Update session
        self.session.reviewed_results = 60
        self.session.save()

        # Cache again with force refresh
        ReviewCacheManager.cache_review_session(self.session, force_refresh=True)
        cached_data2 = cache.get(cache_key)

        # Should be updated
        self.assertEqual(cached_data2["reviewed_results"], 60)
        self.assertNotEqual(cached_data2["last_cached"], first_cached_time)

    def test_cache_review_progress(self):
        """Test caching review progress data"""
        # Cache progress
        progress_data = ReviewCacheManager.cache_review_progress(self.session)

        # Verify structure
        self.assertIsNotNone(progress_data)
        assert progress_data is not None
        self.assertEqual(progress_data["session_id"], str(self.session.id))
        self.assertEqual(
            progress_data["progress_percentage"], self.session.progress_percentage
        )
        self.assertEqual(progress_data["reviewed_results"], 50)
        self.assertEqual(progress_data["total_results"], 100)

    def test_get_cached_review_session_hit(self):
        """Test cache hit for review session"""
        # Cache session
        ReviewCacheManager.cache_review_session(self.session)

        # Retrieve from cache
        cached_data = ReviewCacheManager.get_cached_review_session(str(self.session.id))

        # Should be cache hit
        self.assertIsNotNone(cached_data)
        assert cached_data is not None
        self.assertEqual(cached_data["session_id"], str(self.session.id))

    def test_get_cached_review_session_miss(self):
        """Test cache miss for review session"""
        # Don't cache anything
        cached_data = ReviewCacheManager.get_cached_review_session(str(self.session.id))

        # Should be cache miss
        self.assertIsNone(cached_data)

    def test_get_cached_review_progress(self):
        """Test retrieving cached progress"""
        # Cache progress
        ReviewCacheManager.cache_review_progress(self.session)

        # Retrieve
        progress = ReviewCacheManager.get_cached_review_progress(str(self.session.id))

        # Verify
        self.assertIsNotNone(progress)
        assert progress is not None
        self.assertEqual(progress["session_id"], str(self.session.id))

    def test_invalidate_review_cache(self):
        """Test cache invalidation"""
        # Cache multiple items
        ReviewCacheManager.cache_review_session(self.session)
        ReviewCacheManager.cache_review_progress(self.session)
        ReviewCacheManager.update_review_activity(str(self.session.id))

        # Verify all cached
        self.assertIsNotNone(
            ReviewCacheManager.get_cached_review_session(str(self.session.id))
        )
        self.assertIsNotNone(
            ReviewCacheManager.get_cached_review_progress(str(self.session.id))
        )

        # Invalidate all
        ReviewCacheManager.invalidate_review_cache(str(self.session.id))

        # Verify all cleared
        self.assertIsNone(
            ReviewCacheManager.get_cached_review_session(str(self.session.id))
        )
        self.assertIsNone(
            ReviewCacheManager.get_cached_review_progress(str(self.session.id))
        )

    def test_update_review_activity(self):
        """Test updating review activity timestamp"""
        session_id = str(self.session.id)

        # Update activity
        ReviewCacheManager.update_review_activity(session_id)

        # Verify cached
        cache_key = ReviewCacheManager.get_activity_cache_key(session_id)
        activity_time = cache.get(cache_key)

        self.assertIsNotNone(activity_time)
        self.assertIsInstance(activity_time, timezone.datetime)

    def test_calculate_ttl_recent_activity(self):
        """Test TTL calculation with recent activity"""
        # Recent activity (within 2 hours)
        recent_activity = timedelta(hours=1)

        ttl = ReviewCacheManager._calculate_ttl(recent_activity)

        # Should use short TTL
        self.assertEqual(ttl, ReviewCacheManager.REVIEW_SESSION_TTL)

    def test_calculate_ttl_dormant_activity(self):
        """Test TTL calculation with dormant activity"""
        # Dormant activity (> 2 hours)
        dormant_activity = timedelta(hours=25)

        ttl = ReviewCacheManager._calculate_ttl(dormant_activity)

        # Should use long TTL
        self.assertEqual(ttl, ReviewCacheManager.DORMANT_SESSION_TTL)

    def test_calculate_ttl_no_activity(self):
        """Test TTL calculation with no activity"""
        ttl = ReviewCacheManager._calculate_ttl(None)

        # Should use long TTL
        self.assertEqual(ttl, ReviewCacheManager.DORMANT_SESSION_TTL)

    def test_warm_review_cache(self):
        """Test cache warming for review session"""
        # Warm cache
        results = ReviewCacheManager.warm_review_cache(self.session)

        # Verify all caches warmed
        self.assertTrue(results["session_data"])
        self.assertTrue(results["progress_data"])

        # Verify data is actually cached
        self.assertIsNotNone(
            ReviewCacheManager.get_cached_review_session(str(self.session.id))
        )
        self.assertIsNotNone(
            ReviewCacheManager.get_cached_review_progress(str(self.session.id))
        )

    def test_cache_results_summary(self):
        """Test caching results summary"""
        # Create some test results
        ProcessedResult.objects.create(
            session=self.session,
            title="Result 1",
            url="https://example.com/1",
            domain="example.com",
            snippet="Test snippet 1",
        )
        ProcessedResult.objects.create(
            session=self.session,
            title="Result 2",
            url="https://test.com/2",
            domain="test.com",
            snippet="Test snippet 2",
        )

        # Cache summary
        summary = ReviewCacheManager.cache_results_summary(self.session)

        # Verify summary structure
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["session_id"], str(self.session.id))
        self.assertEqual(summary["total_results"], 100)
        self.assertGreater(summary["unique_domains"], 0)

    def test_get_cached_results_summary(self):
        """Test retrieving cached results summary"""
        # Create result
        ProcessedResult.objects.create(
            session=self.session,
            title="Result 1",
            url="https://example.com/1",
            domain="example.com",
            snippet="Test snippet",
        )

        # Cache summary
        ReviewCacheManager.cache_results_summary(self.session)

        # Retrieve
        summary = ReviewCacheManager.get_cached_results_summary(str(self.session.id))

        # Verify
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["session_id"], str(self.session.id))

    def test_get_cache_statistics(self):
        """Test retrieving cache statistics"""
        stats = ReviewCacheManager.get_cache_statistics()

        # Verify structure
        self.assertIn("review_session_ttl", stats)
        self.assertIn("dormant_session_ttl", stats)
        self.assertIn("review_progress_ttl", stats)
        self.assertIn("results_summary_ttl", stats)
        self.assertIn("timestamp", stats)

        # Verify values
        self.assertEqual(
            stats["review_session_ttl"], ReviewCacheManager.REVIEW_SESSION_TTL
        )
        self.assertEqual(
            stats["dormant_session_ttl"], ReviewCacheManager.DORMANT_SESSION_TTL
        )

    def test_cache_key_generation(self):
        """Test cache key generation methods"""
        session_id = str(self.session.id)

        # Test all key generators
        session_key = ReviewCacheManager.get_session_cache_key(session_id)
        progress_key = ReviewCacheManager.get_progress_cache_key(session_id)
        summary_key = ReviewCacheManager.get_summary_cache_key(session_id)
        activity_key = ReviewCacheManager.get_activity_cache_key(session_id)

        # Verify all unique
        keys = {session_key, progress_key, summary_key, activity_key}
        self.assertEqual(len(keys), 4)

        # Verify format
        self.assertTrue(session_key.startswith("review_session:"))
        self.assertTrue(progress_key.startswith("review_progress:"))
        self.assertTrue(summary_key.startswith("results_summary:"))
        self.assertTrue(activity_key.startswith("review_activity:"))
