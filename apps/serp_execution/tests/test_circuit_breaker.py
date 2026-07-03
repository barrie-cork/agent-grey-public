"""
Tests for Phase 3 Circuit Breaker implementation.

Tests cover:
- Circuit breaker state transitions
- Redis storage persistence
- Dynamic configuration via Constance
- Failure handling and recovery
- Statistics collection
"""

import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

import pybreaker
from django.conf import settings
from django.test import TestCase

from apps.core.utils.redis_utils import get_safe_redis_connection
from apps.core.services.circuit_breaker import (
    CircuitBreakerListener,
    DynamicCircuitBreaker,
    RedisCircuitBreakerStorage,
    get_circuit_breaker_status,
    reset_all_circuit_breakers,
)

_has_redis_backend = (
    settings.CACHES.get("default", {}).get("BACKEND", "").endswith("RedisCache")
)


def _make_config_side_effect(overrides=None):
    """Create a side_effect for _get_config_value that returns overrides or defaults."""
    defaults = {
        "USE_CIRCUIT_BREAKERS": True,
        "CB_SERPER_API_FAIL_MAX": 5,
        "CB_SERPER_API_RESET_TIMEOUT": 60,
        "CB_DATABASE_FAIL_MAX": 3,
        "CB_DATABASE_RESET_TIMEOUT": 120,
        "CB_COLLECT_STATISTICS": True,
        "CB_NOTIFY_ON_OPEN": True,
    }
    if overrides:
        defaults.update(overrides)

    def side_effect(key, default=None, value_type=None):
        if key in defaults:
            return defaults[key]
        return default

    return side_effect


@unittest.skipUnless(_has_redis_backend, "Requires Redis cache backend")
class RedisCircuitBreakerStorageTest(TestCase):
    """Test Redis-based circuit breaker storage."""

    def setUp(self):
        """Set up test fixtures."""
        self.storage = RedisCircuitBreakerStorage("test_breaker")
        self.redis = get_safe_redis_connection("default")
        # Clean up any existing test data
        for key in self.redis.scan_iter("breaker:test_breaker:*"):
            self.redis.delete(key)

    def tearDown(self):
        """Clean up after tests."""
        # Clean up test data
        for key in self.redis.scan_iter("breaker:test_breaker:*"):
            self.redis.delete(key)

    def test_state_persistence(self):
        """Test that state is persisted in Redis."""
        # Initially should be closed
        self.assertEqual(self.storage.state, pybreaker.STATE_CLOSED)

        # Set to open
        self.storage.state = pybreaker.STATE_OPEN
        self.assertEqual(self.storage.state, pybreaker.STATE_OPEN)

        # Create new storage instance - should read from Redis
        new_storage = RedisCircuitBreakerStorage("test_breaker")
        self.assertEqual(new_storage.state, pybreaker.STATE_OPEN)

    def test_counter_operations(self):
        """Test counter increment and reset."""
        # Initially counter should be 0
        self.assertEqual(self.storage.counter, 0)

        # Increment counter
        new_count = self.storage.increment_counter()
        self.assertEqual(new_count, 1)
        self.assertEqual(self.storage.counter, 1)

        # Increment again
        new_count = self.storage.increment_counter()
        self.assertEqual(new_count, 2)

        # Reset counter
        self.storage.reset_counter()
        self.assertEqual(self.storage.counter, 0)

    def test_opened_at_timestamp(self):
        """Test opened_at timestamp storage."""
        # Initially should be None
        self.assertIsNone(self.storage.opened_at)

        # Set timestamp as float
        timestamp = datetime.now().timestamp()
        self.storage.opened_at = timestamp

        # opened_at returns a datetime object
        result = self.storage.opened_at
        self.assertIsInstance(result, datetime)
        expected = datetime.fromtimestamp(timestamp)
        self.assertAlmostEqual(result.timestamp(), expected.timestamp(), places=2)  # type: ignore[union-attr]

        # Clear timestamp
        self.storage.opened_at = None
        self.assertIsNone(self.storage.opened_at)

    @patch("apps.core.services.circuit_breaker._get_config_value")
    def test_statistics_collection(self, mock_get_config):
        """Test statistics collection features."""
        mock_get_config.side_effect = _make_config_side_effect(
            {"CB_COLLECT_STATISTICS": True}
        )

        # Record a state change
        self.storage._record_state_change("closed", "open")

        # Check history was recorded
        history_key = self.storage._get_key("history")
        history = self.redis.lrange(history_key, 0, -1)
        self.assertEqual(len(history), 1)

        # Parse and verify history entry
        entry = json.loads(history[0].decode("utf-8"))
        self.assertEqual(entry["old_state"], "closed")
        self.assertEqual(entry["new_state"], "open")
        self.assertIn("timestamp", entry)

    @patch("apps.core.services.circuit_breaker._get_config_value")
    def test_failure_recording(self, mock_get_config):
        """Test failure statistics recording."""
        mock_get_config.side_effect = _make_config_side_effect(
            {"CB_COLLECT_STATISTICS": True}
        )

        # Record failures
        self.storage._record_failure()
        self.storage._record_failure()

        # Check daily failure count via the underlying Redis client
        stats_key = self.storage._get_key("stats:failures")
        today = datetime.now().strftime("%Y-%m-%d")

        # Use the storage's underlying redis connection (not the safe wrapper)
        raw_redis = self.storage.redis._redis_conn
        assert raw_redis is not None
        failure_count = raw_redis.hget(stats_key, today)
        self.assertEqual(int(failure_count), 2)

    def test_get_statistics(self):
        """Test comprehensive statistics retrieval."""
        # Set up some test data
        self.storage.state = pybreaker.STATE_OPEN
        self.storage.increment_counter()
        self.storage.increment_counter()
        self.storage.opened_at = datetime.now().timestamp()

        # Get statistics
        stats = self.storage.get_statistics()

        # Verify statistics
        self.assertEqual(stats["current_state"], pybreaker.STATE_OPEN)
        self.assertEqual(stats["failure_count"], 2)
        self.assertTrue(stats["is_open"])
        self.assertFalse(stats["is_closed"])
        self.assertIsNotNone(stats["opened_at"])

    def test_reset(self):
        """Test complete reset functionality."""
        # Set up some state
        self.storage.state = pybreaker.STATE_OPEN
        self.storage.increment_counter()
        self.storage.opened_at = datetime.now().timestamp()

        # Reset
        self.storage.reset()

        # Everything should be cleared
        self.assertEqual(self.storage.state, pybreaker.STATE_CLOSED)
        self.assertEqual(self.storage.counter, 0)
        self.assertIsNone(self.storage.opened_at)


