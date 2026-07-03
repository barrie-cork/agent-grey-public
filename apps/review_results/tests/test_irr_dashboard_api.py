"""
Tests for IRR dashboard endpoint per-reviewer breakdown.

Tests the ?include_breakdown=true parameter on the session IRR metrics endpoint,
including ownership permission enforcement and response structure.
"""

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.utils import (
    DisablePersonalOrgSignalMixin,
    create_test_user,
    make_session_participant,
)
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import (
    ReviewerAssignment,
    ReviewerDecision,
)


class IRRDashboardEndpointTest(DisablePersonalOrgSignalMixin, TestCase):
    """Integration tests for GET /api/sessions/{id}/irr-metrics/?include_breakdown=true."""

    def setUp(self):
        """Set up test data with org, owner, reviewers, session, and IRR records."""
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-irr"
        )

        self.owner = create_test_user(username_prefix="owner")
        OrganisationMembership.objects.create(
            user=self.owner, organisation=self.organisation, role="LEAD_REVIEWER"
        )

        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.organisation, role="REVIEWER"
        )

        self.reviewer2 = create_test_user(username_prefix="reviewer2")
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.organisation, role="REVIEWER"
        )

        self.session = SearchSession.objects.create(
            title="IRR Test Session",
            owner=self.owner,
            organisation=self.organisation,
            status="under_review",
        )
        # reviewers gain session access as accepted participants
        # (org membership alone no longer grants access -- GH #230).
        make_session_participant(self.session, self.reviewer1)
        make_session_participant(self.session, self.reviewer2)

        # Create decisions and IRR record
        for i in range(3):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i}",
                url=f"https://example.com/{i}",
                snippet="Test",
            )
            a1 = ReviewerAssignment.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=self.reviewer1,
                role="PRIMARY",
                is_active=True,
            )
            a2 = ReviewerAssignment.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=self.reviewer2,
                role="SECONDARY",
                is_active=True,
            )
            ReviewerDecision.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=self.reviewer1,
                assignment=a1,
                decision="INCLUDE",
                screening_stage="SCREENING",
                is_revote=False,
            )
            ReviewerDecision.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=self.reviewer2,
                assignment=a2,
                decision="INCLUDE",
                screening_stage="SCREENING",
                is_revote=False,
            )

        # Create an IRR record
        from apps.review_results.services.irr_service import (
            InterRaterReliabilityService,
        )

        service = InterRaterReliabilityService()
        service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
        )

        self.url = reverse(
            "review_results_api:session-irr-metrics", args=[self.session.id]
        )

    def test_include_breakdown_as_owner_returns_breakdown(self):
        """Owner requesting include_breakdown=true gets per_reviewer_breakdown."""
        self.client.force_login(self.owner)
        response = self.client.get(self.url, {"include_breakdown": "true"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("per_reviewer_breakdown", data)
        breakdown = data["per_reviewer_breakdown"]
        self.assertIsInstance(breakdown, list)
        self.assertGreater(len(breakdown), 0)

        # Verify structure
        entry = breakdown[0]
        self.assertIn("reviewer_id", entry)
        self.assertIn("average_kappa", entry)
        self.assertIn("pairwise_comparisons", entry)

    def test_include_breakdown_as_non_owner_returns_403(self):
        """Non-owner requesting include_breakdown=true gets 403."""
        self.client.force_login(self.reviewer1)
        response = self.client.get(self.url, {"include_breakdown": "true"})

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertEqual(data["error"], "per_reviewer_breakdown_forbidden")

    def test_without_include_breakdown_no_breakdown_key(self):
        """Request without include_breakdown omits breakdown from response."""
        self.client.force_login(self.owner)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("per_reviewer_breakdown", data)
