"""
Tests for Per-Reviewer Breakdown API endpoint.

Focus areas:
- Session owner permission check (only owners can request breakdown)
- Query parameter handling (?include_breakdown=true)
- Response structure validation
- Regular reviewers cannot access breakdown
- Backward compatibility (without query param)
"""

from django.test import TestCase
from django.utils import timezone
from rest_framework import status

from apps.core.tests.utils import (
    DisablePersonalOrgSignalMixin,
    create_test_user,
    make_session_participant,
)
from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import SearchSession
from apps.review_results.models import InterRaterReliability


class PerReviewerBreakdownAPITest(DisablePersonalOrgSignalMixin, TestCase):
    """Test API endpoint for per-reviewer breakdown functionality."""

    def setUp(self):
        """Set up test data with organisation, session, and users."""
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-breakdown"
        )

        # Session owner
        self.owner = create_test_user(username_prefix="owner")
        OrganisationMembership.objects.create(
            user=self.owner,
            organisation=self.organisation,
            role="LEAD_REVIEWER",
            is_active=True,
        )

        # Regular reviewer
        self.reviewer_a = create_test_user(username_prefix="reviewer_a")
        OrganisationMembership.objects.create(
            user=self.reviewer_a,
            organisation=self.organisation,
            role="REVIEWER",
            is_active=True,
        )

        self.reviewer_b = create_test_user(username_prefix="reviewer_b")
        OrganisationMembership.objects.create(
            user=self.reviewer_b,
            organisation=self.organisation,
            role="REVIEWER",
            is_active=True,
        )

        # Create session
        self.session = SearchSession.objects.create(
            organisation=self.organisation, owner=self.owner, title="Test Session"
        )
        # reviewers gain session access as accepted participants
        # (org membership alone no longer grants access -- GH #230).
        make_session_participant(self.session, self.reviewer_a)
        make_session_participant(self.session, self.reviewer_b)

        # Create IRR data
        now = timezone.now()
        InterRaterReliability.objects.create(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
            cohens_kappa=0.85,
            percentage_agreement=90.0,
            total_comparisons=200,
            agreements=180,
            disagreements=20,
            screening_stage="SCREENING",
            calculation_window_start=now,
            calculation_window_end=now,
        )

        self.url = f"/api/sessions/{self.session.id}/irr-metrics/"

    def test_session_owner_can_request_breakdown(self):
        """Test session owner can successfully request per-reviewer breakdown."""
        self.client.force_login(self.owner)

        response = self.client.get(self.url, {"include_breakdown": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("per_reviewer_breakdown", data)
        self.assertIsInstance(data["per_reviewer_breakdown"], list)
        self.assertGreater(len(data["per_reviewer_breakdown"]), 0)

    def test_regular_reviewer_cannot_request_breakdown(self):
        """Test regular reviewer gets 403 when requesting breakdown."""
        self.client.force_login(self.reviewer_a)

        response = self.client.get(self.url, {"include_breakdown": "true"})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        data = response.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "per_reviewer_breakdown_forbidden")

    def test_without_breakdown_param_returns_summary_only(self):
        """Test endpoint returns summary only when breakdown not requested."""
        self.client.force_login(self.owner)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("session_wide_metrics", data)
        self.assertNotIn("per_reviewer_breakdown", data)

    def test_breakdown_param_false_returns_summary_only(self):
        """Test include_breakdown=false returns summary only."""
        self.client.force_login(self.owner)

        response = self.client.get(self.url, {"include_breakdown": "false"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertNotIn("per_reviewer_breakdown", data)

    def test_response_includes_is_session_owner_flag(self):
        """Test response includes is_session_owner flag."""
        self.client.force_login(self.owner)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("is_session_owner", data)
        self.assertTrue(data["is_session_owner"])

    def test_regular_reviewer_sees_is_session_owner_false(self):
        """Test regular reviewer sees is_session_owner=false."""
        self.client.force_login(self.reviewer_a)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("is_session_owner", data)
        self.assertFalse(data["is_session_owner"])

    def test_breakdown_structure_is_correct(self):
        """Test per-reviewer breakdown has correct structure."""
        self.client.force_login(self.owner)

        response = self.client.get(self.url, {"include_breakdown": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        breakdown = data["per_reviewer_breakdown"]
        self.assertIsInstance(breakdown, list)

        # Check first reviewer has correct fields
        if len(breakdown) > 0:
            reviewer = breakdown[0]
            self.assertIn("reviewer_id", reviewer)
            self.assertIn("reviewer_name", reviewer)
            self.assertIn("reviewer_email", reviewer)
            self.assertIn("average_kappa", reviewer)
            self.assertIn("average_agreement", reviewer)
            self.assertIn("pairwise_comparisons", reviewer)
            self.assertIn("total_comparisons", reviewer)
            self.assertIn("meets_cochrane_average", reviewer)

            # Check pairwise comparison structure
            if len(reviewer["pairwise_comparisons"]) > 0:
                pairwise = reviewer["pairwise_comparisons"][0]
                self.assertIn("with_reviewer_id", pairwise)
                self.assertIn("with_reviewer_name", pairwise)
                self.assertIn("cohens_kappa", pairwise)
                self.assertIn("percentage_agreement", pairwise)
                self.assertIn("agreements", pairwise)
                self.assertIn("disagreements", pairwise)
                self.assertIn("total_comparisons", pairwise)
                self.assertIn("meets_threshold", pairwise)

    def test_unauthenticated_request_returns_error(self):
        """Test unauthenticated requests are rejected."""
        response = self.client.get(self.url)

        # Django test client returns 302 (redirect to login) for unauthenticated
        self.assertIn(
            response.status_code,
            [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN],
        )

    def test_session_from_different_organisation_returns_404(self):
        """Test session from different organisation returns 404."""
        # Create different organisation and user
        other_org = Organisation.objects.create(
            name="Other Organisation", slug="other-org-breakdown"
        )
        other_user = create_test_user(username_prefix="other_user")
        OrganisationMembership.objects.create(
            user=other_user,
            organisation=other_org,
            role="LEAD_REVIEWER",
            is_active=True,
        )

        self.client.force_login(other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_backward_compatibility_with_old_response_format(self):
        """Test endpoint is backward compatible (can handle old widget code)."""
        self.client.force_login(self.reviewer_a)

        # Old widgets don't send include_breakdown parameter
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Should have new structure
        self.assertIn("session_wide_metrics", data)

        # Session-wide metrics should have all expected fields
        metrics = data["session_wide_metrics"]
        self.assertIn("average_kappa", metrics)
        self.assertIn("average_agreement", metrics)
        self.assertIn("total_pairs", metrics)
        self.assertIn("meets_cochrane", metrics)