class DynamicCircuitBreakerTest(TestCase):
    """Test dynamic circuit breaker factory."""

    @patch("apps.core.services.circuit_breaker._get_config_value")
    def test_create_serper_breaker_enabled(self, mock_get_config):
        """Test creating Serper breaker when enabled."""
        mock_get_config.side_effect = _make_config_side_effect(
            {
                "USE_CIRCUIT_BREAKERS": True,
                "CB_SERPER_API_FAIL_MAX": 5,
                "CB_SERPER_API_RESET_TIMEOUT": 60,
            }
        )

        breaker = DynamicCircuitBreaker.create_serper_breaker()

        self.assertIsInstance(breaker, pybreaker.CircuitBreaker)
        self.assertEqual(breaker.fail_max, 5)
        self.assertEqual(breaker.reset_timeout, 60)
        self.assertEqual(breaker.name, "SerperAPI")

    @patch("apps.core.services.circuit_breaker._get_config_value")
    def test_create_serper_breaker_disabled(self, mock_get_config):
        """Test creating Serper breaker when disabled."""
        mock_get_config.side_effect = _make_config_side_effect(
            {
                "USE_CIRCUIT_BREAKERS": False,
            }
        )

        breaker = DynamicCircuitBreaker.create_serper_breaker()

        self.assertIsInstance(breaker, pybreaker.CircuitBreaker)
        self.assertEqual(breaker.fail_max, float("inf"))  # Never opens
        self.assertEqual(breaker.name, "SerperAPI_Disabled")

    @patch("apps.core.services.circuit_breaker._get_config_value")
    def test_create_database_breaker(self, mock_get_config):
        """Test creating database breaker."""
        mock_get_config.side_effect = _make_config_side_effect(
            {
                "USE_CIRCUIT_BREAKERS": True,
                "CB_DATABASE_FAIL_MAX": 3,
                "CB_DATABASE_RESET_TIMEOUT": 30,
            }
        )

        breaker = DynamicCircuitBreaker.create_database_breaker()

        self.assertIsInstance(breaker, pybreaker.CircuitBreaker)
        self.assertEqual(breaker.fail_max, 3)
        self.assertEqual(breaker.reset_timeout, 30)
        self.assertEqual(breaker.name, "Database")

    def test_get_all_breakers_status(self):
        """Test getting status of all breakers."""
        status = DynamicCircuitBreaker.get_all_breakers_status()

        self.assertIn("serper_api", status)
        self.assertIn("database", status)

        for breaker_name, breaker_status in status.items():
            self.assertIn("current_state", breaker_status)
            self.assertIn("failure_count", breaker_status)


