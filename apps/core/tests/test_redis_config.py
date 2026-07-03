"""
Tests for Redis configuration module.

This module tests the Redis configuration functionality including:
- Connection checking with various scenarios
- Cache configuration generation
- Fallback behavior when Redis is unavailable
- SSL configuration handling
- Channels configuration
"""

import unittest.mock
from unittest.mock import MagicMock, Mock, patch

from django.test import TestCase

from apps.core.redis_config import (
    CACHE_KEYS,
    check_redis_connection,
    get_cache_config,
    get_cache_key,
    get_celery_config,
    get_channels_config,
    get_redis_url,
    get_session_config,
)


class RedisConfigTestCase(TestCase):
    """Test Redis configuration functions."""

    def setUp(self):
        """Set up test environment."""
        self.test_redis_url = "redis://localhost:6379/0"
        self.test_redis_ssl_url = "rediss://user:pass@redis.digitalocean.com:25061/0"

    @patch("apps.core.redis_config.get_env")
    def test_get_redis_url_default(self, mock_get_env):
        """Test get_redis_url returns default URL."""
        mock_get_env.return_value = self.test_redis_url
        url = get_redis_url()
        self.assertEqual(url, self.test_redis_url)
        mock_get_env.assert_called_once_with("REDIS_URL", default=None)

    @patch("apps.core.redis_config.get_env")
    def test_get_redis_url_custom(self, mock_get_env):
        """Test get_redis_url returns custom URL from environment."""
        custom_url = "redis://custom:6380/1"
        mock_get_env.return_value = custom_url
        url = get_redis_url()
        self.assertEqual(url, custom_url)

    @patch("importlib.util.find_spec")
    def test_get_cache_config_django_redis_unavailable(self, mock_find_spec):
        """Test get_cache_config returns database cache when django_redis unavailable."""
        mock_find_spec.return_value = None  # django_redis not found

        config = get_cache_config()

        self.assertIn("default", config)
        self.assertEqual(
            config["default"]["BACKEND"], "django.core.cache.backends.db.DatabaseCache"
        )
        self.assertEqual(config["default"]["LOCATION"], "cache_table")

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    def test_get_cache_config_invalid_redis_url(self, mock_get_url, mock_find_spec):
        """Test get_cache_config handles invalid Redis URL."""
        mock_find_spec.return_value = MagicMock()  # django_redis available
        mock_get_url.return_value = None  # Invalid URL

        config = get_cache_config()

        self.assertEqual(
            config["default"]["BACKEND"], "django.core.cache.backends.db.DatabaseCache"
        )

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    def test_get_cache_config_redis_available(self, mock_get_url, mock_find_spec):
        """Test get_cache_config returns Redis configuration when available."""
        mock_find_spec.return_value = MagicMock()  # django_redis available
        mock_get_url.return_value = self.test_redis_url

        config = get_cache_config()

        self.assertIn("default", config)
        self.assertEqual(config["default"]["BACKEND"], "django_redis.cache.RedisCache")
        self.assertEqual(config["default"]["LOCATION"], self.test_redis_url)
        self.assertEqual(config["default"]["KEY_PREFIX"], "greylit")

        # Check session cache
        self.assertIn("session", config)
        self.assertEqual(config["session"]["KEY_PREFIX"], "session")

        # Check query cache
        self.assertIn("query", config)
        self.assertEqual(config["query"]["KEY_PREFIX"], "query")

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    @patch("apps.core.redis_config._get_ssl_connection_kwargs")
    def test_get_cache_config_ssl_configuration(
        self, mock_get_ssl_kwargs, mock_get_url, mock_find_spec
    ):
        """Test get_cache_config handles SSL Redis URLs."""
        mock_find_spec.return_value = MagicMock()  # django_redis available
        mock_get_url.return_value = self.test_redis_ssl_url

        # Mock SSL kwargs that would be returned by _get_ssl_connection_kwargs
        import ssl as ssl_module

        mock_ssl_kwargs = {
            "connection_class": "redis.connection.SSLConnection",
            "ssl_cert_reqs": ssl_module.CERT_NONE,
            "ssl_ca_certs": None,
            "ssl_certfile": None,
            "ssl_keyfile": None,
        }
        mock_get_ssl_kwargs.return_value = mock_ssl_kwargs

        config = get_cache_config()

        self.assertEqual(config["default"]["LOCATION"], self.test_redis_ssl_url)

        # Check SSL connection pool kwargs are added
        connection_kwargs = config["default"]["OPTIONS"]["CONNECTION_POOL_KWARGS"]
        self.assertEqual(
            connection_kwargs["connection_class"], "redis.connection.SSLConnection"
        )
        self.assertEqual(connection_kwargs["ssl_cert_reqs"], unittest.mock.ANY)

    @patch("apps.core.redis_config.get_redis_url")
    def test_get_celery_config(self, mock_get_url):
        """Test get_celery_config returns proper Celery configuration."""
        mock_get_url.return_value = self.test_redis_url

        config = get_celery_config()

        assert config is not None
        self.assertEqual(config["broker_url"], self.test_redis_url)
        self.assertEqual(config["result_backend"], self.test_redis_url)
        self.assertEqual(config["task_serializer"], "json")
        self.assertEqual(config["result_serializer"], "json")
        self.assertEqual(config["timezone"], "UTC")
        self.assertTrue(config["enable_utc"])

    def test_get_session_config(self):
        """Test get_session_config returns proper session configuration."""
        config = get_session_config()

        self.assertEqual(
            config["SESSION_ENGINE"], "django.contrib.sessions.backends.cache"
        )
        self.assertEqual(config["SESSION_CACHE_ALIAS"], "session")
        self.assertEqual(config["SESSION_COOKIE_AGE"], 86400)
        self.assertFalse(config["SESSION_EXPIRE_AT_BROWSER_CLOSE"])

    @patch("importlib.util.find_spec")
    def test_check_redis_connection_redis_not_available(self, mock_find_spec):
        """Test check_redis_connection when Redis library not installed."""
        mock_find_spec.return_value = None

        is_connected, message = check_redis_connection()

        self.assertFalse(is_connected)
        self.assertEqual(message, "Redis library not installed")

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    def test_check_redis_connection_invalid_url(self, mock_get_url, mock_find_spec):
        """Test check_redis_connection with invalid URL."""
        mock_find_spec.return_value = MagicMock()  # redis available
        mock_get_url.return_value = None

        is_connected, message = check_redis_connection()

        self.assertFalse(is_connected)
        self.assertIn("Invalid Redis URL", message)

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    @patch("redis.from_url")
    def test_check_redis_connection_success(
        self, mock_redis_from_url, mock_get_url, mock_find_spec
    ):
        """Test check_redis_connection successful connection."""
        mock_find_spec.return_value = MagicMock()  # redis available
        mock_get_url.return_value = self.test_redis_url

        # Mock Redis client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.info.return_value = {
            "redis_version": "6.2.0",
            "used_memory_human": "1.2M",
            "connected_clients": 5,
        }
        mock_redis_from_url.return_value = mock_client

        is_connected, message = check_redis_connection()

        self.assertTrue(is_connected)
        self.assertIn("Redis 6.2.0 connected", message)
        self.assertIn("Memory: 1.2M", message)
        self.assertIn("Clients: 5", message)

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    @patch("redis.from_url")
    def test_check_redis_connection_ssl(
        self, mock_redis_from_url, mock_get_url, mock_find_spec
    ):
        """Test check_redis_connection with SSL URL."""
        mock_find_spec.return_value = MagicMock()  # redis available
        mock_get_url.return_value = self.test_redis_ssl_url

        # Mock Redis client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.info.return_value = {"redis_version": "6.2.0"}
        mock_redis_from_url.return_value = mock_client

        is_connected, message = check_redis_connection()

        self.assertTrue(is_connected)
        # Verify SSL parameters were passed
        call_args = mock_redis_from_url.call_args
        self.assertIn("ssl_cert_reqs", call_args[1])

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    @patch("apps.core.redis_config._create_redis_client")
    @patch("apps.core.redis_config._gather_redis_diagnostics")
    def test_check_redis_connection_failure(
        self, mock_gather_diagnostics, mock_create_client, mock_get_url, mock_find_spec
    ):
        """Test check_redis_connection with connection failure."""
        mock_find_spec.return_value = MagicMock()  # redis available
        mock_get_url.return_value = self.test_redis_url

        # Mock successful client creation
        mock_client = Mock()
        mock_create_client.return_value = mock_client

        # Mock diagnostics showing connection failure
        mock_gather_diagnostics.return_value = (
            False,
            "Redis connection failed: Connection refused",
        )

        is_connected, message = check_redis_connection()

        self.assertFalse(is_connected)
        self.assertIn("Redis connection failed", message)

    @patch("apps.core.redis_config.get_redis_url")
    def test_get_channels_config_invalid_url(self, mock_get_url):
        """Test get_channels_config with invalid Redis URL."""
        mock_get_url.return_value = None

        config = get_channels_config()

        self.assertEqual(
            config["default"]["BACKEND"], "channels.layers.InMemoryChannelLayer"
        )

    @patch("apps.core.redis_config.get_redis_url")
    def test_get_channels_config_redis_url(self, mock_get_url):
        """Test get_channels_config with valid Redis URL."""
        mock_get_url.return_value = self.test_redis_url

        config = get_channels_config()

        self.assertEqual(
            config["default"]["BACKEND"], "channels_redis.core.RedisChannelLayer"
        )
        # Check basic configuration
        self.assertIn("hosts", config["default"]["CONFIG"])

    @patch("apps.core.redis_config.get_redis_url")
    def test_get_channels_config_ssl_url(self, mock_get_url):
        """Test get_channels_config with SSL Redis URL."""
        mock_get_url.return_value = self.test_redis_ssl_url

        config = get_channels_config()

        self.assertEqual(
            config["default"]["BACKEND"], "channels_redis.core.RedisChannelLayer"
        )
        # SSL URLs should be handled as connection strings
        hosts = config["default"]["CONFIG"]["hosts"]  # type: ignore[index]
        self.assertTrue(isinstance(hosts, list))  # type: ignore[index]
        self.assertTrue(len(hosts) > 0)

    def test_get_cache_key_valid_pattern(self):
        """Test get_cache_key with valid pattern."""
        key = get_cache_key("session_list", user_id="123")
        self.assertEqual(key, "sessions:user:123:list")

    def test_get_cache_key_invalid_pattern(self):
        """Test get_cache_key with invalid pattern raises error."""
        with self.assertRaises(ValueError) as context:
            get_cache_key("invalid_pattern", user_id="123")
        self.assertIn("Unknown cache key type", str(context.exception))

    def test_get_cache_key_missing_params(self):
        """Test get_cache_key with missing required parameters."""
        with self.assertRaises(KeyError):
            get_cache_key("session_list")  # Missing user_id parameter

    def test_cache_keys_patterns(self):
        """Test that all cache key patterns are properly defined."""
        expected_keys = [
            "session_list",
            "session_detail",
            "search_results",
            "statistics",
            "report",
            "query_count",
            "user_activity",
        ]

        for key in expected_keys:
            self.assertIn(key, CACHE_KEYS)
            # Ensure patterns contain format placeholders
            pattern = CACHE_KEYS[key]
            if key == "session_list":
                self.assertIn("{user_id}", pattern)
            elif key == "session_detail":
                self.assertIn("{session_id}", pattern)

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    def test_get_cache_config_exception_handling(self, mock_get_url, mock_find_spec):
        """Test get_cache_config handles exceptions gracefully."""
        mock_find_spec.return_value = MagicMock()  # django_redis available
        mock_get_url.side_effect = Exception("Redis URL error")

        config = get_cache_config()

        # Should fall back to database cache
        self.assertEqual(
            config["default"]["BACKEND"], "django.core.cache.backends.db.DatabaseCache"
        )

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    def test_get_cache_config_validation(self, mock_get_url, mock_find_spec):
        """Test get_cache_config validates configuration structure."""
        mock_find_spec.return_value = MagicMock()  # django_redis available
        mock_get_url.return_value = self.test_redis_url

        config = get_cache_config()

        # Verify configuration structure
        self.assertIsInstance(config, dict)
        self.assertIn("default", config)
        self.assertIn("BACKEND", config["default"])

        # Verify OPTIONS are properly configured
        options = config["default"]["OPTIONS"]
        # Note: CLIENT_CLASS was removed in the refactoring as per Django 5.2 deprecation
        self.assertIn("CONNECTION_POOL_KWARGS", options)
        self.assertTrue(options["IGNORE_EXCEPTIONS"])


