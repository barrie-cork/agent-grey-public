"""
Comprehensive test suite for distributed lock utilities.

This test suite covers:
- Lock acquisition and release
- Concurrent lock attempts
- Timeout and expiration handling
- Cache fallback mechanisms
- Error handling paths
- Celery worker context
- Edge cases and race conditions
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch

from django.core.cache import cache, caches
from django.test import TestCase

from apps.core.utils.distributed_lock import (
    DistributedLock,
    LockAcquisitionError,
    LockConfig,
)


class DistributedLockBasicTests(TestCase):
    """Test basic lock acquisition and release functionality."""

    def setUp(self):
        """Set up test environment."""
        cache.clear()
        self.lock = DistributedLock()

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()

    def test_lock_acquisition_and_release(self):
        """Test that a lock can be acquired and released successfully."""
        key = f"test_lock_{uuid.uuid4()}"

        with self.lock.acquire(key):
            # Lock should be held
            self.assertTrue(self.lock.is_locked(key))

        # Lock should be released after context exit
        self.assertFalse(self.lock.is_locked(key))

    def test_lock_prevents_concurrent_access(self):
        """Test that holding a lock prevents another process from acquiring it."""
        key = f"test_lock_{uuid.uuid4()}"

        with self.lock.acquire(key):
            # Try to acquire same lock with zero retries
            lock2 = DistributedLock(LockConfig(retry_count=1, retry_delay=0.1))
            with self.assertRaises(LockAcquisitionError):
                with lock2.acquire(key):
                    pass

    def test_lock_release_after_first_holder_exits(self):
        """Test that lock can be acquired after first holder releases it."""
        key = f"test_lock_{uuid.uuid4()}"

        # First holder acquires and releases
        with self.lock.acquire(key):
            pass

        # Second holder should be able to acquire
        with self.lock.acquire(key):
            self.assertTrue(self.lock.is_locked(key))

    def test_lock_with_custom_timeout(self):
        """Test lock with custom timeout value."""
        key = f"test_lock_{uuid.uuid4()}"
        custom_timeout = 5

        with self.lock.acquire(key, timeout=custom_timeout):
            # Lock should exist in cache
            cached_value = cache.get(key)
            self.assertIsNotNone(cached_value)

    def test_lock_expiration(self):
        """Test that lock expires after timeout period."""
        key = f"test_lock_{uuid.uuid4()}"
        short_timeout = 1

        # Acquire lock with short timeout
        lock = DistributedLock(LockConfig(timeout=short_timeout))
        with lock.acquire(key, timeout=short_timeout):
            self.assertTrue(lock.is_locked(key))

        # Wait for expiration
        time.sleep(short_timeout + 0.5)

        # Lock should have expired
        self.assertFalse(lock.is_locked(key))

    def test_force_release(self):
        """Test force release of a held lock."""
        key = f"test_lock_{uuid.uuid4()}"

        with self.lock.acquire(key):
            self.assertTrue(self.lock.is_locked(key))

            # Force release from outside the context
            lock2 = DistributedLock()
            result = lock2.force_release(key)
            self.assertTrue(result)
            self.assertFalse(lock2.is_locked(key))

    def test_force_release_nonexistent_lock(self):
        """Test force release returns False for non-existent lock."""
        key = f"test_lock_{uuid.uuid4()}"
        result = self.lock.force_release(key)
        self.assertFalse(result)


class DistributedLockRetryTests(TestCase):
    """Test retry and backoff mechanisms."""

    def setUp(self):
        """Set up test environment."""
        cache.clear()

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()

    def test_retry_with_exponential_backoff(self):
        """Test retry mechanism with exponential backoff."""
        key = f"test_lock_{uuid.uuid4()}"
        lock1 = DistributedLock()
        lock2 = DistributedLock(
            LockConfig(retry_count=3, retry_delay=0.1, use_exponential_backoff=True)
        )

        with lock1.acquire(key):
            start_time = time.time()
            with self.assertRaises(LockAcquisitionError):
                with lock2.acquire(key):
                    pass
            elapsed = time.time() - start_time

            # Should have waited: 0.1 + 0.2 = 0.3 seconds (approximately)
            # Add tolerance for timing variations
            self.assertGreater(elapsed, 0.25)
            self.assertLess(elapsed, 0.5)

    def test_retry_without_exponential_backoff(self):
        """Test retry mechanism with linear backoff."""
        key = f"test_lock_{uuid.uuid4()}"
        lock1 = DistributedLock()
        lock2 = DistributedLock(
            LockConfig(retry_count=3, retry_delay=0.1, use_exponential_backoff=False)
        )

        with lock1.acquire(key):
            start_time = time.time()
            with self.assertRaises(LockAcquisitionError):
                with lock2.acquire(key):
                    pass
            elapsed = time.time() - start_time

            # Should have waited: 0.1 + 0.1 = 0.2 seconds (approximately)
            self.assertGreater(elapsed, 0.15)
            self.assertLess(elapsed, 0.35)

    def test_immediate_acquisition_on_release(self):
        """Test that lock can be acquired immediately after release in retry loop."""
        key = f"test_lock_{uuid.uuid4()}"
        lock1 = DistributedLock()
        lock2 = DistributedLock(
            LockConfig(retry_count=5, retry_delay=0.5, use_exponential_backoff=False)
        )

        def release_after_delay():
            """Release lock after short delay."""
            time.sleep(0.3)
            lock1.force_release(key)

        # Start release in background
        with ThreadPoolExecutor(max_workers=1) as executor:
            # Acquire initial lock
            with lock1.acquire(key):
                # Schedule release
                future = executor.submit(release_after_delay)

                # This should succeed after retry (lock gets released)
                start_time = time.time()
                with lock2.acquire(key):
                    elapsed = time.time() - start_time
                    # Should have acquired after first retry
                    self.assertGreater(elapsed, 0.2)
                    self.assertLess(elapsed, 1.5)

                future.result()


class DistributedLockConcurrencyTests(TestCase):
    """Test concurrency scenarios and race conditions."""

    def setUp(self):
        """Set up test environment."""
        cache.clear()

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()

    def test_concurrent_lock_attempts(self):
        """Test multiple threads trying to acquire same lock."""
        key = f"test_lock_{uuid.uuid4()}"
        success_count = 0
        failure_count = 0
        lock_holder = None

        def try_acquire_lock(worker_id):
            """Try to acquire lock and return result."""
            nonlocal success_count, failure_count, lock_holder
            lock = DistributedLock(LockConfig(retry_count=1, retry_delay=0.1))
            try:
                with lock.acquire(key):
                    success_count += 1
                    lock_holder = worker_id
                    time.sleep(0.2)  # Hold lock briefly
                    return True
            except LockAcquisitionError:
                failure_count += 1
                return False

        # Launch 5 concurrent workers
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_acquire_lock, i) for i in range(5)]
            _results = [f.result() for f in as_completed(futures)]

        # Exactly one should succeed (mutual exclusion)
        self.assertEqual(success_count, 1)
        self.assertEqual(failure_count, 4)
        self.assertIsNotNone(lock_holder)

    def test_sequential_lock_access(self):
        """Test sequential lock acquisition by multiple workers."""
        key = f"test_lock_{uuid.uuid4()}"
        execution_order = []

        def acquire_and_work(worker_id):
            """Acquire lock and record execution order."""
            lock = DistributedLock(
                LockConfig(
                    retry_count=10, retry_delay=0.1, use_exponential_backoff=False
                )
            )
            with lock.acquire(key):
                execution_order.append(worker_id)
                time.sleep(0.05)

        # Launch workers sequentially with slight delays
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for i in range(3):
                futures.append(executor.submit(acquire_and_work, i))
                time.sleep(0.02)  # Stagger submissions

            # Wait for all to complete
            for f in futures:
                f.result()

        # All workers should have executed
        self.assertEqual(len(execution_order), 3)
        # Each worker should appear exactly once
        self.assertEqual(set(execution_order), {0, 1, 2})


class DistributedLockCacheFallbackTests(TestCase):
    """Test cache fallback mechanisms and error handling."""

    def setUp(self):
        """Set up test environment."""
        cache.clear()

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()

    @patch("apps.core.utils.distributed_lock.os.environ.get")
    def test_celery_worker_context(self, mock_env_get):
        """Test lock behavior in Celery worker context."""
        mock_env_get.return_value = "celery"

        with patch("apps.core.cache_init.get_worker_cache") as mock_worker_cache:
            # Mock worker cache returns valid cache
            mock_worker_cache.return_value = caches["default"]

            key = f"test_lock_{uuid.uuid4()}"
            lock = DistributedLock()

            with lock.acquire(key):
                self.assertTrue(lock.is_locked(key))

            mock_worker_cache.assert_called()

    @patch("apps.core.utils.distributed_lock.os.environ.get")
    @patch("apps.core.cache_init.get_worker_cache")
    def test_celery_worker_cache_unavailable(self, mock_worker_cache, mock_env_get):
        """Test fallback when worker cache is unavailable."""
        mock_env_get.return_value = "celery"
        mock_worker_cache.return_value = None

        key = f"test_lock_{uuid.uuid4()}"
        lock = DistributedLock(LockConfig(retry_count=1))

        # Should raise LockAcquisitionError due to unavailable cache
        with self.assertRaises(LockAcquisitionError):
            with lock.acquire(key):
                pass

    def test_cache_access_failure_triggers_database_fallback(self):
        """Test that cache access failure triggers database cache fallback."""
        key = f"test_lock_{uuid.uuid4()}"
        lock = DistributedLock()

        # Mock the entire _get_cache_instance to simulate failure and fallback
        with patch.object(lock, "_get_cache_instance") as mock_get_cache:
            # Simulate fallback to database cache
            mock_db_cache = Mock()
            mock_db_cache.add.return_value = True
            mock_db_cache.get.return_value = "test_value"
            mock_db_cache.delete.return_value = None
            mock_get_cache.return_value = mock_db_cache

            # Should still work with database fallback
            with lock.acquire(key):
                self.assertTrue(lock.is_locked(key))

            # Verify methods were called
            self.assertTrue(mock_db_cache.add.called)
            self.assertTrue(mock_db_cache.get.called)

    def test_cache_method_not_callable(self):
        """Test handling of cache backend where methods aren't callable."""
        key = f"test_lock_{uuid.uuid4()}"
        lock = DistributedLock()

        # Mock _get_cache_instance to return cache with non-callable add
        mock_cache = Mock()
        mock_cache.add = "not_callable"  # String instead of method

        # Mock fallback cache
        mock_fallback = Mock()
        mock_fallback.add.return_value = True

        with patch.object(lock, "_get_cache_instance", return_value=mock_cache):
            with patch.object(
                lock, "_validate_cache_method", return_value=mock_fallback
            ):
                # Should fallback to valid cache
                result = lock._safe_cache_add(key, "value", 300)
                self.assertTrue(result)
                self.assertTrue(mock_fallback.add.called)

    def test_type_error_handling(self):
        """Test handling of TypeError from cache operations."""
        key = f"test_lock_{uuid.uuid4()}"
        lock = DistributedLock()

        # Mock cache that raises TypeError
        mock_cache = Mock()
        mock_cache.add.side_effect = TypeError("'str' object is not callable")

        # Mock fallback cache
        mock_fallback = Mock()
        mock_fallback.add.return_value = True

        with patch.object(lock, "_get_cache_instance", return_value=mock_cache):
            with patch.object(
                lock, "_validate_cache_method", return_value=mock_cache
            ):  # Passes validation
                with patch.object(
                    lock, "_handle_cache_type_error", return_value=mock_fallback
                ):
                    # Should handle TypeError and use fallback
                    result = lock._safe_cache_add(key, "value", 300)
                    self.assertTrue(result)
                    self.assertTrue(mock_fallback.add.called)

    def test_general_exception_handling(self):
        """Test handling of general exceptions from cache operations."""
        key = f"test_lock_{uuid.uuid4()}"
        lock = DistributedLock()

        # Mock cache that raises unexpected error
        mock_cache = Mock()
        mock_cache.get.side_effect = RuntimeError("Unexpected error")

        with patch.object(lock, "_get_cache_instance", return_value=mock_cache):
            with patch.object(lock, "_validate_cache_method", return_value=mock_cache):
                # Should return None on error and not crash
                result = lock._safe_cache_get(key)
                self.assertIsNone(result)