class CircuitBreakerListenerTest(TestCase):
    """Test circuit breaker listener."""

    @patch("apps.core.services.circuit_breaker.sentry_sdk")
    @patch("apps.core.services.circuit_breaker._get_config_value")
    def test_state_change_notification(self, mock_get_config, mock_sentry):
        """Test that state changes trigger notifications."""
        mock_get_config.side_effect = _make_config_side_effect(
            {
                "CB_NOTIFY_ON_OPEN": True,
            }
        )

        listener = CircuitBreakerListener()
        mock_cb = Mock()
        mock_cb.name = "TestBreaker"

        # Test opening circuit
        listener.state_change(mock_cb, pybreaker.STATE_CLOSED, pybreaker.STATE_OPEN)

        # Should send Sentry alert
        mock_sentry.capture_message.assert_called_once()
        call_args = mock_sentry.capture_message.call_args
        self.assertIn("TestBreaker", call_args[0][0])
        self.assertIn("OPEN", call_args[0][0])

    @patch("apps.core.services.circuit_breaker.logger")
    def test_failure_logging(self, mock_logger):
        """Test that failures are logged."""
        listener = CircuitBreakerListener()
        mock_cb = Mock()
        mock_cb.name = "TestBreaker"

        exception = Exception("Test error")
        listener.failure(mock_cb, exception)

        mock_logger.debug.assert_called_once()
        self.assertIn("TestBreaker", mock_logger.debug.call_args[0][0])


class CircuitBreakerIntegrationTest(TestCase):
    """Integration tests for circuit breaker configuration and status."""

    @patch("apps.core.services.circuit_breaker._get_config_value")
    def test_get_circuit_breaker_status(self, mock_get_config):
        """Test getting comprehensive circuit breaker status."""
        mock_get_config.side_effect = _make_config_side_effect(
            {
                "USE_CIRCUIT_BREAKERS": True,
                "CB_SERPER_API_FAIL_MAX": 5,
                "CB_SERPER_API_RESET_TIMEOUT": 60,
                "CB_DATABASE_FAIL_MAX": 3,
                "CB_DATABASE_RESET_TIMEOUT": 30,
            }
        )

        status = get_circuit_breaker_status()

        self.assertTrue(status["enabled"])
        self.assertIn("breakers", status)
        self.assertIn("configuration", status)

        # Check configuration
        self.assertEqual(status["configuration"]["serper_api"]["fail_max"], 5)
        self.assertEqual(status["configuration"]["database"]["fail_max"], 3)

    @unittest.skipUnless(_has_redis_backend, "Requires Redis cache backend")
    def test_reset_all_circuit_breakers(self):
        """Test resetting all circuit breakers."""
        # Set up some state in breakers
        storage1 = RedisCircuitBreakerStorage("serper_api")
        storage1.state = pybreaker.STATE_OPEN
        storage1.increment_counter()

        storage2 = RedisCircuitBreakerStorage("database")
        storage2.state = pybreaker.STATE_OPEN
        storage2.increment_counter()

        # Reset all
        reset_all_circuit_breakers()

        # Check they're reset
        self.assertEqual(storage1.state, pybreaker.STATE_CLOSED)
        self.assertEqual(storage1.counter, 0)
        self.assertEqual(storage2.state, pybreaker.STATE_CLOSED)
        self.assertEqual(storage2.counter, 0)
