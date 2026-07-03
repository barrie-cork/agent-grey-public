"""
Tests for SafeDatabaseCache backend.
"""

from unittest.mock import MagicMock, patch

from django.test import TransactionTestCase

from apps.core.backends.safe_cache import SafeDatabaseCache, get_safe_cache


class SafeDatabaseCacheTestCase(TransactionTestCase):
    """Test the SafeDatabaseCache backend."""

    def setUp(self):
        """Set up test cache."""
        self.cache = SafeDatabaseCache(
            "test_cache_table",
            {
                "OPTIONS": {
                    "CONNECTION_THRESHOLD": 18,
                    "CONNECTION_THRESHOLD_PGBOUNCER": 80,
                }
            },
        )

    def test_initialization(self):
        """Test cache initialization with options."""
        self.assertEqual(self.cache.connection_threshold, 18)
        self.assertEqual(self.cache.connection_threshold_pgbouncer, 80)

    @patch("apps.core.backends.safe_cache.connections")
    def test_connection_safety_check_safe(self, mock_connections):
        """Test connection safety check when safe to proceed."""
        # Mock cursor and connection check
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (10, 22)  # 10 active, 22 max
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)

        mock_connections.__getitem__.return_value.cursor.return_value = mock_cursor

        is_safe, active, max_conn = self.cache._check_connection_safety()

        self.assertTrue(is_safe)
        self.assertEqual(active, 10)
        self.assertEqual(max_conn, 22)

    @patch("apps.core.backends.safe_cache.connections")
    def test_connection_safety_check_unsafe(self, mock_connections):
        """Test connection safety check when unsafe (too many connections)."""
        # Mock cursor with high connection count
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            19,
            22,
        )  # 19 active, 22 max (above threshold)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)

        mock_connections.__getitem__.return_value.cursor.return_value = mock_cursor

        is_safe, active, max_conn = self.cache._check_connection_safety()

        self.assertFalse(is_safe)
        self.assertEqual(active, 19)
        self.assertEqual(max_conn, 22)

    @patch("apps.core.backends.safe_cache.connections")
    def test_pgbouncer_detection(self, mock_connections):
        """Test pgBouncer detection based on max connections."""
        # Mock cursor with pgBouncer connection count
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (45, 97)  # 45 active, 97 max (pgBouncer)
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)

        mock_connections.__getitem__.return_value.cursor.return_value = mock_cursor

        is_safe, active, max_conn = self.cache._check_connection_safety()

        self.assertTrue(is_safe)  # 45 < 80 (pgBouncer threshold)
        self.assertEqual(max_conn, 97)

    @patch("apps.core.backends.safe_cache.SafeDatabaseCache._check_connection_safety")
    def test_get_with_safe_connections(self, mock_check):
        """Test cache get when connections are safe."""
        mock_check.return_value = (True, 10, 22)

        # Mock the parent class get method
        with patch.object(
            SafeDatabaseCache.__bases__[0], "get", return_value="cached_value"
        ):
            result = self.cache.get("test_key", "default")
            self.assertEqual(result, "cached_value")

    @patch("apps.core.backends.safe_cache.SafeDatabaseCache._check_connection_safety")
    def test_get_with_unsafe_connections(self, mock_check):
        """Test cache get returns default when connections are unsafe."""
        mock_check.return_value = (False, 19, 22)

        result = self.cache.get("test_key", "default_value")
        self.assertEqual(result, "default_value")

    @patch("apps.core.backends.safe_cache.SafeDatabaseCache._check_connection_safety")
    def test_set_with_safe_connections(self, mock_check):
        """Test cache set when connections are safe."""
        mock_check.return_value = (True, 10, 22)

        with patch.object(SafeDatabaseCache.__bases__[0], "set") as mock_set:
            self.cache.set("test_key", "test_value", 300)
            mock_set.assert_called_once_with("test_key", "test_value", 300, None)

    @patch("apps.core.backends.safe_cache.SafeDatabaseCache._check_connection_safety")
    def test_set_with_unsafe_connections(self, mock_check):
        """Test cache set is skipped when connections are unsafe."""
        mock_check.return_value = (False, 19, 22)

        with patch.object(SafeDatabaseCache.__bases__[0], "set") as mock_set:
            self.cache.set("test_key", "test_value", 300)
            mock_set.assert_not_called()

    @patch("apps.core.backends.safe_cache.SafeDatabaseCache._check_connection_safety")
    def test_delete_with_safe_connections(self, mock_check):
        """Test cache delete when connections are safe."""
        mock_check.return_value = (True, 10, 22)

        with patch.object(SafeDatabaseCache.__bases__[0], "delete") as mock_delete:
            self.cache.delete("test_key")
            mock_delete.assert_called_once_with("test_key", None)

    @patch("apps.core.backends.safe_cache.SafeDatabaseCache._check_connection_safety")
    def test_clear_with_unsafe_connections(self, mock_check):
        """Test cache clear is skipped when connections are unsafe."""
        mock_check.return_value = (False, 19, 22)

        with patch.object(SafeDatabaseCache.__bases__[0], "clear") as mock_clear:
            with self.assertLogs(
                "apps.core.backends.safe_cache", level="WARNING"
            ) as logs:
                self.cache.clear()
                mock_clear.assert_not_called()
                self.assertIn("Cache clear skipped", logs.output[0])

    @patch("apps.core.backends.safe_cache.SafeDatabaseCache._check_connection_safety")
    def test_get_many_with_safe_connections(self, mock_check):
        """Test cache get_many when connections are safe."""
        mock_check.return_value = (True, 10, 22)

        with patch.object(
            SafeDatabaseCache.__bases__[0],
            "get_many",
            return_value={"key1": "val1", "key2": "val2"},
        ):
            result = self.cache.get_many(["key1", "key2"])
            self.assertEqual(result, {"key1": "val1", "key2": "val2"})

    @patch("apps.core.backends.safe_cache.SafeDatabaseCache._check_connection_safety")
    def test_get_many_with_unsafe_connections(self, mock_check):
        """Test cache get_many returns empty dict when connections are unsafe."""
        mock_check.return_value = (False, 19, 22)

        result = self.cache.get_many(["key1", "key2"])
        self.assertEqual(result, {})

    def test_get_safe_cache(self):
        """Test get_safe_cache utility function."""
        cache = get_safe_cache()
        self.assertIsNotNone(cache)

    @patch("apps.core.backends.safe_cache.connections")
    def test_connection_check_exception_handling(self, mock_connections):
        """Test exception handling in connection check."""
        # Mock cursor that raises an exception
        mock_connections.__getitem__.side_effect = Exception("Database error")

        is_safe, active, max_conn = self.cache._check_connection_safety()

        self.assertFalse(is_safe)  # Should be unsafe on error
        self.assertEqual(active, 0)
        self.assertEqual(max_conn, 0)

    @patch("apps.core.backends.safe_cache.caches")
    def test_get_safe_cache_with_safe_db_alias(self, mock_caches):
        """Test get_safe_cache when safe_db alias exists."""
        # Create a mock SafeDatabaseCache instance
        mock_safe_cache = MagicMock(spec=SafeDatabaseCache)

        # Mock caches to return our safe cache for 'safe_db'
        mock_caches.__getitem__.side_effect = lambda x: (
            mock_safe_cache if x == "safe_db" else MagicMock()
        )

        cache = get_safe_cache()
        self.assertEqual(cache, mock_safe_cache)

    @patch("apps.core.backends.safe_cache.caches")
    def test_get_safe_cache_without_safe_db_alias(self, mock_caches):
        """Test get_safe_cache falls back to default when safe_db doesn't exist."""
        # Regression test for: 'CacheHandler' object has no attribute 'get' (Issue #61435449)
        mock_default_cache = MagicMock()

        # Mock caches to raise KeyError for 'safe_db', return default for 'default'
        def getitem_side_effect(alias):
            if alias == "safe_db":
                raise KeyError(f"The connection '{alias}' doesn't exist.")
            return mock_default_cache

        mock_caches.__getitem__.side_effect = getitem_side_effect

        cache = get_safe_cache()
        self.assertEqual(cache, mock_default_cache)

    @patch("apps.core.backends.safe_cache.caches")
    def test_get_safe_cache_with_non_safe_cache_backend(self, mock_caches):
        """Test get_safe_cache returns default when safe_db is not SafeDatabaseCache."""
        mock_other_cache = MagicMock()  # Not a SafeDatabaseCache instance
        mock_default_cache = MagicMock()

        def getitem_side_effect(alias):
            if alias == "safe_db":
                return mock_other_cache
            return mock_default_cache

        mock_caches.__getitem__.side_effect = getitem_side_effect

        cache = get_safe_cache()
        self.assertEqual(cache, mock_default_cache)
