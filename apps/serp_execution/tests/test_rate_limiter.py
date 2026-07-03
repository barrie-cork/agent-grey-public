"""
Tests for the rate limiter services.
"""

import os
import time
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.utils.redis_utils import get_safe_redis_connection
from apps.serp_execution.services.rate_limiter import (
    GlobalRateLimiter,
    MockRateLimiter,
    get_rate_limiter,
)


class GlobalRateLimiterTests(TestCase):
    """Tests for GlobalRateLimiter with Redis."""

    def setUp(self):
        """Set up test environment."""
        # Clear any existing rate limiter instance
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None

        # Ensure Redis is not skipped for these tests
        os.environ.pop("SKIP_REDIS_CONFIG", None)

    def tearDown(self):
        """Clean up after tests."""
        # Reset the global rate limiter
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None

        # Clean up any test keys in Redis
        try:
            redis = get_safe_redis_connection("default")
            test_keys = redis.scan_iter("rate_limit:test_*")
            for key in test_keys:
                redis.delete(key)
        except Exception:
            pass

    @patch("apps.core.services.rate_limiter.get_safe_redis_connection")
    def test_lazy_initialization(self, mock_get_redis):
        """Test rate limiter is not created at import time."""
        # Clear any existing instance and ensure Redis is not skipped
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None
        os.environ.pop("SKIP_REDIS_CONFIG", None)

        # Verify no Redis connection until get_rate_limiter is called
        mock_get_redis.assert_not_called()

        # Now get the rate limiter
        get_rate_limiter()

        # Should have attempted to get Redis connection
        mock_get_redis.assert_called()

    @patch("apps.core.services.rate_limiter.get_safe_redis_connection")
    def test_fallback_to_mock_on_redis_error(self, mock_get_redis):
        """Test fallback when Redis unavailable."""
        # Clear any existing instance
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None

        # Ensure SKIP_REDIS_CONFIG is not set so it tries Redis first
        os.environ.pop("SKIP_REDIS_CONFIG", None)

        # Make Redis connection fail
        mock_get_redis.side_effect = Exception("Redis connection failed")

        # Get rate limiter should return MockRateLimiter
        limiter = get_rate_limiter()
        self.assertIsInstance(limiter, MockRateLimiter)

        # Should always allow requests
        allowed, wait_time = limiter.is_allowed("test_fallback")
        self.assertTrue(allowed)
        self.assertEqual(wait_time, 0.0)

    def test_skip_redis_config_environment_variable(self):
        """Test SKIP_REDIS_CONFIG environment variable."""
        # Set the environment variable
        os.environ["SKIP_REDIS_CONFIG"] = "true"

        # Clear any existing instance
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None

        # Get rate limiter should return MockRateLimiter
        limiter = get_rate_limiter()
        self.assertIsInstance(limiter, MockRateLimiter)

        # Clean up
        os.environ.pop("SKIP_REDIS_CONFIG", None)

    @patch("apps.core.services.rate_limiter.get_safe_redis_connection")
    def test_rate_limiting_logic(self, mock_get_redis):
        """Test the actual rate limiting logic."""
        # Create a mock Redis instance
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock redis.eval to return 1 (allowed)
        mock_redis.eval.return_value = 1

        limiter = GlobalRateLimiter()

        # First request should be allowed
        allowed, wait_time = limiter.is_allowed("test_identifier")
        self.assertTrue(allowed)
        # When allowed, wait_time is config.API_RATE_LIMIT_BURST - 1
        self.assertIsInstance(wait_time, float)

        # Mock rate limit reached (redis.eval returns 0)
        mock_redis.eval.return_value = 0

        allowed, wait_time = limiter.is_allowed("test_identifier")
        self.assertFalse(allowed)
        # When denied, wait_time is the retry delay
        self.assertIsInstance(wait_time, float)
        self.assertGreater(wait_time, 0)

    def test_wait_if_needed(self):
        """Test wait_if_needed method."""
        limiter = get_rate_limiter()

        if isinstance(limiter, MockRateLimiter):
            # Mock limiter should never wait
            start = time.time()
            result = limiter.wait_if_needed("test_wait", max_wait=1.0)
            elapsed = time.time() - start
            self.assertTrue(result)
            self.assertLess(elapsed, 0.1)  # Should return immediately
        else:
            # Real limiter behavior would depend on Redis state
            # Just verify it doesn't error
            result = limiter.wait_if_needed("test_wait", max_wait=0.1)
            self.assertIsInstance(result, bool)

    def test_get_status(self):
        """Test getting rate limiter status."""
        limiter = get_rate_limiter()
        status = limiter.get_status("test_status")

        self.assertIsInstance(status, dict)
        if isinstance(limiter, MockRateLimiter):
            self.assertEqual(status["status"], "mock")
        else:
            self.assertIn("tokens", status)
            self.assertIn("rate_limit", status)

    def test_reset(self):
        """Test resetting rate limiter."""
        limiter = get_rate_limiter()

        # Reset should not raise errors
        limiter.reset("test_reset")

        # After reset, should be able to make requests
        allowed, _ = limiter.is_allowed("test_reset")
        self.assertTrue(allowed)


