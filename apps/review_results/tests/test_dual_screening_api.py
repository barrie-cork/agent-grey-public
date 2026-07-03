"""
Tests for dual screening API endpoints (Phase D).

This module tests the multi-reviewer workflow API endpoints including:
- ClaimNextResultAPIView
- SubmitDecisionAPIView
- SkipResultAPIView
- ReviewProgressAPIView
"""

import json
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.utils import DisablePersonalOrgSignalMixin, create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import (
    ConflictResolution,
    ReviewerAssignment,
    ReviewerDecision,
    ResultSkip,
)

User = get_user_model()


class ClaimNextResultAPITestCase(DisablePersonalOrgSignalMixin, TestCase):
    """Test the ClaimNextResultAPIView endpoint."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-claim"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.organisation, role="REVIEWER"
        )

        self.reviewer2 = create_test_user(username_prefix="reviewer2")
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.organisation, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
            organisation=self.organisation,
            status="under_review",
        )

        # Create results
        self.result1 = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result 1",
            url="https://example.com/test1",
            processing_status="success",
            min_reviewers_required=2,
            reviewers_completed=0,
        )

        self.result2 = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result 2",
            url="https://example.com/test2",
            processing_status="success",
            min_reviewers_required=2,
            reviewers_completed=0,
        )

    def test_claim_next_result_success(self):
        """Test successfully claiming next available result."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results:claim_next_result")

        response = self.client.post(
            url,
            data=json.dumps({"session_id": str(self.session.id)}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify response structure
        self.assertTrue(data["success"])
        self.assertIn("result", data)
        self.assertIn("assignment_role", data)
        self.assertEqual(data["assignment_role"], "PRIMARY")

        # Verify assignment was created
        assignment = ReviewerAssignment.objects.filter(
            reviewer=self.reviewer1, result__session=self.session, is_active=True
        ).first()
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.role, "PRIMARY")

    def test_claim_next_result_no_organisation(self):
        """Test claiming fails if user has no organisation."""
        no_org_user = create_test_user(username_prefix="no_org")
        self.client.force_login(no_org_user)
        url = reverse("review_results:claim_next_result")

        response = self.client.post(
            url, data=json.dumps({}), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["code"], "NO_ORGANISATION")

    def test_claim_next_result_no_results_available(self):
        """Test claiming when no results are available."""
        # Reviewer 1 claims both results
        self.client.force_login(self.reviewer1)
        url = reverse("review_results:claim_next_result")

        # Claim first result
        self.client.post(
            url,
            data=json.dumps({"session_id": str(self.session.id)}),
            content_type="application/json",
        )

        # Claim second result
        self.client.post(
            url,
            data=json.dumps({"session_id": str(self.session.id)}),
            content_type="application/json",
        )

        # Try to claim third result (none available)
        response = self.client.post(
            url,
            data=json.dumps({"session_id": str(self.session.id)}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["code"], "NO_RESULTS_AVAILABLE")

    def test_claim_next_result_secondary_reviewer(self):
        """Test that second reviewer gets SECONDARY role."""
        # Reviewer 1 claims first
        self.client.force_login(self.reviewer1)
        url = reverse("review_results:claim_next_result")

        response1 = self.client.post(
            url,
            data=json.dumps({"session_id": str(self.session.id)}),
            content_type="application/json",
        )
        result_id = response1.json()["result"]["id"]

        # Reviewer 2 claims same result
        self.client.force_login(self.reviewer2)
        response2 = self.client.post(
            url,
            data=json.dumps({"session_id": str(self.session.id)}),
            content_type="application/json",
        )

        self.assertEqual(response2.status_code, 200)
        data = response2.json()
        self.assertEqual(data["result"]["id"], result_id)
        self.assertEqual(data["assignment_role"], "SECONDARY")


class SubmitDecisionAPITestCase(DisablePersonalOrgSignalMixin, TestCase):
    """Test the SubmitDecisionAPIView endpoint."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-submit"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.organisation, role="REVIEWER"
        )

        self.reviewer2 = create_test_user(username_prefix="reviewer2")
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.organisation, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
            organisation=self.organisation,
            status="under_review",
        )

        # Create result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            processing_status="success",
            min_reviewers_required=2,
            reviewers_completed=0,
        )

        # Create assignments
        self.assignment1 = ReviewerAssignment.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=self.reviewer1,
            role="PRIMARY",
            is_active=True,
        )

        self.assignment2 = ReviewerAssignment.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=self.reviewer2,
            role="SECONDARY",
            is_active=True,
        )

    def test_submit_decision_include_success(self):
        """Test successfully submitting INCLUDE decision."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results:submit_decision")

        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "result_id": str(self.result.id),
                    "decision": "INCLUDE",
                    "confidence_level": 3,
                    "notes": "Relevant grey literature",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify response structure
        self.assertTrue(data["success"])
        self.assertIn("decision", data)
        self.assertEqual(data["decision"]["decision"], "INCLUDE")
        self.assertFalse(data["conflict_detected"])
        self.assertEqual(data["reviewers_completed"], 1)
        self.assertEqual(data["min_reviewers_required"], 2)

        # Verify decision was created
        decision = ReviewerDecision.objects.filter(
            reviewer=self.reviewer1, result=self.result
        ).first()
        self.assertIsNotNone(decision)
        self.assertEqual(decision.decision, "INCLUDE")
        self.assertEqual(decision.confidence_level, 3)

    def test_submit_decision_exclude_requires_reason(self):
        """Test that EXCLUDE decision requires exclusion_reason."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results:submit_decision")

        response = self.client.post(
            url,
            data=json.dumps({"result_id": str(self.result.id), "decision": "EXCLUDE"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("exclusion_reason", data["error"])

    def test_submit_decision_conflict_detection(self):
        """Test automatic conflict detection when reviewers disagree."""
        # Reviewer 1 submits INCLUDE
        self.client.force_login(self.reviewer1)
        url = reverse("review_results:submit_decision")

        self.client.post(
            url,
            data=json.dumps(
                {
                    "result_id": str(self.result.id),
                    "decision": "INCLUDE",
                    "confidence_level": 2,
                }
            ),
            content_type="application/json",
        )

        # Reviewer 2 submits EXCLUDE
        self.client.force_login(self.reviewer2)

        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "result_id": str(self.result.id),
                    "decision": "EXCLUDE",
                    "exclusion_reason": "not_relevant",
                    "confidence_level": 3,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify conflict was detected
        self.assertTrue(data["conflict_detected"])
        self.assertFalse(data["consensus_reached"])

        # Verify conflict record was created
        conflict = ConflictResolution.objects.filter(
            result=self.result, status="PENDING"
        ).first()
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict.conflict_type, "INCLUDE_EXCLUDE")

    def test_submit_decision_consensus(self):
        """Test consensus reached when reviewers agree."""
        # Reviewer 1 submits INCLUDE
        self.client.force_login(self.reviewer1)
        url = reverse("review_results:submit_decision")

        self.client.post(
            url,
            data=json.dumps({"result_id": str(self.result.id), "decision": "INCLUDE"}),
            content_type="application/json",
        )

        # Reviewer 2 also submits INCLUDE
        self.client.force_login(self.reviewer2)

        response = self.client.post(
            url,
            data=json.dumps({"result_id": str(self.result.id), "decision": "INCLUDE"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify consensus was reached
        self.assertFalse(data["conflict_detected"])
        self.assertTrue(data["consensus_reached"])

    def test_submit_decision_invalid_decision_value(self):
        """Test that invalid decision values are rejected."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results:submit_decision")

        response = self.client.post(
            url,
            data=json.dumps({"result_id": str(self.result.id), "decision": "INVALID"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])

    def test_submit_decision_duplicate_prevents_resubmission(self):
        """Test that reviewers cannot submit multiple decisions for same result."""
        self.client.force_login(self.reviewer1)
        url = reverse("review_results:submit_decision")

        # Submit first decision
        self.client.post(
            url,
            data=json.dumps({"result_id": str(self.result.id), "decision": "INCLUDE"}),
            content_type="application/json",
        )

        # Try to submit second decision
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "result_id": str(self.result.id),
                    "decision": "EXCLUDE",
                    "exclusion_reason": "not_relevant",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("already submitted", data["error"])


class SkipResultAPITestCase(DisablePersonalOrgSignalMixin, TestCase):
    """Test the SkipResultAPIView endpoint."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-skip"
        )

        # Create user
        self.reviewer = create_test_user(username_prefix="reviewer1")
        OrganisationMembership.objects.create(
            user=self.reviewer, organisation=self.organisation, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer,
            organisation=self.organisation,
            status="under_review",
        )

        # Create results
        self.result1 = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result 1",
            url="https://example.com/test1",
            processing_status="success",
            min_reviewers_required=2,
            reviewers_completed=0,
        )

        self.result2 = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result 2",
            url="https://example.com/test2",
            processing_status="success",
            min_reviewers_required=2,
            reviewers_completed=0,
        )

        # Create assignment for result1
        self.assignment = ReviewerAssignment.objects.create(
            organisation=self.organisation,
            result=self.result1,
            reviewer=self.reviewer,
            role="PRIMARY",
            is_active=True,
        )

    def test_skip_result_success(self):
        """Test successfully skipping a result."""
        self.client.force_login(self.reviewer)
        url = reverse("review_results:skip_result")

        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "result_id": str(self.result1.id),
                    "skip_reason": "Insufficient information",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify response structure
        self.assertTrue(data["success"])
        self.assertIn("next_result", data)

        # Verify skip record was created
        skip = ResultSkip.objects.filter(
            reviewer=self.reviewer, result=self.result1
        ).first()
        self.assertIsNotNone(skip)
        self.assertEqual(skip.reason, "Insufficient information")

        # Verify assignment was deactivated
        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.is_active)

    def test_skip_result_claims_next(self):
        """Test that skipping automatically claims next result."""
        self.client.force_login(self.reviewer)
        url = reverse("review_results:skip_result")

        response = self.client.post(
            url,
            data=json.dumps(
                {"result_id": str(self.result1.id), "skip_reason": "Skipping to next"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify next result was claimed
        self.assertIsNotNone(data["next_result"])
        self.assertEqual(data["next_result"]["id"], str(self.result2.id))

        # Verify new assignment was created for result2
        new_assignment = ReviewerAssignment.objects.filter(
            reviewer=self.reviewer, result=self.result2, is_active=True
        ).first()
        self.assertIsNotNone(new_assignment)


class ReviewProgressAPITestCase(DisablePersonalOrgSignalMixin, TestCase):
    """Test the ReviewProgressAPIView endpoint."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-progress"
        )

        # Create users
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.organisation, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.reviewer1,
            organisation=self.organisation,
            status="under_review",
        )

        # Create results
        self.result1 = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result 1",
            url="https://example.com/test1",
            processing_status="success",
            min_reviewers_required=2,
            reviewers_completed=0,
        )

        self.result2 = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result 2",
            url="https://example.com/test2",
            processing_status="success",
            min_reviewers_required=2,
            reviewers_completed=2,  # Fully reviewed
        )

    def test_review_progress_success(self):
        """Test successfully getting review progress."""
        self.client.force_login(self.reviewer1)
        url = reverse(
            "review_results:review_progress",
            kwargs={"session_id": str(self.session.id)},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Verify response structure
        self.assertTrue(data["success"])
        self.assertIn("progress", data)

        progress = data["progress"]
        self.assertEqual(progress["total_results"], 2)
        self.assertEqual(progress["pending"], 1)  # result1 not fully reviewed
        self.assertIn("completion_percentage", progress)

    def test_review_progress_permission_denied(self):
        """Test that non-members cannot access progress."""
        other_user = create_test_user(username_prefix="other")
        self.client.force_login(other_user)
        url = reverse(
            "review_results:review_progress",
            kwargs={"session_id": str(self.session.id)},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data["success"])

    def test_review_progress_session_not_found(self):
        """Test progress for non-existent session."""
        self.client.force_login(self.reviewer1)
        url = reverse(
            "review_results:review_progress",
            kwargs={"session_id": "00000000-0000-0000-0000-000000000000"},
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["success"])