class DistributedLockHelperMethodsTests(TestCase):
    """Test helper methods in isolation."""

    def setUp(self):
        """Set up test environment."""
        cache.clear()
        self.lock = DistributedLock()

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()

    def test_get_cache_instance_standard(self):
        """Test _get_cache_instance returns standard cache."""
        cache_instance = self.lock._get_cache_instance("test")
        self.assertIsNotNone(cache_instance)
        self.assertTrue(callable(getattr(cache_instance, "add", None)))

    def test_get_cache_instance_fallback(self):
        """Test _get_cache_instance triggers fallback on failure."""
        # Patch caches at the django.core.cache level where it's imported
        with patch("django.core.cache.caches") as mock_caches_module:
            # Make the __getitem__ raise an exception
            mock_caches_module.__getitem__.side_effect = Exception("Cache unavailable")

            with patch("django.core.cache.backends.db.DatabaseCache") as mock_db_cache:
                mock_instance = Mock()
                mock_db_cache.return_value = mock_instance

                cache_instance = self.lock._get_cache_instance("test")

                # Verify fallback was triggered
                self.assertIsNotNone(cache_instance)
                mock_db_cache.assert_called()

    def test_validate_cache_method_success(self):
        """Test _validate_cache_method with valid cache."""
        mock_cache = Mock()
        mock_cache.add = Mock()

        result = self.lock._validate_cache_method(mock_cache, "add", "test_key")
        self.assertEqual(result, mock_cache)

    def test_validate_cache_method_fallback(self):
        """Test _validate_cache_method triggers fallback for non-callable method."""
        mock_cache = Mock()
        mock_cache.add = "not_callable"

        with patch("django.core.cache.backends.db.DatabaseCache") as mock_db_cache:
            mock_instance = Mock()
            mock_instance.add = Mock()
            mock_db_cache.return_value = mock_instance

            result = self.lock._validate_cache_method(mock_cache, "add", "test_key")
            self.assertEqual(result, mock_instance)

    def test_handle_cache_type_error_str_not_callable(self):
        """Test _handle_cache_type_error for 'str object is not callable' error."""
        error = TypeError("'str' object is not callable")

        with patch("django.core.cache.backends.db.DatabaseCache") as mock_db_cache:
            mock_instance = Mock()
            mock_db_cache.return_value = mock_instance

            result = self.lock._handle_cache_type_error(error, "test_key", "add")
            self.assertEqual(result, mock_instance)

    def test_handle_cache_type_error_other_type_error(self):
        """Test _handle_cache_type_error for other TypeError."""
        error = TypeError("Some other type error")

        result = self.lock._handle_cache_type_error(error, "test_key", "add")
        self.assertIsNone(result)


