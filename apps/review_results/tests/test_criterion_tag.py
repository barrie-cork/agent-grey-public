"""
Tests for criterion_tag on ConflictComment.

Verifies:
- POST comment with valid criterion_tag
- POST comment without tag (blank OK)
- POST comment with invalid tag (400)
- criterion_tag + criterion_tag_display in serializer output
- Tag on reply comments
"""

import json

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.utils import create_test_user, make_session_participant
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.models import (
    ConflictComment,
    ConflictResolution,
    ReviewerDecision,
)


class CriterionTagTestCase(TestCase):
    """Tests for comment criterion_tag field."""

    def setUp(self):
        """Set up test data with a conflict and two reviewers."""
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        self.org = Organisation.objects.create(
            name="Test Org", slug="test-org-criterion"
        )
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.org, role="REVIEWER", is_active=True
        )
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.org, role="REVIEWER", is_active=True
        )

        self.session = SearchSession.objects.create(
            owner=self.reviewer1,
            organisation=self.org,
            title="Test Session",
            status="under_review",
        )
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            version=1,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
            conflict_resolution_method="CONSENSUS",
            consensus_criteria="MAJORITY",
            created_by=self.reviewer1,
            organisation=self.org,
        )
        self.session.current_configuration = self.config
        self.session.save(update_fields=["current_configuration"])
        # reviewer1 owns the session; reviewer2 gains access as an accepted
        # reviewer (org membership alone no longer grants access -- GH #230).
        make_session_participant(self.session, self.reviewer2)

        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            snippet="Test snippet",
            url="https://example.com/test",
            processing_status="success",
        )

        self.decision1 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            confidence_level=3,
        )
        self.decision2 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            exclusion_reason="not_relevant",
            confidence_level=3,
        )

        self.conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            resolution_method="CONSENSUS",
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

        self.url = reverse(
            "review_results_api:create-comment",
            kwargs={"conflict_id": self.conflict.id},
        )

    def _login_as(self, user):
        self.client.login(username=user.username, password="testpass123")

    def test_post_comment_with_criterion_tag(self):
        """POST with valid criterion_tag sets the field and returns display."""
        self._login_as(self.reviewer1)
        response = self.client.post(
            self.url,
            data=json.dumps(
                {"content": "Population mismatch here", "criterion_tag": "population"}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["criterion_tag"], "population")
        self.assertEqual(data["criterion_tag_display"], "Population match")

        # Verify DB
        comment = ConflictComment.objects.get(id=data["id"])
        self.assertEqual(comment.criterion_tag, "population")

    def test_post_comment_without_criterion_tag(self):
        """POST without criterion_tag succeeds (blank is OK)."""
        self._login_as(self.reviewer1)
        response = self.client.post(
            self.url,
            data=json.dumps({"content": "General observation"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["criterion_tag"], "")
        self.assertEqual(data["criterion_tag_display"], "")

    def test_post_comment_with_blank_criterion_tag(self):
        """POST with empty string criterion_tag succeeds."""
        self._login_as(self.reviewer1)
        response = self.client.post(
            self.url,
            data=json.dumps({"content": "Another comment", "criterion_tag": ""}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["criterion_tag"], "")

    def test_post_comment_with_invalid_criterion_tag(self):
        """POST with invalid criterion_tag returns 400."""
        self._login_as(self.reviewer1)
        response = self.client.post(
            self.url,
            data=json.dumps({"content": "Bad tag", "criterion_tag": "nonexistent_tag"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_criterion_tag_on_reply(self):
        """Replies can also have criterion tags."""
        self._login_as(self.reviewer1)
        # Create parent comment
        parent_response = self.client.post(
            self.url,
            data=json.dumps({"content": "Parent comment"}),
            content_type="application/json",
        )
        parent_id = parent_response.json()["id"]

        # Reply with criterion tag
        self._login_as(self.reviewer2)
        response = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "content": "Replying about context",
                    "parent_id": parent_id,
                    "criterion_tag": "context",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["criterion_tag"], "context")
        self.assertEqual(data["criterion_tag_display"], "Context appropriateness")

    def test_criterion_tag_in_detail_endpoint(self):
        """Criterion tag fields appear in conflict detail serializer."""
        # Create a comment with a tag
        ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.reviewer1,
            content="Tagged comment",
            criterion_tag="relevance",
        )

        self._login_as(self.reviewer1)
        detail_url = reverse(
            "review_results_api:conflict-details",
            kwargs={"conflict_id": self.conflict.id},
        )
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        comments = data["comments"]
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["criterion_tag"], "relevance")
        self.assertEqual(
            comments[0]["criterion_tag_display"], "Relevance to research question"
        )

    def test_auto_transition_pending_to_in_discussion(self):
        """Posting a comment transitions PENDING conflict to IN_DISCUSSION."""
        self._login_as(self.reviewer1)
        self.assertEqual(self.conflict.status, "PENDING")

        self.client.post(
            self.url,
            data=json.dumps(
                {"content": "Starting discussion", "criterion_tag": "population"}
            ),
            content_type="application/json",
        )

        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "IN_DISCUSSION")
