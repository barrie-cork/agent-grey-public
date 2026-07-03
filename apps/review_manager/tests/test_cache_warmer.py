"""
Tests for cache warming service.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.review_manager.models import SearchSession
from apps.review_manager.services.cache_warmer import CacheWarmerService
from apps.core.tests.utils import create_test_user


class CacheWarmerTestCase(TestCase):
    """Test cache warming functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.service = CacheWarmerService()

        # Create test sessions in different states
        self.executing_session = SearchSession.objects.create(
            title="Executing Session",
            description="Test session in executing state",
            owner=self.user,
            status="executing",
        )

        self.processing_session = SearchSession.objects.create(
            title="Processing Session",
            description="Test session in processing state",
            owner=self.user,
            status="processing_results",
        )

        self.review_session = SearchSession.objects.create(
            title="Review Session",
            description="Test session under review",
            owner=self.user,
            status="under_review",
        )

    @patch("apps.review_manager.services.cache_warmer.group")
    @patch("apps.review_manager.tasks.cache.warm_session_cache")
    def test_warm_active_session_caches_no_blocking(self, mock_task, mock_group):
        """Test that warm_active_session_caches doesn't block on subtasks."""
        # Set up mock for group
        mock_job = MagicMock()
        mock_group.return_value = mock_job

        # Execute the service method
        result = self.service.warm_active_session_caches()

        # Verify high priority sessions are queued with .delay()
        self.assertEqual(
            mock_task.delay.call_count, 2
        )  # executing and processing sessions

        # Verify the task returns successfully without waiting for results
        self.assertIsInstance(result, dict)
        self.assertIn("total_sessions_queued", result)
        self.assertIn("high_priority_count", result)
        self.assertIn("medium_priority_count", result)

        # Verify counts
        self.assertEqual(result["high_priority_count"], 2)
        self.assertGreaterEqual(
            result["medium_priority_count"], 1
        )  # At least the review session

        # Verify group was called for medium priority sessions
        mock_group.assert_called_once()
        mock_job.apply_async.assert_called_once()

    @patch("apps.review_manager.services.cache_warmer.group")
    @patch("apps.review_manager.tasks.cache.warm_session_cache")
    def test_warm_active_session_caches_handles_errors(self, mock_task, mock_group):
        """Test error handling when queueing fails."""
        # Make delay raise an exception
        mock_task.delay.side_effect = Exception("Redis connection error")
        mock_job = MagicMock()
        mock_group.return_value = mock_job

        # Execute the service method - should not raise exception
        result = self.service.warm_active_session_caches()

        # Verify the task completes even with errors
        self.assertIsInstance(result, dict)
        self.assertEqual(
            result["high_priority_count"], 0
        )  # No sessions queued due to error

    @patch("apps.review_manager.tasks.cache.warm_session_cache")
    def test_warm_active_session_caches_with_no_sessions(self, mock_task):
        """Test behavior when no sessions need warming."""
        # Delete all sessions
        SearchSession.objects.all().delete()

        # Execute the service method
        result = self.service.warm_active_session_caches()

        # Verify it handles empty case gracefully
        self.assertIsInstance(result, dict)
        self.assertEqual(result["total_sessions_queued"], 0)
        self.assertEqual(result["high_priority_count"], 0)
        self.assertEqual(result["medium_priority_count"], 0)