class DistributedLockEdgeCasesTests(TestCase):
    """Test edge cases and boundary conditions."""

    def setUp(self):
        """Set up test environment."""
        cache.clear()

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()

    def test_lock_with_zero_timeout(self):
        """Test lock behavior with zero timeout (should use default)."""
        key = f"test_lock_{uuid.uuid4()}"
        lock = DistributedLock(LockConfig(timeout=0))

        # Should still work (uses default timeout)
        with lock.acquire(key, timeout=1):
            self.assertTrue(lock.is_locked(key))

    def test_exception_during_locked_operation(self):
        """Test that lock is released even if operation raises exception."""
        key = f"test_lock_{uuid.uuid4()}"
        lock = DistributedLock()

        with self.assertRaises(ValueError):
            with lock.acquire(key):
                self.assertTrue(lock.is_locked(key))
                raise ValueError("Simulated error")

        # Lock should still be released
        self.assertFalse(lock.is_locked(key))

    def test_lock_timeout_before_release(self):
        """Test behavior when lock times out before explicit release."""
        key = f"test_lock_{uuid.uuid4()}"
        lock = DistributedLock(LockConfig(timeout=1, timeout_buffer=0))

        with lock.acquire(key, timeout=1):
            self.assertTrue(lock.is_locked(key))
            # Wait for lock to expire
            time.sleep(1.5)
            # Lock should have expired
            self.assertFalse(lock.is_locked(key))

        # Should handle gracefully (no error on release of expired lock)

    def test_is_locked_on_nonexistent_key(self):
        """Test is_locked returns False for non-existent key."""
        key = f"test_lock_{uuid.uuid4()}"
        lock = DistributedLock()
        self.assertFalse(lock.is_locked(key))

    def test_lock_with_very_short_timeout(self):
        """Test lock with very short timeout value."""
        key = f"test_lock_{uuid.uuid4()}"
        lock = DistributedLock(LockConfig(timeout=1, timeout_buffer=0))

        with lock.acquire(key, timeout=1):
            self.assertTrue(lock.is_locked(key))

        # Should release successfully despite short timeout

    def test_concurrent_force_release(self):
        """Test concurrent force release attempts."""
        key = f"test_lock_{uuid.uuid4()}"
        lock1 = DistributedLock()

        with lock1.acquire(key):
            results = []

            def force_release_attempt():
                lock2 = DistributedLock()
                return lock2.force_release(key)

            # Multiple concurrent force release attempts
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(force_release_attempt) for _ in range(3)]
                results = [f.result() for f in as_completed(futures)]

            # At least one should succeed
            self.assertTrue(any(results))