class RedisConfigIntegrationTestCase(TestCase):
    """Integration tests for Redis configuration behavior."""

    def setUp(self):
        """Set up test environment."""
        self.test_redis_url = "redis://localhost:6379/0"
        self.test_redis_ssl_url = "rediss://user:pass@redis.digitalocean.com:25061/0"

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    def test_redis_unavailable_fallback_chain(self, mock_get_url, mock_find_spec):
        """Test complete fallback chain when Redis is unavailable."""
        mock_find_spec.return_value = None  # No Redis
        mock_get_url.return_value = None  # No Redis URL either

        # Cache config should fall back to database
        cache_config = get_cache_config()
        self.assertEqual(
            cache_config["default"]["BACKEND"],
            "django.core.cache.backends.db.DatabaseCache",
        )

        # Connection check should fail
        is_connected, message = check_redis_connection()
        self.assertFalse(is_connected)
        self.assertEqual(message, "Redis library not installed")

        # Channels should use in-memory backend
        channels_config = get_channels_config()
        self.assertEqual(
            channels_config["default"]["BACKEND"],
            "channels.layers.InMemoryChannelLayer",
        )

    @patch("importlib.util.find_spec")
    @patch("apps.core.redis_config.get_redis_url")
    @patch("redis.from_url")
    def test_redis_available_full_configuration(
        self, mock_redis_from_url, mock_get_url, mock_find_spec
    ):
        """Test complete configuration when Redis is fully available."""
        # Setup mocks
        mock_find_spec.return_value = MagicMock()  # redis available
        mock_get_url.return_value = self.test_redis_url

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.info.return_value = {
            "redis_version": "6.2.0",
            "used_memory_human": "1.2M",
            "connected_clients": 5,
        }
        mock_redis_from_url.return_value = mock_client

        # Test cache configuration
        cache_config = get_cache_config()
        self.assertEqual(
            cache_config["default"]["BACKEND"], "django_redis.cache.RedisCache"
        )

        # Test connection check
        is_connected, message = check_redis_connection()
        self.assertTrue(is_connected)

        # Test Celery configuration
        celery_config = get_celery_config()
        assert celery_config is not None
        self.assertEqual(celery_config["broker_url"], self.test_redis_url)

        # Test session configuration
        session_config = get_session_config()
        self.assertEqual(
            session_config["SESSION_ENGINE"], "django.contrib.sessions.backends.cache"
        )

        # Test channels configuration
        channels_config = get_channels_config()
        self.assertEqual(
            channels_config["default"]["BACKEND"],
            "channels_redis.core.RedisChannelLayer",
        )
