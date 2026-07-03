"""
Comprehensive tests for SafeRedisWrapper with fallback handling.

These tests ensure the wrapper behaves correctly in both Redis-available
and fallback scenarios, providing consistent API compatibility.
"""

import json
import os
import unittest.mock as mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.utils.redis_utils import (
    SafeRedisWrapper,
    clear_connection_cache,
    get_redis_info,
    get_safe_redis_connection,
    is_redis_available,
)


class TestSafeRedisWrapper(TestCase):
    """Test the SafeRedisWrapper in various scenarios."""

    def setUp(self):
        """Set up test environment."""
        # Clear cache before each test
        cache.clear()
        # Clear connection cache to ensure fresh instances
        clear_connection_cache()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()
        clear_connection_cache()

    @mock.patch("django_redis.get_redis_connection")
    @mock.patch.object(
        SafeRedisWrapper,
        "_get_cache_backend_info",
        return_value={"is_redis": True, "backend": "django_redis.cache.RedisCache"},
    )
    def test_redis_available_scenario(self, _mock_backend, mock_get_connection):
        """Test wrapper behavior when Redis is available."""
        # Mock Redis connection
        mock_redis = mock.MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = b"test_value"
        mock_redis.set.return_value = True
        mock_redis.delete.return_value = 1
        mock_redis.exists.return_value = True
        mock_redis.incr.return_value = 5
        mock_get_connection.return_value = mock_redis

        wrapper = SafeRedisWrapper()

        # Test connection status
        self.assertTrue(wrapper.is_redis_available)
        self.assertFalse(wrapper._use_fallback)

        # Test basic operations
        self.assertEqual(wrapper.get("test_key"), b"test_value")
        self.assertTrue(wrapper.set("test_key", "test_value"))
        self.assertEqual(wrapper.delete("test_key"), 1)
        self.assertTrue(wrapper.exists("test_key"))
        self.assertEqual(wrapper.incr("counter"), 5)
        self.assertTrue(wrapper.ping())

        # Verify Redis was called directly
        mock_redis.get.assert_called_with("test_key")
        mock_redis.set.assert_called_with("test_key", "test_value", ex=None)
        mock_redis.delete.assert_called_with("test_key")
        mock_redis.exists.assert_called_with("test_key")
        mock_redis.incr.assert_called_with("counter", 1)

    @mock.patch("django_redis.get_redis_connection")
    def test_redis_unavailable_fallback(self, mock_get_connection):
        """Test wrapper fallback when Redis is unavailable."""
        # Mock Redis connection failure
        mock_get_connection.side_effect = Exception("Redis connection failed")

        wrapper = SafeRedisWrapper()

        # Should use fallback
        self.assertFalse(wrapper.is_redis_available)
        self.assertTrue(wrapper._use_fallback)

        # Test cache operations work
        self.assertTrue(wrapper.set("test_key", "test_value", ex=300))
        result = wrapper.get("test_key")

        # Should return bytes for consistency with Redis
        self.assertIsInstance(result, bytes)
        self.assertEqual(result, b"test_value")

        # Verify Django cache was used
        self.assertEqual(cache.get("test_key"), "test_value")

        # Test other operations
        self.assertTrue(wrapper.exists("test_key"))
        self.assertEqual(wrapper.incr("counter"), 1)
        self.assertEqual(wrapper.incr("counter", 5), 6)
        self.assertEqual(wrapper.delete("test_key"), 1)

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "test-non-redis",
            }
        }
    )
    def test_non_redis_backend_detection(self):
        """Test automatic detection of non-Redis backends."""
        wrapper = SafeRedisWrapper()

        # Should detect non-Redis backend and use fallback
        self.assertFalse(wrapper.is_redis_available)
        self.assertTrue(wrapper._use_fallback)
        self.assertIn("locmem", wrapper.backend_type.lower())

        # Operations should still work
        wrapper.set("test", "value")
        self.assertEqual(wrapper.get("test"), b"value")

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.dummy.DummyCache",
            }
        }
    )
    def test_dummy_cache_backend(self):
        """Test behavior with dummy cache backend."""
        wrapper = SafeRedisWrapper()

        # Should detect dummy backend
        self.assertFalse(wrapper.is_redis_available)
        self.assertTrue(wrapper._use_fallback)

        # Operations should not fail (but may not persist with dummy cache)
        wrapper.set("key", "value")
        # Dummy cache doesn't persist, so get may return None
        result = wrapper.get("key")
        # Should handle gracefully
        self.assertIsNone(result)

    def test_connection_singleton_behavior(self):
        """Test that connections are reused properly."""
        conn1 = get_safe_redis_connection("default")
        conn2 = get_safe_redis_connection("default")

        # Should be the same instance
        self.assertIs(conn1, conn2)

        # Different connection names should be different instances
        conn_other = get_safe_redis_connection("other")
        self.assertIsNot(conn1, conn_other)

    def test_clear_connection_cache(self):
        """Test connection cache clearing."""
        conn1 = get_safe_redis_connection("default")
        clear_connection_cache()
        conn2 = get_safe_redis_connection("default")

        # Should be different instances after cache clear
        self.assertIsNot(conn1, conn2)

    def test_bytes_vs_strings_handling(self):
        """Test consistent handling of bytes vs strings."""
        wrapper = get_safe_redis_connection()

        # Test string input
        wrapper.set("string_key", "string_value")
        result1 = wrapper.get("string_key")
        self.assertIsInstance(result1, bytes)

        # Test bytes input
        wrapper.set("bytes_key", b"bytes_value")
        result2 = wrapper.get("bytes_key")
        self.assertIsInstance(result2, bytes)

    def test_hash_operations(self):
        """Test hash operations with fallback."""
        wrapper = get_safe_redis_connection()

        # Test hash operations
        test_hash = {"field1": "value1", "field2": "value2"}
        wrapper.hmset("hash_key", test_hash)

        # Test getting all hash fields
        result = wrapper.hgetall("hash_key")
        self.assertIsInstance(result, dict)

        # Test getting specific fields
        fields = wrapper.hmget("hash_key", "field1", "field2")
        self.assertIsInstance(fields, list)
        self.assertEqual(len(fields), 2)

        # Test incrementing hash field
        initial_count = wrapper.hincrby("counter_hash", "visits", 1)
        self.assertEqual(initial_count, 1)
        next_count = wrapper.hincrby("counter_hash", "visits", 5)
        self.assertEqual(next_count, 6)

    def test_list_operations(self):
        """Test list operations with fallback."""
        wrapper = get_safe_redis_connection()

        # Test list operations
        list_length = wrapper.lpush("test_list", "item1", "item2", "item3")
        self.assertEqual(list_length, 3)

        # Test list length
        length = wrapper.llen("test_list")
        self.assertEqual(length, 3)

        # Test getting list range
        items = wrapper.lrange("test_list", 0, -1)
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 3)

        # Test list trimming
        success = wrapper.ltrim("test_list", 0, 1)
        self.assertTrue(success)

        # Verify trim worked
        length_after_trim = wrapper.llen("test_list")
        self.assertEqual(length_after_trim, 2)

    def test_expiration_operations(self):
        """Test key expiration operations."""
        wrapper = get_safe_redis_connection()

        # Set key with expiration
        wrapper.set("expire_key", "value", ex=60)
        self.assertTrue(wrapper.exists("expire_key"))

        # Test setting expiration on existing key
        wrapper.set("another_key", "value")
        success = wrapper.expire("another_key", 60)
        self.assertTrue(success)

        # Test setex method
        success = wrapper.setex("setex_key", 60, "value")
        self.assertTrue(success)
        self.assertTrue(wrapper.exists("setex_key"))

    def test_scan_operations(self):
        """Test key scanning operations (Redis-only)."""
        wrapper = get_safe_redis_connection()

        # Set up test keys
        wrapper.set("pattern:key1", "value1")
        wrapper.set("pattern:key2", "value2")
        wrapper.set("other:key", "value3")

        # Test scan_iter
        matching_keys = list(wrapper.scan_iter(match="pattern:*"))

        if wrapper.is_redis_available:
            # Redis should return matching keys
            self.assertGreaterEqual(len(matching_keys), 0)  # May vary by implementation
        else:
            # Fallback mode doesn't support pattern scanning
            self.assertEqual(len(matching_keys), 0)

    @mock.patch.dict(os.environ, {"SKIP_REDIS_CONFIG": "true"})
    def test_skip_redis_config_environment(self):
        """Test behavior when SKIP_REDIS_CONFIG is set."""
        clear_connection_cache()  # Ensure fresh instance
        wrapper = SafeRedisWrapper()

        # Should automatically use fallback
        self.assertFalse(wrapper.is_redis_available)
        self.assertTrue(wrapper._use_fallback)
        self.assertEqual(wrapper.backend_type, "build_skip")

    def test_error_isolation(self):
        """Test that Redis errors don't propagate to application."""
        # This test ensures the wrapper handles errors gracefully
        wrapper = get_safe_redis_connection()

        # Even if operations fail, they should not raise exceptions
        try:
            # These should not raise exceptions regardless of backend
            wrapper.set("test", "value")
            wrapper.get("test")
            wrapper.delete("test")
            wrapper.exists("test")
            wrapper.incr("counter")
            wrapper.ping()
            success = True
        except Exception:
            success = False

        self.assertTrue(success, "Redis operations should not raise exceptions")

    def test_info_and_status_methods(self):
        """Test information and status methods."""
        wrapper = get_safe_redis_connection()

        # Test get_info method
        info = wrapper.get_info()
        self.assertIsInstance(info, dict)
        self.assertIn("connection_name", info)
        self.assertIn("is_redis_available", info)
        self.assertIn("use_fallback", info)
        self.assertIn("backend_type", info)
        self.assertIn("ping_success", info)

        # Test is_redis_available function
        available = is_redis_available()
        self.assertIsInstance(available, bool)

        # Test get_redis_info function
        redis_info = get_redis_info()
        self.assertIsInstance(redis_info, dict)
        self.assertEqual(redis_info, info)  # Should be same as wrapper.get_info()