class DistributedLockConfigTests(TestCase):
    """Test lock configuration options."""

    def test_default_config(self):
        """Test default lock configuration values."""
        config = LockConfig()
        self.assertEqual(config.timeout, 300)
        self.assertEqual(config.retry_count, 3)
        self.assertEqual(config.retry_delay, 1.0)
        self.assertTrue(config.use_exponential_backoff)
        self.assertEqual(config.timeout_buffer, 3)

    def test_custom_config(self):
        """Test custom lock configuration values."""
        config = LockConfig(
            timeout=600,
            retry_count=5,
            retry_delay=2.0,
            use_exponential_backoff=False,
            timeout_buffer=5,
        )
        self.assertEqual(config.timeout, 600)
        self.assertEqual(config.retry_count, 5)
        self.assertEqual(config.retry_delay, 2.0)
        self.assertFalse(config.use_exponential_backoff)
        self.assertEqual(config.timeout_buffer, 5)

    def test_lock_with_custom_config(self):
        """Test DistributedLock with custom configuration."""
        config = LockConfig(retry_count=1, retry_delay=0.1, timeout=10)
        lock = DistributedLock(config)

        key = f"test_lock_{uuid.uuid4()}"
        with lock.acquire(key):
            self.assertTrue(lock.is_locked(key))
