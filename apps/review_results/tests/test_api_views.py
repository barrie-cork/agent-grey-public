"""
Tests for review_results API views after TypedDict migration.

This module tests the API endpoints to ensure they continue working
correctly after migrating from Pydantic validation to TypedDict responses.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession

from ..models import SimpleReviewDecision
from apps.core.tests.utils import create_test_user

User = get_user_model()


class APIViewsTypeValidationTestCase(TestCase):
    """Test API endpoints return properly typed responses after TypedDict migration."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="under_review"
        )
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            processing_status="success",
        )
        self.client.login(username=self.user.username, password="testpass123")

    def test_make_decision_api_response_structure(self):
        """Test that MakeDecisionAPIView returns correctly structured TypedDict response."""
        url = reverse(
            "review_results:make_decision_api",
            kwargs={"session_id": str(self.session.id)},
        )

        response = self.client.post(
            url,
            {
                "result_id": str(self.result.id),
                "decision": "include",
                "notes": "Test notes",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify response structure matches ReviewDecisionResponse TypedDict
        required_fields = {"success", "decision", "result_id", "message"}
        self.assertTrue(required_fields.issubset(data.keys()))

        # Verify field types
        self.assertIsInstance(data["success"], bool)
        self.assertIsInstance(data["decision"], str)
        self.assertIsInstance(data["result_id"], str)
        self.assertIsInstance(data["message"], str)

        self.assertTrue(data["success"])
        self.assertEqual(data["decision"], "include")

    def test_session_stats_api_response_structure(self):
        """Test that GetSessionStatsAPIView returns correctly structured TypedDict response."""
        # Create a review decision first
        SimpleReviewDecision.objects.create(
            result=self.result,
            session=self.session,
            reviewer=self.user,
            decision="include",
        )

        url = reverse(
            "review_results:session_stats_api",
            kwargs={"session_id": str(self.session.id)},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify response structure matches SessionStatsResponse TypedDict
        required_fields = {"success", "progress"}
        self.assertTrue(required_fields.issubset(data.keys()))

        # Verify field types
        self.assertIsInstance(data["success"], bool)
        self.assertIsInstance(data["progress"], dict)

        self.assertTrue(data["success"])

    def test_error_response_structure(self):
        """Test that API endpoints return correctly structured error responses."""
        url = reverse(
            "review_results:make_decision_api",
            kwargs={"session_id": str(self.session.id)},
        )

        # Send invalid data to trigger error response
        response = self.client.post(
            url,
            {
                "result_id": "",  # Empty result_id should cause error
                "decision": "include",
            },
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()

        # Verify error response structure matches ErrorResponse TypedDict
        required_fields = {"success", "error"}
        self.assertTrue(required_fields.issubset(data.keys()))

        # Verify field types
        self.assertIsInstance(data["success"], bool)
        self.assertIsInstance(data["error"], str)

        self.assertFalse(data["success"])

    def test_notes_update_response_structure(self):
        """Test that UpdateNotesAPIView returns correctly structured TypedDict response."""
        # Create a review decision first
        _decision = SimpleReviewDecision.objects.create(
            result=self.result,
            session=self.session,
            reviewer=self.user,
            decision="pending",
        )

        url = reverse(
            "review_results:update_notes_api",
            kwargs={"session_id": str(self.session.id)},
        )
        response = self.client.post(
            url, {"result_id": str(self.result.id), "notes": "Updated test notes"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify response structure matches NotesUpdateResponse TypedDict
        required_fields = {"success", "message"}
        self.assertTrue(required_fields.issubset(data.keys()))

        # Verify field types
        self.assertIsInstance(data["success"], bool)
        self.assertIsInstance(data["message"], str)

        self.assertTrue(data["success"])

    def test_url_access_response_structure(self):
        """Test that TrackURLAccessAPIView returns correctly structured TypedDict response."""
        url = reverse(
            "review_results:track_url_access_api",
            kwargs={"session_id": str(self.session.id)},
        )
        response = self.client.post(
            url, {"result_id": str(self.result.id), "url": "https://example.com/test"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify response structure matches URLAccessResponse TypedDict
        required_fields = {"success", "message", "created"}
        self.assertTrue(required_fields.issubset(data.keys()))

        # Verify field types
        self.assertIsInstance(data["success"], bool)
        self.assertIsInstance(data["message"], str)
        self.assertIsInstance(data["created"], bool)

        self.assertTrue(data["success"])