class MockRateLimiterTests(TestCase):
    """Tests for MockRateLimiter fallback."""

    def setUp(self):
        """Create a mock rate limiter."""
        self.limiter = MockRateLimiter()

    def test_always_allows_requests(self):
        """Test mock limiter never blocks."""
        # Make many rapid requests
        for i in range(100):
            allowed, wait_time = self.limiter.is_allowed(f"test_{i}")
            self.assertTrue(allowed)
            self.assertEqual(wait_time, 0.0)

    def test_never_waits(self):
        """Test mock limiter never waits."""
        start = time.time()
        for i in range(10):
            result = self.limiter.wait_if_needed(f"test_{i}", max_wait=10.0)
            self.assertTrue(result)

        elapsed = time.time() - start
        self.assertLess(elapsed, 1.0)  # Should complete quickly

    def test_mock_status(self):
        """Test mock status response."""
        status = self.limiter.get_status("test")
        self.assertEqual(status["status"], "mock")
        self.assertIn("tokens", status)
        self.assertIn("rate_limit", status)

    def test_reset_is_noop(self):
        """Test reset does nothing in mock mode."""
        # Should not raise any errors
        self.limiter.reset("test")

        # Behavior unchanged after reset
        allowed, wait_time = self.limiter.is_allowed("test")
        self.assertTrue(allowed)
        self.assertEqual(wait_time, 0.0)


class RateLimiterConfigurationTests(TestCase):
    """Tests for rate limiter configuration."""

    @patch.dict(os.environ, {"SKIP_REDIS_CONFIG": "false"})
    @patch("apps.core.services.rate_limiter.get_safe_redis_connection")
    def test_production_configuration(self, mock_get_redis):
        """Test rate limiter in production-like environment."""
        # Clear any existing instance
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None

        # Configure mock Redis
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Get rate limiter should create GlobalRateLimiter
        limiter = get_rate_limiter()
        self.assertIsInstance(limiter, GlobalRateLimiter)

    @patch.dict(os.environ, {"SKIP_REDIS_CONFIG": "true"})
    def test_build_time_configuration(self):
        """Test rate limiter during build/deploy."""
        # Clear any existing instance
        import apps.serp_execution.services.rate_limiter as limiter_module

        limiter_module.rate_limiter = None

        # Should use MockRateLimiter during build
        limiter = get_rate_limiter()
        self.assertIsInstance(limiter, MockRateLimiter)

    def test_singleton_pattern(self):
        """Test that get_rate_limiter returns the same instance."""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()

        # Should be the same instance
        self.assertIs(limiter1, limiter2)
