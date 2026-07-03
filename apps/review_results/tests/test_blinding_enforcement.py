"""
Tests for Blinding Enforcement in Dual-Screening Review

Validates PRISMA 2020 blind review compliance per Issue #24:
https://github.com/barrie-cork/agent-grey/issues/24

Test Coverage:
- BlindingService logic (when/how blinding applies)
- Permission checks (who can view what)
- API endpoint responses (data redaction)
- Serializer behavior (reviewer identity redaction)
- Edge cases (arbitrators, single screening, non-blinded sessions)
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import SearchSession, ReviewConfiguration
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import ReviewerAssignment, ReviewerDecision
from apps.review_results.services.blinding_service import BlindingService
from apps.review_results.serializers import (
    ReviewerDecisionOutputSerializer,
    ReviewerDecisionMinimalSerializer,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class BlindingServiceTests(TestCase):
    """Test BlindingService logic for determining when blinding applies."""

    def setUp(self):
        """Set up test data."""
        self.org = Organisation.objects.create(name="Test Org")

        self.user1 = create_test_user(username_prefix="reviewer1")
        self.user2 = create_test_user(username_prefix="reviewer2")

        # Create memberships
        OrganisationMembership.objects.create(
            user=self.user1, organisation=self.org, role="REVIEWER", is_active=True
        )
        OrganisationMembership.objects.create(
            user=self.user2, organisation=self.org, role="REVIEWER", is_active=True
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Blinded Test Session",
            organisation=self.org,
            owner=self.user1,
            status="under_review",
        )

        # Create blinded configuration and set as current
        self.blinded_config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
            created_by=self.user1,
        )
        self.session.current_configuration = self.blinded_config
        self.session.save()

        # Create result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://test.com",
            snippet="Test snippet",
            min_reviewers_required=2,
            reviewers_completed=0,
        )

    def test_should_blind_when_enforced_and_dual_screening(self):
        """Blinding should be active when config has blind_screening_enforced=True and min_reviewers>=2."""
        self.assertTrue(BlindingService.should_blind(self.session))

    def test_should_not_blind_when_not_enforced(self):
        """Blinding should be inactive when blind_screening_enforced=False."""
        self.blinded_config.blind_screening_enforced = False
        self.blinded_config.save()

        self.assertFalse(BlindingService.should_blind(self.session))

    def test_should_not_blind_when_single_screening(self):
        """Blinding should be inactive when min_reviewers_per_result < 2."""
        self.blinded_config.min_reviewers_per_result = 1
        self.blinded_config.save()

        self.assertFalse(BlindingService.should_blind(self.session))

    def test_can_view_own_decision(self):
        """Reviewers can always view their own decisions."""
        decision = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user1,
            decision="INCLUDE",
            confidence_level=3,  # High
            screening_stage="TITLE_ABSTRACT",
            organisation=self.org,
        )

        self.assertTrue(
            BlindingService.can_view_decision(decision, self.user1, self.session)
        )

    def test_cannot_view_other_decision_before_completion(self):
        """Reviewers cannot view others' decisions before result is fully reviewed."""
        decision = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user1,
            decision="INCLUDE",
            confidence_level=3,  # High
            screening_stage="TITLE_ABSTRACT",
            organisation=self.org,
        )

        self.assertFalse(
            BlindingService.can_view_decision(decision, self.user2, self.session)
        )

    def test_can_view_other_decision_after_completion(self):
        """Reviewers can view others' decisions after all required reviewers complete."""
        # First reviewer's decision
        decision1 = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user1,
            decision="INCLUDE",
            confidence_level=3,  # High
            screening_stage="TITLE_ABSTRACT",
            organisation=self.org,
        )

        # Second reviewer's decision (completes the result)
        ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user2,
            decision="EXCLUDE",
            confidence_level=2,  # Medium
            screening_stage="TITLE_ABSTRACT",
            organisation=self.org,
        )

        # Now user2 can view user1's decision
        self.assertTrue(
            BlindingService.can_view_decision(decision1, self.user2, self.session)
        )

    def test_arbitrator_can_always_view_decisions(self):
        """Arbitrators can view all decisions regardless of completion status."""
        arbitrator = create_test_user(username_prefix="arbitrator")
        OrganisationMembership.objects.create(
            user=arbitrator,
            organisation=self.org,
            role="SENIOR_RESEARCHER",
            is_active=True,
        )

        # Create arbitrator assignment
        ReviewerAssignment.objects.create(
            result=self.result,
            reviewer=arbitrator,
            role="ARBITRATOR",
            organisation=self.org,
        )

        decision = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user1,
            decision="INCLUDE",
            confidence_level=3,  # High
            screening_stage="TITLE_ABSTRACT",
            organisation=self.org,
        )

        self.assertTrue(
            BlindingService.can_view_decision(decision, arbitrator, self.session)
        )

    def test_is_result_fully_reviewed(self):
        """Test detection of fully reviewed results."""
        # Initially not fully reviewed
        self.assertFalse(
            BlindingService.is_result_fully_reviewed(self.result, self.session)
        )

        # Add one decision - still not fully reviewed
        ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user1,
            decision="INCLUDE",
            confidence_level=3,  # High
            screening_stage="TITLE_ABSTRACT",
            organisation=self.org,
        )

        self.assertFalse(
            BlindingService.is_result_fully_reviewed(self.result, self.session)
        )

        # Add second decision - now fully reviewed
        ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user2,
            decision="EXCLUDE",
            confidence_level=2,  # Medium
            screening_stage="TITLE_ABSTRACT",
            organisation=self.org,
        )

        self.assertTrue(
            BlindingService.is_result_fully_reviewed(self.result, self.session)
        )

    def test_get_blinding_status(self):
        """Test blinding status reporting."""
        status_info = BlindingService.get_blinding_status(self.session)

        self.assertTrue(status_info["is_blinded"])
        self.assertEqual(status_info["min_reviewers"], 2)
        self.assertIn("PRISMA", status_info["reason"])