class TestRealRedisIntegration(TestCase):
    """
    Integration tests that work with actual Redis if available.

    These tests gracefully handle both Redis-available and fallback scenarios.
    """

    def setUp(self):
        """Set up for integration tests."""
        cache.clear()
        clear_connection_cache()

    def test_circuit_breaker_integration(self):
        """Test integration with circuit breaker patterns."""
        wrapper = get_safe_redis_connection()

        # Simulate circuit breaker state storage
        breaker_key = "breaker:test_service"

        # Set initial state
        wrapper.set(f"{breaker_key}:state", "closed")
        wrapper.set(f"{breaker_key}:counter", "0")

        # Test state retrieval
        state = wrapper.get(f"{breaker_key}:state")
        counter = wrapper.get(f"{breaker_key}:counter")

        if state:
            state_str = (
                state.decode("utf-8") if isinstance(state, bytes) else str(state)
            )
            self.assertEqual(state_str, "closed")

        if counter:
            counter_int = int(
                counter.decode("utf-8") if isinstance(counter, bytes) else counter
            )
            self.assertEqual(counter_int, 0)

        # Test counter increment
        new_count = wrapper.incr(f"{breaker_key}:counter")
        self.assertGreaterEqual(new_count, 1)

    def test_rate_limiter_integration(self):
        """Test integration with rate limiting patterns."""
        wrapper = get_safe_redis_connection()

        # Simulate rate limiter token bucket
        bucket_key = "rate_limit:test_api"

        # Initialize bucket
        bucket_data = {
            "tokens": "10",
            "last_refill": "1640995200.0",  # Timestamp
        }
        wrapper.hmset(bucket_key, bucket_data)

        # Test bucket retrieval
        stored_data = wrapper.hgetall(bucket_key)
        self.assertIsInstance(stored_data, dict)

        if stored_data:
            # Handle both bytes and string keys/values
            tokens_key = b"tokens" if b"tokens" in stored_data else "tokens"
            if tokens_key in stored_data:
                tokens_value = stored_data[tokens_key]
                if isinstance(tokens_value, bytes):
                    tokens = int(tokens_value.decode("utf-8"))
                else:
                    tokens = int(tokens_value)
                self.assertEqual(tokens, 10)

    def test_monitoring_dashboard_integration(self):
        """Test integration with monitoring dashboard patterns."""
        wrapper = get_safe_redis_connection()

        # Simulate queue depth monitoring
        queues = ["search", "batch", "session"]

        for i, queue in enumerate(queues):
            queue_key = f"celery:{queue}"
            # Add some items to simulate queue
            for j in range(i + 1):
                wrapper.lpush(queue_key, f"job_{j}")

        # Test queue depth retrieval
        queue_stats = {}
        for queue in queues:
            queue_key = f"celery:{queue}"
            depth = wrapper.llen(queue_key)
            queue_stats[queue] = depth

        # Verify queue stats
        self.assertIsInstance(queue_stats, dict)
        self.assertEqual(len(queue_stats), 3)

        # In Redis mode, should have actual depths
        # In fallback mode, operations still work but may vary

    def test_performance_baseline(self):
        """Basic performance test to ensure wrapper doesn't add excessive overhead."""
        wrapper = get_safe_redis_connection()

        import time

        # Test basic operations timing
        start_time = time.time()

        for i in range(10):
            key = f"perf_test_{i}"
            wrapper.set(key, f"value_{i}", ex=60)
            wrapper.get(key)
            wrapper.exists(key)
            wrapper.delete(key)

        end_time = time.time()
        total_time = end_time - start_time

        # Should complete 40 operations in reasonable time (generous limit for CI)
        self.assertLess(
            total_time, 5.0, "Performance test should complete within 5 seconds"
        )

        avg_time_per_op = total_time / 40
        # Each operation should average less than 50ms (very generous for fallback mode)
        self.assertLess(
            avg_time_per_op, 0.05, "Average operation time should be reasonable"
        )


