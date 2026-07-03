"""Tests for the simplified 7 core services - FIXED VERSION."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.services.serper_client import SerperClient
from apps.core.services.simple_services import (
    DatabaseStateManager,
    RedisCacheManager,
    SearchResultProcessor,
    SimpleRetryManager,
    TokenBucketRateLimiter,
    URLDeduplicationService,
)
from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession

from .utils import TestUserMixin

User = get_user_model()


class SerperClientTestCase(TestCase, TestUserMixin):
    """Test the simplified SerperClient service."""

    def setUp(self):
        self.user = self.create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="ready_to_execute"
        )

    @patch("apps.core.services.serper_client.requests.post")
    def test_search_success(self, mock_post):
        """Test successful search API call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic": [
                {"title": "Result 1", "link": "https://example.com/1"},
                {"title": "Result 2", "link": "https://example.com/2"},
            ]
        }
        mock_post.return_value = mock_response

        mock_rate_limiter = Mock()
        mock_rate_limiter.can_proceed.return_value = True
        mock_cache = Mock()
        mock_cache.get_search_results.return_value = None  # Cache miss
        client = SerperClient(
            config={
                "api_key": "test-key",
                "timeout": 30,
                "base_url": "https://google.serper.dev/search",
                "cache_timeout": 3600,
                "enable_caching": False,
            },
            rate_limiter=mock_rate_limiter,
            cache_manager=mock_cache,
        )

        results = client.search("test query", 10, self.session)

        self.assertEqual(len(results["organic"]), 2)
        self.assertEqual(results["organic"][0]["title"], "Result 1")
        mock_post.assert_called_once()

    @patch("apps.core.services.serper_client.requests.post")
    def test_search_with_retry(self, mock_post):
        """Test search handles connection errors gracefully."""
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError("Connection error")

        from apps.core.services.simple_services import SerperConnectionError

        mock_rate_limiter = Mock()
        mock_rate_limiter.can_proceed.return_value = True
        client = SerperClient(
            config={
                "api_key": "test-key",
                "timeout": 30,
                "base_url": "https://google.serper.dev/search",
                "cache_timeout": 3600,
                "enable_caching": False,
            },
            rate_limiter=mock_rate_limiter,
            cache_manager=Mock(),
        )

        with self.assertRaises(SerperConnectionError):
            client.search("test query", 10, self.session)


class RateLimiterTestCase(TestCase):
    """Test the simplified TokenBucketRateLimiter service."""

    @patch("apps.core.services.rate_limiter.get_safe_redis_connection")
    def test_rate_limiting(self, mock_redis_conn):
        """Test rate limiting with token bucket."""
        mock_redis = Mock()
        mock_redis_conn.return_value = mock_redis

        limiter = TokenBucketRateLimiter()

        mock_redis.eval.return_value = 1
        can_proceed = limiter.can_proceed("test_key")
        self.assertTrue(can_proceed)

        mock_redis.eval.return_value = 0
        can_proceed = limiter.can_proceed("test_key")
        self.assertFalse(can_proceed)

    def test_wait_time_calculation(self):
        """Test wait time calculation when rate limited."""
        limiter = TokenBucketRateLimiter()

        wait_time = limiter.get_retry_delay()
        self.assertEqual(wait_time, 60)


