"""
Tests for Cohen's Kappa Widget API Endpoint

Tests Phase C deliverables:
- IRR endpoint permission changed to IsAuthenticated
- API returns session-wide summary (not individual pairs)
- All authenticated users can access the endpoint
"""

from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.core.tests.utils import (
    DisablePersonalOrgSignalMixin,
    create_test_user,
    make_session_participant,
)
from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import (
    ReviewConfiguration,
    ReviewInvitation,
    SearchSession,
)
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import (
    ReviewerDecision,
    InterRaterReliability,
    ReviewerAssignment,
)


class KappaWidgetAPITestCase(DisablePersonalOrgSignalMixin, TestCase):
    """Test suite for Cohen's Kappa widget API endpoint."""

    def setUp(self):
        """Set up test fixtures."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-kappa"
        )

        # Create session owner (lead reviewer)
        self.owner = create_test_user(username_prefix="session_owner")
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.owner,
            role="LEAD_REVIEWER",
            is_active=True,
        )

        # Create regular reviewers
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.reviewer1,
            role="REVIEWER",
            is_active=True,
        )

        self.reviewer2 = create_test_user(username_prefix="reviewer2")
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.reviewer2,
            role="REVIEWER",
            is_active=True,
        )

        # Create Workflow #2 session (dual-screening)
        self.session = SearchSession.objects.create(
            title="Test Dual Screening Session",
            organisation=self.organisation,
            owner=self.owner,
            status="under_review",
        )

        # Create Workflow #2 configuration
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            conflict_resolution_method="CONSENSUS",
            blind_screening_enforced=True,
            irr_threshold=0.70,
            created_by=self.owner,
        )
        self.session.current_configuration = self.config
        self.session.save()

        # reviewers gain session access as accepted participants
        # (org membership alone no longer grants access -- GH #230).
        make_session_participant(self.session, self.reviewer1)
        make_session_participant(self.session, self.reviewer2)

        # Create test results
        self.result1 = ProcessedResult.objects.create(
            session=self.session, title="Test Result 1", url="https://example.com/1"
        )

        self.result2 = ProcessedResult.objects.create(
            session=self.session, title="Test Result 2", url="https://example.com/2"
        )

        # Create reviewer assignments
        ReviewerAssignment.objects.create(
            result=self.result1,
            reviewer=self.reviewer1,
            role="PRIMARY",
            organisation=self.organisation,
        )
        ReviewerAssignment.objects.create(
            result=self.result1,
            reviewer=self.reviewer2,
            role="SECONDARY",
            organisation=self.organisation,
        )

        # Create decisions (agreement case)
        ReviewerDecision.objects.create(
            result=self.result1,
            reviewer=self.reviewer1,
            organisation=self.organisation,
            decision="INCLUDE",
            notes="Test decision 1",
        )
        ReviewerDecision.objects.create(
            result=self.result1,
            reviewer=self.reviewer2,
            organisation=self.organisation,
            decision="INCLUDE",
            notes="Test decision 2",
        )

        # Create decisions (disagreement case)
        ReviewerDecision.objects.create(
            result=self.result2,
            reviewer=self.reviewer1,
            organisation=self.organisation,
            decision="INCLUDE",
            notes="Test decision 3",
        )
        ReviewerDecision.objects.create(
            result=self.result2,
            reviewer=self.reviewer2,
            organisation=self.organisation,
            decision="EXCLUDE",
            notes="Test decision 4",
        )

        # Create IRR record
        self.irr = InterRaterReliability.objects.create(
            search_session=self.session,
            organisation=self.organisation,
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            cohens_kappa=0.75,
            percentage_agreement=87.5,
            total_comparisons=2,
            agreements=1,
            disagreements=1,
            screening_stage="SCREENING",
            calculation_window_start=timezone.now() - timedelta(hours=1),
            calculation_window_end=timezone.now(),
        )

        # Endpoint URL
        self.url = reverse(
            "review_results_api:session-irr-metrics",
            kwargs={"session_id": self.session.id},
        )

    def test_endpoint_requires_authentication(self):
        """Test that endpoint requires authentication (IsAuthenticated permission)."""
        # Unauthenticated request should redirect to login or return 403
        response = self.client.get(self.url)
        self.assertIn(
            response.status_code, [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN]
        )

    def test_session_owner_can_access_endpoint(self):
        """Test that session owner (lead reviewer) can access endpoint."""
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_regular_reviewer_can_access_endpoint(self):
        """
        Test that regular reviewers can access endpoint.

        This is the key change from Phase C - permission changed from
        IsLeadReviewerOrAdmin to IsAuthenticated for transparency.
        """
        self.client.force_login(self.reviewer1)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Second reviewer should also have access
        self.client.force_login(self.reviewer2)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_endpoint_returns_session_wide_summary(self):
        """
        Test that endpoint returns session-wide summary format.

        Phase C change: Response should use get_irr_summary() instead of
        returning serialized IRR records.
        """
        self.client.force_login(self.reviewer1)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Verify top-level wrapper keys
        self.assertIn("session_wide_metrics", data)
        self.assertIn("is_session_owner", data)

        metrics = data["session_wide_metrics"]

        # Verify summary format (should have these keys)
        expected_keys = [
            "average_kappa",
            "average_agreement",
            "total_pairs",
            "pairs_below_threshold",
            "meets_cochrane",
            "calculated_at",
        ]

        for key in expected_keys:
            self.assertIn(key, metrics, f"Response missing expected key: {key}")

        # Verify data types
        self.assertIsInstance(metrics["average_kappa"], (int, float))
        self.assertIsInstance(metrics["average_agreement"], (int, float))
        self.assertIsInstance(metrics["total_pairs"], int)
        self.assertIsInstance(metrics["pairs_below_threshold"], int)
        self.assertIsInstance(metrics["meets_cochrane"], bool)

        # Verify values match our test data
        self.assertEqual(metrics["total_pairs"], 1)
        self.assertAlmostEqual(metrics["average_kappa"], 0.75, places=2)
        self.assertAlmostEqual(metrics["average_agreement"], 87.5, places=1)
        self.assertTrue(metrics["meets_cochrane"])  # 0.75 >= 0.70 threshold
        self.assertEqual(metrics["pairs_below_threshold"], 0)

    def test_endpoint_response_not_serialized_records(self):
        """
        Test that endpoint does NOT return serialized IRR records.

        Previously returned: [{reviewer_a: {...}, reviewer_b: {...}, cohens_kappa: ...}]
        Now returns: {average_kappa: 0.75, total_pairs: 1, ...}
        """
        self.client.force_login(self.reviewer1)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Should NOT be a list (old format was list of IRR records)
        self.assertIsInstance(data, dict, "Response should be dict, not list")

        # Should NOT have nested reviewer objects at top level or in metrics
        metrics = data["session_wide_metrics"]
        self.assertNotIn("reviewer_a", metrics)
        self.assertNotIn("reviewer_b", metrics)

    def test_endpoint_handles_no_irr_data(self):
        """Test endpoint response when no IRR data exists yet."""
        # Create session without IRR data
        session_no_irr = SearchSession.objects.create(
            title="Session Without IRR",
            organisation=self.organisation,
            owner=self.owner,
            status="under_review",
        )

        config_no_irr = ReviewConfiguration.objects.create(
            session=session_no_irr, min_reviewers_per_result=2, created_by=self.owner
        )
        session_no_irr.current_configuration = config_no_irr
        session_no_irr.save()
        make_session_participant(session_no_irr, self.reviewer1)

        url = reverse(
            "review_results_api:session-irr-metrics",
            kwargs={"session_id": session_no_irr.id},
        )

        self.client.force_login(self.reviewer1)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Should return zero values, not error
        metrics = data["session_wide_metrics"]
        self.assertEqual(metrics["total_pairs"], 0)
        self.assertIsNone(metrics["average_kappa"])  # None when no IRR data exists

    def test_endpoint_requires_organisation_context(self):
        """Test that user without org and without session access gets 404."""
        # Create user without organisation
        user_no_org = create_test_user(username_prefix="no_org_user")
        # Delete any auto-created memberships (e.g., personal organisation from signals)
        OrganisationMembership.objects.filter(user=user_no_org).delete()

        self.client.force_login(user_no_org)
        response = self.client.get(self.url)

        # No org fast path fails, fallback checks access → denied → 404
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_endpoint_validates_session_ownership(self):
        """Test that endpoint validates session belongs to user's organisation."""
        # Create different organisation
        other_org = Organisation.objects.create(
            name="Other Organisation", slug="other-org"
        )

        other_user = create_test_user(username_prefix="other_user")
        OrganisationMembership.objects.create(
            organisation=other_org, user=other_user, role="REVIEWER", is_active=True
        )

        # Try to access session from different organisation
        self.client.force_login(other_user)
        response = self.client.get(self.url)

        # Should return 404 (get_object_or_404 behaviour)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invited_reviewer_from_different_org_can_access_endpoint(self):
        """Cross-org invited reviewers can access the IRR metrics endpoint."""
        other_org = Organisation.objects.create(
            name="External Organisation", slug="external-org"
        )
        external_reviewer = create_test_user(username_prefix="ext_reviewer")
        OrganisationMembership.objects.create(
            organisation=other_org,
            user=external_reviewer,
            role="REVIEWER",
            is_active=True,
        )

        ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=external_reviewer.email,
            inviter=self.owner,
            status=ReviewInvitation.STATUS_ACCEPTED,
        )

        self.client.force_login(external_reviewer)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("session_wide_metrics", data)
        self.assertFalse(data["is_session_owner"])

    def test_cochrane_threshold_detection(self):
        """Test that meets_cochrane flag correctly identifies threshold."""
        # Update IRR to below Cochrane threshold
        self.irr.cohens_kappa = 0.65
        self.irr.save()

        self.client.force_login(self.reviewer1)
        response = self.client.get(self.url)

        metrics = response.json()["session_wide_metrics"]
        self.assertFalse(metrics["meets_cochrane"])  # 0.65 < 0.70 threshold
        self.assertEqual(metrics["pairs_below_threshold"], 1)

    def test_multiple_reviewer_pairs(self):
        """Test endpoint with multiple reviewer pairs."""
        # Create third reviewer
        reviewer3 = create_test_user(username_prefix="reviewer3")
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=reviewer3,
            role="REVIEWER",
            is_active=True,
        )

        # Create second IRR pair (reviewer1 vs reviewer3)
        InterRaterReliability.objects.create(
            search_session=self.session,
            organisation=self.organisation,
            reviewer_a=self.reviewer1,
            reviewer_b=reviewer3,
            cohens_kappa=0.85,
            percentage_agreement=92.0,
            total_comparisons=5,
            agreements=4,
            disagreements=1,
            screening_stage="SCREENING",
            calculation_window_start=timezone.now() - timedelta(hours=1),
            calculation_window_end=timezone.now(),
        )

        self.client.force_login(self.reviewer1)
        response = self.client.get(self.url)

        metrics = response.json()["session_wide_metrics"]

        # Should average both pairs: (0.75 + 0.85) / 2 = 0.80
        self.assertEqual(metrics["total_pairs"], 2)
        self.assertAlmostEqual(metrics["average_kappa"], 0.80, places=2)
        self.assertTrue(metrics["meets_cochrane"])