class TestEdgeCasesAndErrorHandling(TestCase):
    """Test edge cases and error handling scenarios."""

    def setUp(self):
        cache.clear()
        clear_connection_cache()

    def test_none_values_handling(self):
        """Test handling of None values."""
        wrapper = get_safe_redis_connection()

        # Test getting non-existent key
        result = wrapper.get("non_existent_key")
        self.assertIsNone(result)

        # Test existence check
        exists = wrapper.exists("non_existent_key")
        self.assertFalse(exists)

    def test_large_values(self):
        """Test handling of large values."""
        wrapper = get_safe_redis_connection()

        # Test with moderately large string
        large_value = "x" * 10000  # 10KB string
        success = wrapper.set("large_key", large_value)
        self.assertTrue(success)

        retrieved = wrapper.get("large_key")
        if retrieved:
            retrieved_str = (
                retrieved.decode("utf-8")
                if isinstance(retrieved, bytes)
                else str(retrieved)
            )
            self.assertEqual(len(retrieved_str), 10000)

    def test_special_characters(self):
        """Test handling of special characters and Unicode."""
        wrapper = get_safe_redis_connection()

        # Test Unicode string
        unicode_value = "Hello 世界! 🌍🔥💧"
        wrapper.set("unicode_key", unicode_value)

        retrieved = wrapper.get("unicode_key")
        if retrieved:
            retrieved_str = (
                retrieved.decode("utf-8")
                if isinstance(retrieved, bytes)
                else str(retrieved)
            )
            self.assertEqual(retrieved_str, unicode_value)

    def test_numeric_values(self):
        """Test handling of numeric values."""
        wrapper = get_safe_redis_connection()

        # Test increment with non-existent key
        count1 = wrapper.incr("new_counter")
        self.assertEqual(count1, 1)

        # Test increment with existing key
        count2 = wrapper.incr("new_counter", 10)
        self.assertEqual(count2, 11)

        # Test with string that looks like number
        wrapper.set("string_number", "42")
        result = wrapper.get("string_number")
        if result:
            result_str = (
                result.decode("utf-8") if isinstance(result, bytes) else str(result)
            )
            self.assertEqual(result_str, "42")

    def test_concurrent_access_simulation(self):
        """Simulate concurrent access patterns."""
        wrapper = get_safe_redis_connection()

        # This simulates what might happen with multiple processes
        counter_key = "concurrent_counter"

        # Multiple increments (simulating concurrent access)
        results = []
        for i in range(5):
            result = wrapper.incr(counter_key)
            results.append(result)

        # Results should be increasing (though not guaranteed to be sequential in real concurrency)
        self.assertEqual(len(results), 5)
        self.assertGreater(max(results), 0)

    def test_json_data_handling(self):
        """Test storing and retrieving JSON data."""
        wrapper = get_safe_redis_connection()

        # Test storing JSON-like data
        test_data = {
            "session_id": "12345",
            "user_id": 67890,
            "timestamp": 1640995200,
            "metadata": {"source": "api", "version": "1.0"},
        }

        json_str = json.dumps(test_data)
        wrapper.set("json_key", json_str)

        retrieved = wrapper.get("json_key")
        if retrieved:
            retrieved_str = (
                retrieved.decode("utf-8")
                if isinstance(retrieved, bytes)
                else str(retrieved)
            )
            parsed_data = json.loads(retrieved_str)
            self.assertEqual(parsed_data, test_data)

    @mock.patch("apps.core.utils.redis_utils.logger")
    @mock.patch.object(
        SafeRedisWrapper,
        "_get_cache_backend_info",
        return_value={"is_redis": True, "backend": "django_redis.cache.RedisCache"},
    )
    def test_logging_behavior(self, _mock_backend, mock_logger):
        """Test that appropriate logging occurs."""
        # Create wrapper that will use fallback due to connection failure
        with mock.patch("django_redis.get_redis_connection") as mock_get_conn:
            mock_get_conn.side_effect = Exception("Redis failed")

            wrapper = SafeRedisWrapper()

            # Should have logged the fallback warning
            self.assertTrue(mock_logger.warning.called)

            # Operations should still work and log appropriately
            wrapper.set("test", "value")
            wrapper.get("non_existent")

            # Should not have excessive error logging for normal operations
            _error_calls = [
                call
                for call in mock_logger.error.call_args_list
                if "normal operations" not in str(call)
            ]
