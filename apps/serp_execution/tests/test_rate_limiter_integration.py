"""
Integration tests for rate limiting with and without Redis.
"""

import os
import time
from unittest.mock import MagicMock, patch

from constance.test import override_config
from django.test import TransactionTestCase

from apps.core.utils.redis_utils import get_safe_redis_connection
from apps.serp_execution.services.rate_limiter import (
    GlobalRateLimiter,
    MockRateLimiter,
    get_rate_limiter,
)


class RateLimiterIntegrationTests(TransactionTestCase):
    """Integration tests for rate limiting with and without Redis."""

    def setUp(self):
        """Set up test environment."""
        # Clear any existing rate limiter instance
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None

        # Store original environment
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Clean up after tests."""
        # Reset the global rate limiter
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None

        # Restore original environment
        os.environ.clear()
        os.environ.update(self.original_env)

        # Clean up any test keys in Redis
        try:
            redis = get_safe_redis_connection("default")
            test_keys = redis.scan_iter("rate_limit:*test*")
            for key in test_keys:
                redis.delete(key)
        except Exception:
            pass

    def test_with_redis_available(self):
        """Test behavior when Redis is available."""
        # Ensure Redis is not skipped
        os.environ.pop("SKIP_REDIS_CONFIG", None)

        # Try to get a real Redis connection
        try:
            redis = get_safe_redis_connection("default")
            redis_available = redis.is_redis_available
        except Exception:
            redis_available = False

        if redis_available:
            # Get rate limiter - should be GlobalRateLimiter
            limiter = get_rate_limiter()
            self.assertIsInstance(limiter, GlobalRateLimiter)

            # Test rate limiting behavior
            test_key = "integration_test_redis"

            # Reset to ensure clean state
            limiter.reset(test_key)

            # Should allow initial requests
            allowed, _ = limiter.is_allowed(test_key, rate=60, burst=10)
            self.assertTrue(allowed)

            # Make rapid requests - verify return format
            for _ in range(5):
                allowed, wait_time = limiter.is_allowed(test_key, rate=60, burst=10)
                self.assertIsInstance(allowed, bool)
                self.assertIsInstance(wait_time, float)

            # Test status
            status = limiter.get_status(test_key)
            self.assertIn("tokens", status)
            self.assertIn("rate_limit", status)
            self.assertIn("status", status)
        else:
            # Redis not available in test environment - should fall back
            # to MockRateLimiter or use GlobalRateLimiter with cache fallback
            limiter = get_rate_limiter()
            self.assertIsInstance(limiter, (MockRateLimiter, GlobalRateLimiter))

    def test_with_redis_unavailable(self):
        """Test graceful degradation when Redis is unavailable."""
        # Ensure SKIP_REDIS_CONFIG is not set so it tries Redis first
        os.environ.pop("SKIP_REDIS_CONFIG", None)

        # Force Redis to be unavailable
        with patch(
            "apps.core.services.rate_limiter.get_safe_redis_connection"
        ) as mock_redis:
            mock_redis.side_effect = Exception("Redis connection failed")

            # Clear any existing instance
            import apps.serp_execution.services.rate_limiter as limiter_module

            limiter_module.rate_limiter = None

            # Should fall back to MockRateLimiter
            limiter = get_rate_limiter()
            self.assertIsInstance(limiter, MockRateLimiter)

            # Should never block requests
            test_key = "integration_test_no_redis"
            for _ in range(100):
                allowed, wait_time = limiter.is_allowed(test_key)
                self.assertTrue(allowed)
                self.assertEqual(wait_time, 0.0)

            # Wait should return immediately
            start = time.time()
            result = limiter.wait_if_needed(test_key, max_wait=10.0)
            elapsed = time.time() - start

            self.assertTrue(result)
            self.assertLess(elapsed, 0.1)

    def test_build_time_skip(self):
        """Test SKIP_REDIS_CONFIG environment variable."""
        # Set build-time skip flag
        os.environ["SKIP_REDIS_CONFIG"] = "true"

        # Clear any existing instance
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None

        # Should use MockRateLimiter
        limiter = get_rate_limiter()
        self.assertIsInstance(limiter, MockRateLimiter)

        # Verify mock behavior
        test_key = "integration_test_build"
        allowed, wait_time = limiter.is_allowed(test_key)
        self.assertTrue(allowed)
        self.assertEqual(wait_time, 0.0)

        # Status should indicate mock mode
        status = limiter.get_status(test_key)
        self.assertEqual(status["status"], "mock")

    @override_config(API_RATE_LIMIT_PER_MINUTE=60, API_RATE_LIMIT_BURST=10)
    def test_constance_configuration(self):
        """Test that rate limiter uses Constance configuration."""
        # Ensure Redis is not skipped
        os.environ.pop("SKIP_REDIS_CONFIG", None)

        # Get rate limiter
        limiter = get_rate_limiter()

        if isinstance(limiter, GlobalRateLimiter):
            # Test that it respects Constance settings
            test_key = "integration_test_constance"
            limiter.reset(test_key)

            # The rate and burst should come from Constance
            # When not specified, is_allowed should use Constance defaults
            allowed, _ = limiter.is_allowed(test_key)
            self.assertIsInstance(allowed, bool)

            # Get status to verify configuration
            status = limiter.get_status(test_key)
            self.assertIn("rate_limit", status)
            # Constance config should be reflected
            self.assertEqual(status["rate_limit"], 60)

    def test_concurrent_access(self):
        """Test concurrent access to rate limiter."""
        import threading

        limiter = get_rate_limiter()
        test_key = "integration_test_concurrent"

        if isinstance(limiter, GlobalRateLimiter):
            limiter.reset(test_key)

        results = []

        def make_request():
            allowed, _ = limiter.is_allowed(test_key, rate=1000, burst=100)
            results.append(allowed)

        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Should have results from all threads
        self.assertEqual(len(results), 10)

        # All should be boolean
        for result in results:
            self.assertIsInstance(result, bool)

    def test_error_recovery(self):
        """Test recovery from Redis errors."""
        # Start with working Redis
        os.environ.pop("SKIP_REDIS_CONFIG", None)

        # Clear any existing instance
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None

        # First call succeeds
        with patch(
            "apps.core.services.rate_limiter.get_safe_redis_connection"
        ) as mock_redis:
            mock_instance = MagicMock()
            mock_redis.return_value = mock_instance

            limiter1 = get_rate_limiter()

            # Should create GlobalRateLimiter
            if not os.environ.get("SKIP_REDIS_CONFIG"):
                self.assertIsInstance(limiter1, GlobalRateLimiter)

        # Clear instance to simulate fresh start
        limiter_module.rate_limiter = None

        # Second call fails - should fall back to mock
        with patch(
            "apps.core.services.rate_limiter.get_safe_redis_connection"
        ) as mock_redis:
            mock_redis.side_effect = Exception("Redis down")

            limiter2 = get_rate_limiter()
            self.assertIsInstance(limiter2, MockRateLimiter)

            # Should still work
            allowed, _ = limiter2.is_allowed("test_recovery")
            self.assertTrue(allowed)

    def test_rate_limiter_with_celery_task(self):
        """Test rate limiter integration with Celery tasks."""
        # Mock Celery task context
        limiter = get_rate_limiter()

        # Simulate task execution
        task_id = "test_task_123"

        # Check if task should proceed
        if isinstance(limiter, MockRateLimiter):
            # Mock limiter always allows
            allowed, _ = limiter.is_allowed(f"task:{task_id}")
            self.assertTrue(allowed)
        else:
            # Real limiter depends on Redis state
            allowed, wait_time = limiter.is_allowed(f"task:{task_id}")
            self.assertIsInstance(allowed, bool)
            self.assertIsInstance(wait_time, float)

            if not allowed:
                # Would retry after wait_time
                self.assertGreater(wait_time, 0)

    def test_wait_if_needed_timeout(self):
        """Test wait_if_needed with timeout."""
        limiter = get_rate_limiter()
        test_key = "integration_test_timeout"

        # Test with short timeout
        start = time.time()
        result = limiter.wait_if_needed(test_key, max_wait=0.1)
        elapsed = time.time() - start

        # Should not wait longer than max_wait
        self.assertLessEqual(elapsed, 0.2)  # Allow some overhead
        self.assertIsInstance(result, bool)

        if isinstance(limiter, MockRateLimiter):
            # Mock always returns True immediately
            self.assertTrue(result)
            self.assertLess(elapsed, 0.05)

    def test_reset_functionality(self):
        """Test reset clears rate limit state."""
        limiter = get_rate_limiter()
        test_key = "integration_test_reset"

        if isinstance(limiter, GlobalRateLimiter):
            # Make some requests
            for _ in range(5):
                limiter.is_allowed(test_key, rate=60, burst=10)

            # Get status before reset
            status_before = limiter.get_status(test_key)

            # Reset
            limiter.reset(test_key)

            # Status should show full tokens
            status_after = limiter.get_status(test_key)

            # After reset, should have more tokens (or same if it was already full)
            self.assertGreaterEqual(
                status_after.get("tokens", 100), status_before.get("tokens", 0)
            )
        else:
            # Mock limiter - reset is no-op but shouldn't error
            limiter.reset(test_key)
            status = limiter.get_status(test_key)
            self.assertEqual(status["status"], "mock")