class BlindingSerializerTests(TestCase):
    """Test serializer behavior for reviewer identity redaction."""

    def setUp(self):
        """Set up test data."""
        self.org = Organisation.objects.create(name="Test Org")

        self.user1 = create_test_user(username_prefix="reviewer1")
        self.user2 = create_test_user(username_prefix="reviewer2")

        OrganisationMembership.objects.create(
            user=self.user1, organisation=self.org, role="REVIEWER", is_active=True
        )
        OrganisationMembership.objects.create(
            user=self.user2, organisation=self.org, role="REVIEWER", is_active=True
        )

        self.session = SearchSession.objects.create(
            title="Blinded Test Session",
            organisation=self.org,
            owner=self.user1,
            status="under_review",
        )

        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
            created_by=self.user1,
        )
        self.session.current_configuration = config
        self.session.save()

        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://test.com",
            snippet="Test snippet",
            min_reviewers_required=2,
            reviewers_completed=0,
        )

        self.decision = ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user1,
            decision="INCLUDE",
            confidence_level=3,  # High
            screening_stage="TITLE_ABSTRACT",
            organisation=self.org,
        )

    def test_serializer_shows_own_decision(self):
        """Serializer should show actual reviewer info for own decisions."""
        from unittest.mock import Mock

        request = Mock()
        request.user = self.user1

        context = {"request": request, "session": self.session}

        serializer = ReviewerDecisionOutputSerializer(self.decision, context=context)
        data = serializer.data

        self.assertEqual(data["reviewer"]["username"], self.user1.username)
        self.assertEqual(data["reviewer"]["email"], self.user1.email)

    def test_serializer_redacts_other_reviewer_before_completion(self):
        """Serializer should redact other reviewer info before result completion."""
        from unittest.mock import Mock

        request = Mock()
        request.user = self.user2  # Different user

        context = {"request": request, "session": self.session}

        serializer = ReviewerDecisionOutputSerializer(self.decision, context=context)
        data = serializer.data

        self.assertEqual(data["reviewer"]["id"], "blinded")
        self.assertIn("Reviewer", data["reviewer"]["username"])
        self.assertEqual(data["reviewer"]["email"], "blinded@reviewer.local")

    def test_minimal_serializer_also_redacts(self):
        """ReviewerDecisionMinimalSerializer should also enforce blinding."""
        from unittest.mock import Mock

        request = Mock()
        request.user = self.user2

        context = {"request": request, "session": self.session}

        serializer = ReviewerDecisionMinimalSerializer(self.decision, context=context)
        data = serializer.data

        self.assertEqual(data["reviewer"]["id"], "blinded")


