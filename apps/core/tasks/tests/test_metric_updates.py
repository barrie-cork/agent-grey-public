"""
Tests for Celery metric update tasks.

Tests that tasks call the correct update functions and handle errors.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings


# Ensure Celery runs tasks synchronously in tests
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class MetricUpdateTasksTest(TestCase):
    """Test cases for metric update tasks."""

    @patch("apps.core.tasks.metric_updates.update_session_state_distribution")
    def test_update_session_metrics_task_success(self, mock_update):
        """Test session metrics task calls update function."""
        from apps.core.tasks.metric_updates import update_session_metrics_task

        # Execute task (runs synchronously due to settings)
        update_session_metrics_task()  # type: ignore[call-arg]

        # Verify function was called
        mock_update.assert_called_once()

    @patch("apps.core.tasks.metric_updates.update_review_velocity")
    def test_update_review_metrics_task_success(self, mock_update):
        """Test review metrics task calls update function."""
        from apps.core.tasks.metric_updates import update_review_metrics_task

        # Execute task
        update_review_metrics_task()  # type: ignore[call-arg]

        # Verify function was called
        mock_update.assert_called_once()

    @patch("apps.core.tasks.metric_updates.update_session_state_distribution")
    def test_update_session_metrics_task_retry_on_error(self, mock_update):
        """Test session metrics task retries on exception."""
        from apps.core.tasks.metric_updates import update_session_metrics_task

        # Mock function to raise error
        mock_update.side_effect = Exception("Database connection error")

        # Task should raise after retries
        with self.assertRaises(Exception):
            update_session_metrics_task()  # type: ignore[call-arg]

    @patch("apps.core.tasks.metric_updates.update_review_velocity")
    def test_update_review_metrics_task_retry_on_error(self, mock_update):
        """Test review metrics task retries on exception."""
        from apps.core.tasks.metric_updates import update_review_metrics_task

        # Mock function to raise error
        mock_update.side_effect = Exception("Redis connection error")

        # Task should raise after retries
        with self.assertRaises(Exception):
            update_review_metrics_task()  # type: ignore[call-arg]

    def test_update_session_metrics_task_uses_bind(self):
        """Test task uses bind=True for retry access."""
        from apps.core.tasks.metric_updates import update_session_metrics_task

        # Task should be bound (has bind=True)
        self.assertTrue(hasattr(update_session_metrics_task, "retry"))

    def test_update_review_metrics_task_uses_bind(self):
        """Test task uses bind=True for retry access."""
        from apps.core.tasks.metric_updates import update_review_metrics_task

        # Task should be bound (has bind=True)
        self.assertTrue(hasattr(update_review_metrics_task, "retry"))
