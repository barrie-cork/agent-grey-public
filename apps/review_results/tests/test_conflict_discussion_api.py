"""
Tests for Conflict Discussion API endpoints (Phase 05).

Tests the following endpoints:
- GET /api/conflicts/?session_id={uuid} - List conflicts
- GET /api/conflicts/{id}/ - Conflict detail with decisions
- POST /api/conflicts/{id}/discuss/ - Create comment
- POST /api/conflicts/{id}/resolve/ - Mark resolved
"""

import json
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import SearchSession, ReviewConfiguration
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import (
    ConflictResolution,
    ConflictComment,
    ReviewerDecision,
)
from apps.core.tests.utils import DisablePersonalOrgSignalMixin, create_test_user

User = get_user_model()


class ConflictDiscussionAPITestCase(DisablePersonalOrgSignalMixin, TestCase):
    """Test case for Conflict Discussion API endpoints."""

    def setUp(self):
        """Set up test data."""
        # Create test users
        self.user1 = create_test_user(username_prefix="reviewer1")
        self.user2 = create_test_user(username_prefix="reviewer2")
        self.admin_user = create_test_user(username_prefix="admin")

        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org-conflict"
        )

        # Create memberships
        OrganisationMembership.objects.create(
            user=self.user1,
            organisation=self.org,
            role="RESEARCH_FELLOW",
            is_active=True,
        )
        OrganisationMembership.objects.create(
            user=self.user2,
            organisation=self.org,
            role="RESEARCH_FELLOW",
            is_active=True,
        )
        OrganisationMembership.objects.create(
            user=self.admin_user,
            organisation=self.org,
            role="SENIOR_RESEARCHER",
            is_active=True,
        )

        # Create search session
        self.session = SearchSession.objects.create(
            owner=self.user1,
            organisation=self.org,
            title="Test Session",
            status="under_review",
        )

        # Create review configuration
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            version=1,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
            conflict_resolution_method="CONSENSUS",
            consensus_criteria="MAJORITY",
            created_by=self.user1,
            organisation=self.org,
        )
        self.session.current_configuration = self.config
        self.session.save(update_fields=["current_configuration"])

        # Create processed result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            snippet="Test snippet",
            url="https://example.com/test",
            processing_status="success",
        )

        # Create reviewer decisions (conflicting)
        self.decision1 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.user1,
            decision="INCLUDE",
            confidence_level=3,
            notes="Should include",
        )
        self.decision2 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.user2,
            decision="EXCLUDE",
            exclusion_reason="not_relevant",
            confidence_level=3,
            notes="Should exclude",
        )

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            resolution_method="CONSENSUS",
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

        self.client = Client()

    def test_list_conflicts(self):
        """Test GET /api/conflicts/?session_id={uuid}"""
        self.client.login(username=self.user1.username, password="testpass123")

        url = reverse("review_results:conflict_list")
        response = self.client.get(url, {"session_id": str(self.session.id)})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["conflicts"]), 1)
        self.assertEqual(data["conflicts"][0]["conflict_type"], "INCLUDE_EXCLUDE")
        self.assertEqual(data["conflicts"][0]["status"], "PENDING")

    def test_list_conflicts_requires_session_id(self):
        """Test that session_id parameter is required"""
        self.client.login(username=self.user1.username, password="testpass123")

        url = reverse("review_results:conflict_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("session_id is required", data["error"])

    def test_list_conflicts_permission_denied(self):
        """Test that users from different org cannot list conflicts"""
        other_user = create_test_user(username_prefix="other")
        self.client.login(username=other_user.username, password="testpass123")

        url = reverse("review_results:conflict_list")
        response = self.client.get(url, {"session_id": str(self.session.id)})

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Permission denied", data["error"])

    def test_conflict_detail(self):
        """Test GET /api/conflicts/{id}/"""
        self.client.login(username=self.user1.username, password="testpass123")

        url = reverse(
            "review_results:conflict_detail", kwargs={"conflict_id": self.conflict.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["conflict"]["status"], "PENDING")
        self.assertEqual(len(data["conflict"]["conflicting_decisions"]), 2)
        self.assertEqual(data["conflict"]["resolution_method"], "CONSENSUS")

    def test_conflict_detail_includes_comments(self):
        """Test that conflict detail includes comments"""
        # Create a comment
        _comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user1,
            content="Test comment",
            content_html="<p>Test comment</p>",
        )

        self.client.login(username=self.user1.username, password="testpass123")

        url = reverse(
            "review_results:conflict_detail", kwargs={"conflict_id": self.conflict.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["conflict"]["comments"]), 1)
        self.assertEqual(data["conflict"]["comments"][0]["content"], "Test comment")

    def test_add_comment(self):
        """Test POST /api/conflicts/{id}/discuss/"""
        self.client.login(username=self.user1.username, password="testpass123")

        url = reverse(
            "review_results:conflict_discuss", kwargs={"conflict_id": self.conflict.id}
        )
        payload = {"content": "This is a test comment with **markdown**"}
        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("comment", data)
        self.assertEqual(data["comment"]["content"], payload["content"])
        self.assertIn("markdown", data["comment"]["content_html"])

        # Verify comment was created
        self.assertEqual(
            ConflictComment.objects.filter(conflict=self.conflict).count(), 1
        )

    def test_add_comment_requires_content(self):
        """Test that content is required for comments"""
        self.client.login(username=self.user1.username, password="testpass123")

        url = reverse(
            "review_results:conflict_discuss", kwargs={"conflict_id": self.conflict.id}
        )
        payload = {}
        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("content is required", data["error"])

    def test_add_threaded_comment(self):
        """Test adding a reply to an existing comment"""
        # Create parent comment
        parent = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.user1,
            content="Parent comment",
            content_html="<p>Parent comment</p>",
        )

        self.client.login(username=self.user2.username, password="testpass123")

        url = reverse(
            "review_results:conflict_discuss", kwargs={"conflict_id": self.conflict.id}
        )
        payload = {"content": "Reply to parent", "parent_id": str(parent.id)}
        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["comment"]["parent_id"], str(parent.id))

        # Verify threaded comment was created
        reply = ConflictComment.objects.get(id=data["comment"]["id"])
        self.assertEqual(reply.parent, parent)

    def test_resolve_conflict(self):
        """Test POST /api/conflicts/{id}/resolve/"""
        self.client.login(username=self.user1.username, password="testpass123")

        url = reverse(
            "review_results:conflict_resolve", kwargs={"conflict_id": self.conflict.id}
        )
        payload = {"resolution_notes": "Consensus reached after discussion"}
        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["conflict"]["status"], "RESOLVED")
        self.assertIsNotNone(data["conflict"]["resolved_at"])

        # Verify conflict was resolved
        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "RESOLVED")
        self.assertIsNotNone(self.conflict.resolved_at)
        self.assertEqual(self.conflict.resolved_by, self.user1)

    def test_resolve_conflict_only_for_consensus_method(self):
        """Test that only CONSENSUS conflicts can be resolved via discussion"""
        # Change resolution method
        self.conflict.resolution_method = "LEAD_ARBITRATION"
        self.conflict.save()

        self.client.login(username=self.user1.username, password="testpass123")

        url = reverse(
            "review_results:conflict_resolve", kwargs={"conflict_id": self.conflict.id}
        )
        response = self.client.post(
            url, data=json.dumps({}), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Cannot resolve via discussion", data["error"])

    def test_cannot_resolve_already_resolved_conflict(self):
        """Test that already resolved conflicts cannot be resolved again"""
        self.conflict.status = "RESOLVED"
        self.conflict.save()

        self.client.login(username=self.user1.username, password="testpass123")

        url = reverse(
            "review_results:conflict_resolve", kwargs={"conflict_id": self.conflict.id}
        )
        response = self.client.post(
            url, data=json.dumps({}), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Conflict already resolved", data["error"])