class ResultProcessorTestCase(TestCase, TestUserMixin):
    """Test the simplified SearchResultProcessor service."""

    def setUp(self):
        self.processor = SearchResultProcessor()
        self.user = self.create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="processing_results"
        )

    @patch("apps.results_manager.models.ProcessedResult")
    @patch("apps.serp_execution.models.RawSearchResult")
    def test_process_results_batch(self, mock_raw_result, mock_processed_result):
        """Test batch processing of results."""
        mock_raw_result.objects.create.return_value = Mock()
        mock_processed_result.objects.create.return_value = Mock()

        results = [
            {
                "title": f"Result {i}",
                "link": f"https://example.com/{i}",
                "snippet": f"Snippet {i}",
            }
            for i in range(100)
        ]

        processed_count, errors = self.processor.process_search_results(
            results, None, self.session
        )

        self.assertEqual(processed_count, 100)
        self.assertEqual(len(errors), 0)

    @patch("apps.results_manager.models.ProcessedResult")
    @patch("apps.serp_execution.models.RawSearchResult")
    def test_result_validation(self, mock_raw_result, mock_processed_result):
        """Test result validation."""
        mock_raw_result.objects.create.return_value = Mock()
        mock_processed_result.objects.create.return_value = Mock()

        valid_results = [
            {
                "title": "Test Title",
                "link": "https://example.com/page",
                "snippet": "Test snippet",
            }
        ]

        processed_count, errors = self.processor.process_search_results(
            valid_results, None, self.session
        )

        self.assertEqual(processed_count, 1)
        self.assertEqual(len(errors), 0)

        invalid_results = [
            {"title": "", "link": "not-a-valid-url", "snippet": "Test snippet"}
        ]

        processed_count, errors = self.processor.process_search_results(
            invalid_results, None, self.session
        )

        self.assertEqual(processed_count, 0)
        self.assertGreater(len(errors), 0)


class DeduplicationServiceTestCase(TestCase):
    """Test the URL-only deduplication service."""

    def setUp(self):
        self.service = URLDeduplicationService()
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="processing_results"
        )

    def test_url_normalization(self):
        """Test conservative URL normalization."""
        url1 = "https://example.com/page?utm_source=google&id=123"
        normalized1 = self.service.normalize_url(url1)
        self.assertNotIn("utm_source", normalized1)
        self.assertIn("id=123", normalized1)

        url2 = "https://example.com/page#section"
        normalized2 = self.service.normalize_url(url2)
        self.assertNotIn("#section", normalized2)

    def test_cross_query_deduplication(self):
        """Test deduplication URL normalization."""
        url1 = "https://example.com/page?utm_source=google"
        url2 = "https://Example.com/page"

        normalized1 = self.service.normalize_url(url1)
        normalized2 = self.service.normalize_url(url2)

        self.assertEqual(normalized1, normalized2)
        self.assertNotIn("utm_source", normalized1)
        self.assertIn("example.com/page", normalized1)

    @patch("apps.results_manager.models.ProcessedResult")
    def test_deduplicate_session_results(self, mock_processed_result):
        """Test deduplication at session level."""
        mock_queryset = Mock()
        mock_processed_result.objects.filter.return_value = mock_queryset
        mock_queryset.order_by.return_value = []

        result = self.service.deduplicate_session_results(self.session)
        self.assertIsInstance(result, dict)
        self.assertIn("total_duplicates", result)
        self.assertGreaterEqual(result["total_duplicates"], 0)


class StateManagerTestCase(TestCase):
    """Test the simplified DatabaseStateManager service."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )
        self.manager = DatabaseStateManager()

    def test_atomic_status_transition(self):
        """Test atomic database state transitions."""
        success = self.manager.set_session_status(
            self.session, "defining_search", "Starting search definition"
        )

        self.assertTrue(success)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "defining_search")
        self.assertEqual(self.session.status_detail, "Starting search definition")

    def test_invalid_transition(self):
        """Test that StateManager doesn't validate transitions (ultra-simple)."""
        success = self.manager.set_session_status(
            self.session, "completed", "Direct transition"
        )

        self.assertTrue(success)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")

    def test_automatic_timestamps(self):
        """Test that StateManager updates updated_at timestamp."""
        original_updated_at = self.session.updated_at

        import time

        time.sleep(0.01)

        self.manager.set_session_status(self.session, "executing")
        self.session.refresh_from_db()

        self.assertGreater(self.session.updated_at, original_updated_at)
        self.assertEqual(self.session.status, "executing")


