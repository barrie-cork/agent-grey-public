"""
Tests for cache utilities.
"""

from unittest.mock import MagicMock, patch

from django.core.cache.backends.base import BaseCache
from django.test import TestCase

from apps.core.cache_utils import (
    _get_redis_diagnostics,
    _validate_cache_with_retry,
    get_safe_cache,
    is_cache_available,
    reset_cache_validation,
    safe_cache_add,
    safe_cache_delete,
    safe_cache_get,
    safe_cache_set,
)


class CacheUtilsTestCase(TestCase):
    """Test cache utilities."""

    def setUp(self):
        """Set up test environment."""
        reset_cache_validation()

    def tearDown(self):
        """Clean up after tests."""
        reset_cache_validation()

    @patch("apps.core.cache_utils._get_cache_instance")
    @patch("apps.core.cache_utils.get_env_bool")
    def test_get_safe_cache_with_string_cache(
        self, mock_get_env_bool, mock_get_instance
    ):
        """Test handling when cache is a string instead of cache backend."""
        mock_get_env_bool.return_value = False
        mock_get_instance.return_value = "string_cache"

        result = get_safe_cache()
        # _validate_cache_instance converts strings to DatabaseCache
        from django.core.cache.backends.db import DatabaseCache

        self.assertIsInstance(result, DatabaseCache)

    @patch("apps.core.cache_utils._get_cache_instance")
    @patch("apps.core.cache_utils.get_env_bool")
    def test_get_safe_cache_with_callable_non_backend(
        self, mock_get_env_bool, mock_get_instance
    ):
        """Test handling when cache is callable but not a BaseCache instance."""
        mock_get_env_bool.return_value = False

        mock_cache = MagicMock()
        mock_cache.__class__.__name__ = "MockCache"
        mock_get_instance.return_value = mock_cache

        # Mock validation to fail
        with patch("apps.core.cache_utils._validate_cache_with_retry") as mock_validate:
            mock_validate.return_value = (False, "validation failed")
            result = get_safe_cache()
            # Should return None because validation failed
            self.assertIsNone(result)

    @patch("apps.core.cache_utils._get_cache_instance")
    @patch("apps.core.cache_utils.get_env_bool")
    def test_get_safe_cache_missing_methods(self, mock_get_env_bool, mock_get_instance):
        """Test handling when cache doesn't have required methods."""
        mock_get_env_bool.return_value = False

        mock_cache = MagicMock(spec=[])  # No methods
        mock_cache.__class__.__name__ = "MockCache"
        mock_get_instance.return_value = mock_cache

        result = get_safe_cache()
        from django.core.cache.backends.db import DatabaseCache

        self.assertIsInstance(result, DatabaseCache)

    @patch("apps.core.cache_utils._get_cache_instance")
    @patch("apps.core.cache_utils.get_env_bool")
    def test_get_safe_cache_non_callable_methods(
        self, mock_get_env_bool, mock_get_instance
    ):
        """Test handling when cache methods are not callable."""
        mock_get_env_bool.return_value = False

        mock_cache = MagicMock()
        mock_cache.__class__.__name__ = "MockCache"
        mock_cache.set = "not_callable"
        mock_cache.get = "not_callable"
        # _validate_cache_instance checks hasattr(set/get), which will pass for MagicMock
        # but the validation retry will detect non-callable set
        mock_get_instance.return_value = mock_cache

        with patch("apps.core.cache_utils._validate_cache_with_retry") as mock_validate:
            mock_validate.return_value = (True, "skipped")
            result = get_safe_cache()
            self.assertIsNotNone(result)

    @patch("apps.core.cache_utils._get_cache_instance")
    @patch("apps.core.cache_utils.get_env_bool")
    @patch("apps.core.cache_utils._validate_cache_with_retry")
    def test_get_safe_cache_valid_backend(
        self, mock_validate, mock_get_env_bool, mock_get_instance
    ):
        """Test with a valid cache backend."""
        mock_get_env_bool.return_value = False
        mock_validate.return_value = (True, "")

        mock_cache = MagicMock(spec=BaseCache)
        mock_cache.__class__.__name__ = "RedisCache"
        mock_cache.set = MagicMock()
        mock_cache.get = MagicMock()
        mock_get_instance.return_value = mock_cache

        result = get_safe_cache()
        self.assertEqual(result, mock_cache)

    @patch("apps.core.cache_utils._get_cache_instance")
    @patch("apps.core.cache_utils.get_env_bool")
    def test_get_safe_cache_database_backend_skip_validation(
        self, mock_get_env_bool, mock_get_instance
    ):
        """Test that DatabaseCache backend skips validation."""
        mock_get_env_bool.return_value = False

        mock_cache = MagicMock(spec=BaseCache)
        mock_cache.__class__.__name__ = "DatabaseCache"
        mock_cache.set = MagicMock()
        mock_cache.get = MagicMock()
        mock_get_instance.return_value = mock_cache

        with patch("apps.core.cache_utils._validate_cache_with_retry") as mock_validate:
            result = get_safe_cache()
            self.assertEqual(result, mock_cache)
            # Validation should not be called for DatabaseCache
            mock_validate.assert_not_called()

    @patch("apps.core.cache_utils._get_cache_instance")
    @patch("apps.core.cache_utils.get_env_bool")
    def test_get_safe_cache_skip_validation_env(
        self, mock_get_env_bool, mock_get_instance
    ):
        """Test skipping validation via environment variable."""
        mock_get_env_bool.return_value = True  # skip validation

        mock_cache = MagicMock(spec=BaseCache)
        mock_cache.__class__.__name__ = "RedisCache"
        mock_cache.set = MagicMock()
        mock_cache.get = MagicMock()
        mock_get_instance.return_value = mock_cache

        with patch("apps.core.cache_utils._validate_cache_with_retry") as mock_validate:
            result = get_safe_cache()
            self.assertEqual(result, mock_cache)
            # Validation should not be called when skipped
            mock_validate.assert_not_called()

    def test_get_safe_cache_caches_result(self):
        """Test that get_safe_cache caches its result."""
        reset_cache_validation()

        with patch("apps.core.cache_utils._get_cache_instance") as mock_get_instance:
            with patch("apps.core.cache_utils.get_env_bool") as mock_get_env_bool:
                mock_get_env_bool.return_value = False

                mock_cache = MagicMock(spec=BaseCache)
                mock_cache.__class__.__name__ = "RedisCache"
                mock_cache.set = MagicMock()
                mock_cache.get = MagicMock()
                mock_get_instance.return_value = mock_cache

                with patch(
                    "apps.core.cache_utils._validate_cache_with_retry"
                ) as mock_validate:
                    mock_validate.return_value = (True, "")

                    # First call
                    result1 = get_safe_cache()
                    self.assertEqual(result1, mock_cache)
                    mock_validate.assert_called_once()

                    # Second call should return cached result
                    result2 = get_safe_cache()
                    self.assertEqual(result2, mock_cache)
                    # Validation should still only be called once
                    mock_validate.assert_called_once()

    def test_safe_cache_add(self):
        """Test safe_cache_add function."""
        mock_cache = MagicMock(spec=BaseCache)
        mock_cache.add = MagicMock(return_value=True)

        with patch("apps.core.cache_utils.get_safe_cache", return_value=mock_cache):
            result = safe_cache_add("test_key", "test_value", 60)
            self.assertTrue(result)
            mock_cache.add.assert_called_once_with("test_key", "test_value", 60)

    def test_safe_cache_add_no_cache(self):
        """Test safe_cache_add when cache is not available."""
        with patch("apps.core.cache_utils.get_safe_cache", return_value=None):
            result = safe_cache_add("test_key", "test_value", 60)
            self.assertFalse(result)

    def test_safe_cache_add_exception(self):
        """Test safe_cache_add when cache.add raises exception."""
        mock_cache = MagicMock(spec=BaseCache)
        mock_cache.add = MagicMock(side_effect=Exception("Cache error"))

        with patch("apps.core.cache_utils.get_safe_cache", return_value=mock_cache):
            result = safe_cache_add("test_key", "test_value", 60)
            self.assertFalse(result)

    def test_safe_cache_set(self):
        """Test safe_cache_set function."""
        mock_cache = MagicMock(spec=BaseCache)
        mock_cache.set = MagicMock()

        with patch("apps.core.cache_utils.get_safe_cache", return_value=mock_cache):
            result = safe_cache_set("test_key", "test_value", 60)
            self.assertTrue(result)
            mock_cache.set.assert_called_once_with("test_key", "test_value", 60)

    def test_safe_cache_get(self):
        """Test safe_cache_get function."""
        mock_cache = MagicMock(spec=BaseCache)
        mock_cache.get = MagicMock(return_value="cached_value")

        with patch("apps.core.cache_utils.get_safe_cache", return_value=mock_cache):
            result = safe_cache_get("test_key", default="default")
            self.assertEqual(result, "cached_value")
            mock_cache.get.assert_called_once_with("test_key", "default")

    def test_safe_cache_get_no_cache(self):
        """Test safe_cache_get when cache is not available."""
        with patch("apps.core.cache_utils.get_safe_cache", return_value=None):
            result = safe_cache_get("test_key", default="default")
            self.assertEqual(result, "default")

    def test_safe_cache_delete(self):
        """Test safe_cache_delete function."""
        mock_cache = MagicMock(spec=BaseCache)
        mock_cache.delete = MagicMock()

        with patch("apps.core.cache_utils.get_safe_cache", return_value=mock_cache):
            result = safe_cache_delete("test_key")
            self.assertTrue(result)
            mock_cache.delete.assert_called_once_with("test_key")

    def test_reset_cache_validation(self):
        """Test reset_cache_validation function."""
        with patch("apps.core.cache_utils._get_cache_instance") as mock_get_instance:
            with patch("apps.core.cache_utils.get_env_bool") as mock_get_env_bool:
                mock_get_env_bool.return_value = False

                mock_cache = MagicMock(spec=BaseCache)
                mock_cache.__class__.__name__ = "RedisCache"
                mock_cache.set = MagicMock()
                mock_cache.get = MagicMock()
                mock_get_instance.return_value = mock_cache

                with patch(
                    "apps.core.cache_utils._validate_cache_with_retry"
                ) as mock_validate:
                    mock_validate.return_value = (True, "")

                    # Trigger validation
                    get_safe_cache()
                    mock_validate.assert_called_once()

                    # Reset
                    reset_cache_validation()

                    # Should validate again after reset
                    get_safe_cache()
                    self.assertEqual(mock_validate.call_count, 2)

    def test_is_cache_available(self):
        """Test is_cache_available function."""
        mock_cache = MagicMock(spec=BaseCache)

        with patch("apps.core.cache_utils.get_safe_cache", return_value=mock_cache):
            self.assertTrue(is_cache_available())

        with patch("apps.core.cache_utils.get_safe_cache", return_value=None):
            self.assertFalse(is_cache_available())

    def test_validate_cache_with_retry_success(self):
        """Test _validate_cache_with_retry with successful validation."""
        mock_cache = MagicMock(spec=BaseCache)

        stored_value = {}

        def mock_set(key, value, timeout):
            stored_value[key] = value
            return True

        def mock_get(key):
            return stored_value.get(key)

        mock_cache.set = MagicMock(side_effect=mock_set)
        mock_cache.get = MagicMock(side_effect=mock_get)
        mock_cache.delete = MagicMock(return_value=True)

        with patch("apps.core.cache_utils.get_env_int") as mock_get_env_int:
            with patch("apps.core.cache_utils.get_env_float") as mock_get_env_float:
                mock_get_env_int.side_effect = [60, 3]  # timeout, max_attempts
                mock_get_env_float.return_value = 0.01  # Short delay for test

                is_valid, error = _validate_cache_with_retry(mock_cache, "TestCache")
                self.assertTrue(is_valid)
                self.assertEqual(error, "")

    def test_validate_cache_with_retry_failure(self):
        """Test _validate_cache_with_retry with failed validation."""
        mock_cache = MagicMock(spec=BaseCache)
        mock_cache.set = MagicMock()
        mock_cache.get = MagicMock(return_value=None)
        mock_cache.delete = MagicMock()

        with patch("apps.core.cache_utils.get_env_int") as mock_get_env_int:
            with patch("apps.core.cache_utils.get_env_float") as mock_get_env_float:
                mock_get_env_int.side_effect = [60, 1]  # timeout, max_attempts
                mock_get_env_float.return_value = 0.01

                is_valid, error = _validate_cache_with_retry(mock_cache, "TestCache")
                self.assertFalse(is_valid)
                self.assertIn("Cache validation failed", error)

    def test_get_redis_diagnostics(self):
        """Test _get_redis_diagnostics function."""
        # Test non-Redis backend
        diagnostics = _get_redis_diagnostics("DatabaseCache")
        self.assertFalse(diagnostics["redis_available"])
        self.assertEqual(diagnostics["error"], "Not a Redis backend")

        # Test Redis backend name
        diagnostics = _get_redis_diagnostics("RedisCache")
        self.assertIsInstance(diagnostics["redis_available"], bool)
        self.assertIn("error", diagnostics)
        self.assertIn("connection_info", diagnostics)
        self.assertEqual(diagnostics["backend"], "RedisCache")
