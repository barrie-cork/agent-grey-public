"""
Tests for bulk decision functionality in review_results app.
"""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import SimpleReviewDecision
from apps.core.tests.utils import create_test_user

User = get_user_model()


class BulkDecisionTests(TestCase):
    """Test bulk decision API functionality."""

    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = create_test_user()

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="under_review"
        )

        # Create test results
        self.results = []
        for i in range(5):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"https://example.com/result{i + 1}",
                snippet=f"Test snippet {i + 1}",
            )
            self.results.append(result)

        # Log in the test user
        self.client.login(username=self.user.username, password="testpass123")

        # URL for bulk decision API
        self.bulk_url = reverse(
            "review_results:bulk_decision", kwargs={"session_id": self.session.id}
        )

    def test_bulk_exclude_with_reason(self):
        """Test bulk exclude with single reason for multiple results."""
        # Prepare data
        result_ids = [str(r.id) for r in self.results]

        # Make bulk exclude request
        response = self.client.post(
            self.bulk_url,
            {
                "result_ids[]": result_ids,
                "decision": "exclude",
                "exclusion_reason": "not_relevant",
                "notes": "Bulk exclusion test",
            },
        )

        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["processed_count"], 5)
        self.assertEqual(data["decision"], "exclude")

        # Verify database
        for result in self.results:
            decision = SimpleReviewDecision.objects.get(result=result)
            self.assertEqual(decision.decision, "exclude")
            self.assertEqual(decision.exclusion_reason, "not_relevant")
            self.assertEqual(decision.notes, "Bulk exclusion test")
            self.assertEqual(decision.reviewer, self.user)

    def test_bulk_include(self):
        """Test bulk include for multiple results."""
        # Prepare data
        result_ids = [str(r.id) for r in self.results[:3]]

        # Make bulk include request
        response = self.client.post(
            self.bulk_url,
            {
                "result_ids[]": result_ids,
                "decision": "include",
                "notes": "Relevant results",
            },
        )

        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["processed_count"], 3)

        # Verify database
        for result in self.results[:3]:
            decision = SimpleReviewDecision.objects.get(result=result)
            self.assertEqual(decision.decision, "include")
            self.assertEqual(decision.exclusion_reason, "")
            self.assertEqual(decision.notes, "Relevant results")

    def test_bulk_maybe(self):
        """Test bulk maybe decision for multiple results."""
        # Prepare data
        result_ids = [str(r.id) for r in self.results[:2]]

        # Make bulk maybe request
        response = self.client.post(
            self.bulk_url,
            {
                "result_ids[]": result_ids,
                "decision": "maybe",
                "notes": "Need further review",
            },
        )

        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["processed_count"], 2)

        # Verify database
        for result in self.results[:2]:
            decision = SimpleReviewDecision.objects.get(result=result)
            self.assertEqual(decision.decision, "maybe")
            self.assertEqual(decision.notes, "Need further review")

    def test_bulk_exclude_requires_reason(self):
        """Test that bulk exclude requires an exclusion reason."""
        result_ids = [str(self.results[0].id)]

        # Should fail without exclusion_reason
        response = self.client.post(
            self.bulk_url, {"result_ids[]": result_ids, "decision": "exclude"}
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("error", data)

    def test_bulk_limit_100_results(self):
        """Test that bulk operations are limited to 100 results."""
        # Create more than 100 result IDs (they don't need to exist for this test)
        result_ids = [str(uuid.uuid4()) for _ in range(101)]

        response = self.client.post(
            self.bulk_url, {"result_ids[]": result_ids, "decision": "include"}
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        # Check that error message contains information about the limit
        self.assertIn("error", data)

    def test_bulk_update_existing_decisions(self):
        """Test updating existing decisions in bulk."""
        # First create some decisions
        for result in self.results[:3]:
            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.user,
                decision="include",
                notes="Initial decision",
            )

        # Now update them in bulk
        result_ids = [str(r.id) for r in self.results[:3]]
        response = self.client.post(
            self.bulk_url,
            {
                "result_ids[]": result_ids,
                "decision": "exclude",
                "exclusion_reason": "duplicate",
                "notes": "Updated decision",
            },
        )

        # Verify response
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["updated"], 3)
        self.assertEqual(data["created"], 0)

        # Verify database
        for result in self.results[:3]:
            decision = SimpleReviewDecision.objects.get(result=result)
            self.assertEqual(decision.decision, "exclude")
            self.assertEqual(decision.exclusion_reason, "duplicate")
            self.assertEqual(decision.notes, "Updated decision")

    def test_bulk_decision_requires_authentication(self):
        """Test that bulk decision requires user authentication."""
        # Log out
        self.client.logout()

        response = self.client.post(
            self.bulk_url,
            {"result_ids[]": [str(self.results[0].id)], "decision": "include"},
        )

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_bulk_decision_requires_session_ownership(self):
        """Test that users can only bulk update their own sessions."""
        # Create another user and session
        other_user = create_test_user(username_prefix="otheruser")
        other_session = SearchSession.objects.create(
            title="Other Session", owner=other_user, status="under_review"
        )

        # Try to access other user's session
        other_url = reverse(
            "review_results:bulk_decision", kwargs={"session_id": other_session.id}
        )
        response = self.client.post(
            other_url,
            {"result_ids[]": [str(self.results[0].id)], "decision": "include"},
        )

        # Should be forbidden
        self.assertEqual(response.status_code, 403)

    def test_bulk_decision_with_invalid_results(self):
        """Test bulk decision with some invalid result IDs."""
        # Mix valid and invalid IDs
        result_ids = [
            str(self.results[0].id),
            str(uuid.uuid4()),  # Invalid ID
            str(self.results[1].id),
        ]

        response = self.client.post(
            self.bulk_url, {"result_ids[]": result_ids, "decision": "include"}
        )

        # Should fail if any results are not found
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("not found", data["error"].lower())

    def test_empty_result_ids(self):
        """Test that empty result_ids list returns an error."""
        response = self.client.post(
            self.bulk_url, {"result_ids[]": [], "decision": "include"}
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