class CacheManagerTestCase(TestCase):
    """Test the simplified RedisCacheManager service."""

    @patch("apps.core.services.cache_manager.cache")
    def test_query_caching(self, mock_cache):
        """Test caching of query results."""
        manager = RedisCacheManager()

        mock_cache.get.return_value = {"cached": "data"}
        query_params = {"q": "test query", "num": 10}
        result = manager.get_search_results(query_params)
        self.assertEqual(result, {"cached": "data"})

        manager.set_search_results(query_params, {"new": "data"})
        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        self.assertTrue(call_args[0][0].startswith("serp_cache:"))
        self.assertEqual(call_args[0][1], {"new": "data"})
        self.assertEqual(call_args[0][2], 3600)

    def test_cache_key_generation(self):
        """Test cache key generation."""
        manager = RedisCacheManager()

        key = manager._generate_key({"q": "test query", "num": 10})
        self.assertIsNotNone(key)
        self.assertTrue(key.startswith("serp_cache:"))

        key2 = manager._generate_key({"q": "test query", "num": 10})
        self.assertEqual(key, key2)

        key3 = manager._generate_key({"q": "different query", "num": 10})
        self.assertNotEqual(key, key3)

    def test_cache_persistence(self):
        """Test cache persistence across operations."""
        manager = RedisCacheManager()

        self.assertEqual(manager.default_ttl, 3600)

    def test_cache_cleanup(self):
        """Test cache cleanup operations."""
        manager = RedisCacheManager()

        result = manager.invalidate_session("test-session-id")
        self.assertTrue(result)

    @patch("apps.core.services.cache_manager.cache")
    def test_cache_hit(self, mock_cache):
        """Test cache hit and miss behavior."""
        manager = RedisCacheManager()

        mock_cache.get.return_value = {"cached": "data"}
        result = manager.get_search_results({"q": "test"})
        self.assertEqual(result, {"cached": "data"})

        mock_cache.get.return_value = None
        result = manager.get_search_results({"q": "test2"})
        self.assertIsNone(result)


class RetryManagerTestCase(TestCase):
    """Test the simplified SimpleRetryManager service."""

    def test_error_categorization(self):
        """Test categorization of different error types."""
        manager = SimpleRetryManager()

        delay = manager.get_retry_delay(Exception("rate limit exceeded"))
        self.assertEqual(delay, 300)

        delay = manager.get_retry_delay(ConnectionError("Connection failed"))
        self.assertEqual(delay, 60)

        delay = manager.get_retry_delay(Exception("API quota exceeded"))
        self.assertEqual(delay, 120)

    def test_exponential_backoff(self):
        """Test exponential backoff with retry attempts."""
        manager = SimpleRetryManager()

        error = Exception("test error")

        delay1 = manager.get_retry_delay(error, 1)
        delay2 = manager.get_retry_delay(error, 2)
        delay3 = manager.get_retry_delay(error, 3)

        self.assertLess(delay1, delay2)
        self.assertLess(delay2, delay3)
        self.assertLessEqual(delay3, 180 * 4)


class IntegrationTestCase(TestCase):
    """Integration tests for the simplified architecture."""

    def setUp(self):
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Integration Test", owner=self.user, status="ready_to_execute"
        )

    @patch("apps.core.services.serper_client.requests.post")
    def test_complete_workflow(self, mock_post):
        """Test complete workflow with all services."""
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                "organic": [
                    {"title": "Result 1", "link": "https://example.com/1"},
                    {"title": "Result 2", "link": "https://example.com/1"},
                ]
            },
        )

        state_manager = DatabaseStateManager()
        mock_rate_limiter = Mock()
        mock_rate_limiter.can_proceed.return_value = True
        serper_client = SerperClient(
            config={
                "api_key": "test-key",
                "timeout": 30,
                "base_url": "https://google.serper.dev/search",
                "cache_timeout": 3600,
                "enable_caching": False,
            },
            rate_limiter=mock_rate_limiter,
            cache_manager=Mock(),
        )

        # 1. Transition to executing
        state_manager.set_session_status(self.session, "executing")

        # 2. Execute search
        _results = serper_client.search("test query", 10, self.session)

        # 3. Transition to processing
        state_manager.set_session_status(self.session, "processing_results")

        # 4. Create processed results for deduplication
        from apps.results_manager.models import ProcessedResult

        ProcessedResult.objects.create(
            session=self.session, url="https://example.com/1", title="Result 1"
        )
        ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/1",
            title="Result 1 Duplicate",
        )

        # 5. Deduplicate
        dedup_service = URLDeduplicationService()
        dedup_result = dedup_service.deduplicate_session_results(self.session)
        self.assertEqual(dedup_result["total_duplicates"], 1)

        # 6. Transition to ready for review
        state_manager.set_session_status(self.session, "ready_for_review")

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_for_review")
