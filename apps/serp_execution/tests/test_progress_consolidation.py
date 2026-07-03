from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.core.progress.tracker import progress_tracker
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestProgressConsolidation(TestCase):
    """Test that all progress goes through ProgressTracker."""

    def setUp(self):
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        # Create a test session
        self.session = SearchSession.objects.create(
            owner=self.user, title="Test Session", status="executing"
        )
        self.session_id = str(self.session.id)

    @patch("apps.review_manager.models.SearchSession.update_status_detail")
    def test_execution_uses_session_status_updates(self, mock_update_detail):
        """Verify handle_progress_updates calls session.update_status_detail."""
        from apps.serp_execution.tasks.execution_helpers import handle_progress_updates

        # Call the helper function
        handle_progress_updates(
            session_id=self.session_id,
            execution=MagicMock(id="test-exec-123"),
            phase="executing",
            message="Test message",
            processed_count=10,
            total_count=20,
        )

        # Verify session status was updated
        mock_update_detail.assert_called_once_with("Test message")

    def test_no_percentage_in_api_response(self):
        """Verify API responses don't include percentage fields."""
        # First update progress so there's something to fetch
        progress_tracker.update_progress(
            session_id=self.session_id,
            component="executing",
            current_step="Test step",
            processed_count=5,
            total_count=10,
        )

        # Test session progress API
        response = self.client.get(
            f"/execution/api/session/{self.session_id}/progress/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # These fields should NOT exist
        self.assertNotIn("percentage", data)
        self.assertNotIn("overall_progress", data)
        self.assertNotIn("progress", data)

        # These fields SHOULD exist
        self.assertIn("current_step", data)
        self.assertIn("status", data)

    def test_query_progress_api_no_percentage(self):
        """Verify query progress API doesn't return percentages."""
        # Need to create a strategy first
        from apps.search_strategy.models import SearchStrategy

        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
        )

        # Create a test query
        _query = SearchQuery.objects.create(
            session=self.session, strategy=strategy, query_text="test query"
        )

        # Test query progress API
        response = self.client.get(
            f"/execution/api/session/{self.session_id}/query-progress/"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Check overall response
        self.assertNotIn("overall_progress", data)
        self.assertNotIn("progress", data)
        self.assertNotIn("percentage", data)

        # Check individual query entries
        if "queries" in data and len(data["queries"]) > 0:
            for query_data in data["queries"]:
                self.assertNotIn("progress_percentage", query_data)
                self.assertNotIn("percentage", query_data)

    def test_progress_tracker_has_no_percentage_methods(self):
        """Verify ProgressTracker doesn't have percentage calculation methods."""
        # These methods should NOT exist
        self.assertFalse(hasattr(progress_tracker, "_calculate_global_progress"))
        self.assertFalse(hasattr(progress_tracker, "PROGRESS_RANGES"))
        self.assertFalse(hasattr(progress_tracker, "DEFAULT_PROGRESS_RANGES"))

        # These methods SHOULD exist
        self.assertTrue(hasattr(progress_tracker, "update_progress"))
        self.assertTrue(hasattr(progress_tracker, "get_progress"))
        self.assertTrue(hasattr(progress_tracker, "reset_progress"))

    def test_progress_tracker_returns_correct_format(self):
        """Verify ProgressTracker returns data in the correct format."""
        # Update progress
        progress_tracker.update_progress(
            session_id=self.session_id,
            component="executing",
            current_step="Testing step",
            processed_count=5,
            total_count=10,
            metadata={"test": "data"},
        )

        # Get progress
        progress_data = progress_tracker.get_progress(self.session_id)

        # Verify format
        self.assertIn("status", progress_data)
        self.assertIn("component", progress_data)
        self.assertIn("current_step", progress_data)
        self.assertIn("processed_count", progress_data)
        self.assertIn("total_count", progress_data)

        # Ensure no percentage fields
        self.assertNotIn("percentage", progress_data)
        self.assertNotIn("progress", progress_data)
        self.assertNotIn("overall_progress", progress_data)