class KappaWidgetIntegrationTestCase(DisablePersonalOrgSignalMixin, TestCase):
    """Integration tests for Kappa widget in full workflow context."""

    def setUp(self):
        """Set up test fixtures."""
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-integration-org"
        )

        self.owner = create_test_user(username_prefix="integration_owner")
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.owner,
            role="LEAD_REVIEWER",
            is_active=True,
        )

        self.session = SearchSession.objects.create(
            title="Integration Test Session",
            organisation=self.organisation,
            owner=self.owner,
            status="under_review",
        )

        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            irr_threshold=0.70,
            created_by=self.owner,
        )
        self.session.current_configuration = self.config
        self.session.save()

    def test_widget_data_refresh_workflow(self):
        """Test that widget can fetch updated IRR data after new calculations."""
        url = reverse(
            "review_results_api:session-irr-metrics",
            kwargs={"session_id": self.session.id},
        )

        self.client.force_login(self.owner)

        # Initial state: no IRR data
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        metrics = response.json()["session_wide_metrics"]
        self.assertEqual(metrics["total_pairs"], 0)

        # Simulate IRR calculation
        reviewer1 = create_test_user(username_prefix="r1")
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=reviewer1,
            role="REVIEWER",
            is_active=True,
        )

        reviewer2 = create_test_user(username_prefix="r2")
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=reviewer2,
            role="REVIEWER",
            is_active=True,
        )

        InterRaterReliability.objects.create(
            search_session=self.session,
            organisation=self.organisation,
            reviewer_a=reviewer1,
            reviewer_b=reviewer2,
            cohens_kappa=0.82,
            percentage_agreement=91.0,
            total_comparisons=10,
            agreements=9,
            disagreements=1,
            screening_stage="SCREENING",
            calculation_window_start=timezone.now() - timedelta(hours=1),
            calculation_window_end=timezone.now(),
        )

        # Refresh: should now have IRR data
        response = self.client.get(url)
        metrics = response.json()["session_wide_metrics"]
        self.assertEqual(metrics["total_pairs"], 1)
        self.assertAlmostEqual(metrics["average_kappa"], 0.82, places=2)
        self.assertTrue(metrics["meets_cochrane"])

    def test_widget_visible_only_for_workflow_2(self):
        """
        Test that widget endpoint works for Workflow #2 sessions only.

        Note: The endpoint will work for any session, but the template
        conditionally renders the widget only for is_workflow_2.
        """
        # Create Workflow #1 session
        workflow1_session = SearchSession.objects.create(
            title="Workflow 1 Session",
            organisation=self.organisation,
            owner=self.owner,
            status="under_review",
        )

        config1 = ReviewConfiguration.objects.create(
            session=workflow1_session,
            min_reviewers_per_result=1,  # Workflow #1
            created_by=self.owner,
        )
        workflow1_session.current_configuration = config1
        workflow1_session.save()

        url = reverse(
            "review_results_api:session-irr-metrics",
            kwargs={"session_id": workflow1_session.id},
        )

        self.client.force_login(self.owner)
        response = self.client.get(url)

        # API endpoint still works (returns no data for Workflow #1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        metrics = response.json()["session_wide_metrics"]
        self.assertEqual(metrics["total_pairs"], 0)  # No IRR in Workflow #1