class BlindingAPITests(TestCase):
    """Test API endpoint responses respect blinding rules."""

    def setUp(self):
        """Set up test data and API client."""
        self.client = APIClient()
        self.org = Organisation.objects.create(name="Test Org")

        self.user1 = create_test_user(username_prefix="reviewer1")
        self.user2 = create_test_user(username_prefix="reviewer2")

        OrganisationMembership.objects.create(
            user=self.user1, organisation=self.org, role="LEAD_REVIEWER", is_active=True
        )
        OrganisationMembership.objects.create(
            user=self.user2, organisation=self.org, role="REVIEWER", is_active=True
        )

        self.session = SearchSession.objects.create(
            title="Blinded Test Session",
            organisation=self.org,
            owner=self.user1,
            status="under_review",
        )

        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
            created_by=self.user1,
        )
        self.session.current_configuration = config
        self.session.save()

        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://test.com",
            snippet="Test snippet",
            min_reviewers_required=2,
            reviewers_completed=0,
        )

    def test_dashboard_redacts_reviewer_identities(self):
        """Team dashboard should redact other reviewers' identities when blinded."""
        from django.urls import reverse

        # Create some decisions
        ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user1,
            decision="INCLUDE",
            confidence_level=3,  # High
            screening_stage="TITLE_ABSTRACT",
            organisation=self.org,
        )
        ReviewerDecision.objects.create(
            result=self.result,
            reviewer=self.user2,
            decision="EXCLUDE",
            confidence_level=2,  # Medium
            screening_stage="TITLE_ABSTRACT",
            organisation=self.org,
        )

        # Login as user1 (LEAD_REVIEWER, required for dashboard access)
        # Use force_login (not force_authenticate) so middleware sees authenticated user
        self.client.force_login(self.user1)

        # Request team stats via correct endpoint
        url = reverse("review_results_api:dashboard-stats")
        response = self.client.get(url, {"session_id": str(self.session.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        reviewer_breakdown = response.data["reviewer_breakdown"]

        # Find user2's stats
        user2_stats = next(
            (
                r
                for r in reviewer_breakdown
                if r["reviewer"]["username"] != self.user1.username
            ),
            None,
        )

        if user2_stats:
            # Should be blinded
            self.assertIn("Reviewer", user2_stats["reviewer"]["username"])
            self.assertEqual(user2_stats["reviewer"]["email"], "blinded@reviewer.local")


class BlindingEdgeCaseTests(TestCase):
    """Test edge cases and special scenarios for blinding."""

    def setUp(self):
        """Set up test data."""
        self.org = Organisation.objects.create(name="Test Org")

        self.user1 = create_test_user(username_prefix="reviewer1")

        OrganisationMembership.objects.create(
            user=self.user1, organisation=self.org, role="REVIEWER", is_active=True
        )

        self.session = SearchSession.objects.create(
            title="Test Session",
            organisation=self.org,
            owner=self.user1,
            status="under_review",
        )

    def test_no_config_means_no_blinding(self):
        """Session without configuration should not enforce blinding."""
        self.assertFalse(BlindingService.should_blind(self.session))

    def test_non_blinded_single_screening_mode(self):
        """Single screening mode should not enforce blinding."""
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=1,
            blind_screening_enforced=False,
            created_by=self.user1,
        )
        self.session.current_configuration = config
        self.session.save()

        self.assertFalse(BlindingService.should_blind(self.session))

    def test_explicitly_disabled_blinding(self):
        """Explicitly disabled blinding should be respected."""
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            blind_screening_enforced=False,
            created_by=self.user1,
        )
        self.session.current_configuration = config
        self.session.save()

        self.assertFalse(BlindingService.should_blind(self.session))
