"""
WF2 Dual Screening Hardening Tests.

Tests for edge cases and race condition fixes in the dual screening workflow:
- Duplicate conflict prevention (DB constraint + application-level guard)
- Escalated conflict resolution blocking
- Signal reliability (ReviewerCompletion creation)
- IRR summary denominator transparency
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from unittest.mock import patch

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import (
    ReviewInvitation,
    SearchSession,
)
from apps.review_results.models import (
    ConflictResolution,
    ReviewerAssignment,
    ReviewerCompletion,
    ReviewerDecision,
)
from apps.review_results.services.irr_service import InterRaterReliabilityService
from apps.review_results.services.review_coordination_service import (
    ReviewCoordinationService,
)

User = get_user_model()


class DuplicateConflictPreventionTest(TestCase):
    """Test that duplicate conflicts cannot be created for the same result."""

    def setUp(self):
        self.organisation = Organisation.objects.create(
            name="Test Org", slug="test-dup-conflict"
        )
        self.owner = create_test_user(username_prefix="dup-owner")
        OrganisationMembership.objects.create(
            user=self.owner,
            organisation=self.organisation,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )
        self.session = SearchSession.objects.create(
            title="Dup Conflict Test",
            owner=self.owner,
            status="under_review",
            organisation=self.organisation,
        )
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/dup-test",
            snippet="Test",
        )

    def test_db_constraint_prevents_second_active_conflict(self):
        """DB constraint blocks creating a second active conflict for the same result."""
        ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )

        with self.assertRaises(IntegrityError):
            ConflictResolution.objects.create(
                organisation=self.organisation,
                result=self.result,
                conflict_type="INCLUDE_EXCLUDE",
                status="IN_DISCUSSION",
            )

    def test_resolved_conflict_allows_new_active(self):
        """A RESOLVED conflict does not block creating a new conflict for same result."""
        ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="RESOLVED",
        )

        # This should succeed -- resolved conflicts don't block new ones
        new_conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="LOW_CONFIDENCE",
            status="PENDING",
        )
        self.assertEqual(new_conflict.status, "PENDING")

    def test_evaluate_decisions_skips_if_active_conflict_exists(self):
        """_evaluate_decisions skips conflict creation when one already exists."""
        reviewer1 = create_test_user(username_prefix="eval-r1")
        reviewer2 = create_test_user(username_prefix="eval-r2")

        for reviewer in [reviewer1, reviewer2]:
            OrganisationMembership.objects.create(
                user=reviewer,
                organisation=self.organisation,
                role=OrganisationMembership.ROLE_REVIEWER,
            )
            ReviewerAssignment.objects.create(
                organisation=self.organisation,
                result=self.result,
                reviewer=reviewer,
            )

        # Create existing conflict
        existing = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )

        # Create conflicting decisions
        ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=reviewer1,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=reviewer2,
            decision="EXCLUDE",
            screening_stage="SCREENING",
        )

        # Call _evaluate_decisions -- should NOT create a second conflict
        service = ReviewCoordinationService()
        service._evaluate_decisions(self.result, "SCREENING")

        self.assertEqual(
            ConflictResolution.objects.filter(result=self.result).count(),
            1,
            "Should not create a duplicate conflict",
        )
        self.assertEqual(
            ConflictResolution.objects.get(result=self.result).id,
            existing.id,
        )


class EscalatedConflictResolutionTest(TestCase):
    """Test that escalated conflicts cannot be resolved via normal resolution."""

    def setUp(self):
        self.organisation = Organisation.objects.create(
            name="Test Org", slug="test-escalation"
        )
        self.resolver = create_test_user(username_prefix="esc-resolver")
        OrganisationMembership.objects.create(
            user=self.resolver,
            organisation=self.organisation,
            role=OrganisationMembership.ROLE_INFORMATION_SPECIALIST,
        )
        self.session = SearchSession.objects.create(
            title="Escalation Test",
            owner=self.resolver,
            status="under_review",
            organisation=self.organisation,
        )
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Escalated Result",
            url="https://example.com/escalated",
            snippet="Test",
        )

    def test_resolve_conflict_blocks_escalated_status(self):
        """resolve_conflict raises ValueError when conflict is ESCALATED."""
        conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="ESCALATED",
        )

        # Create assignment so resolver can create a decision
        ReviewerAssignment.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=self.resolver,
        )

        service = ReviewCoordinationService()

        with self.assertRaises(ValueError) as ctx:
            service.resolve_conflict(
                conflict_id=str(conflict.id),
                resolver=self.resolver,
                resolution_data={
                    "decision": "INCLUDE",
                    "resolution_method": "CONSENSUS",
                },
                organisation=self.organisation,
            )

        self.assertIn("escalated", str(ctx.exception).lower())

    def test_resolve_conflict_blocks_already_resolved(self):
        """resolve_conflict raises ValueError when conflict is already RESOLVED."""
        conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="RESOLVED",
        )

        service = ReviewCoordinationService()

        with self.assertRaises(ValueError) as ctx:
            service.resolve_conflict(
                conflict_id=str(conflict.id),
                resolver=self.resolver,
                resolution_data={
                    "decision": "INCLUDE",
                    "resolution_method": "CONSENSUS",
                },
                organisation=self.organisation,
            )

        self.assertIn("already resolved", str(ctx.exception).lower())


class ReviewerCompletionSignalTest(TestCase):
    """Test ReviewerCompletion creation signal reliability."""

    def setUp(self):
        self.organisation = Organisation.objects.create(
            name="Test Org", slug="test-completion-signal"
        )
        self.owner = create_test_user(username_prefix="sig-owner")
        OrganisationMembership.objects.create(
            user=self.owner,
            organisation=self.organisation,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )
        self.reviewer = create_test_user(username_prefix="sig-reviewer")
        OrganisationMembership.objects.create(
            user=self.reviewer,
            organisation=self.organisation,
            role=OrganisationMembership.ROLE_REVIEWER,
        )
        self.session = SearchSession.objects.create(
            title="Signal Test Session",
            owner=self.owner,
            status="ready_for_review",
            organisation=self.organisation,
            total_results=5,
        )

    @patch(
        "apps.review_results.signals.EmailNotificationService",
        autospec=True,
    )
    def test_invitation_acceptance_creates_completion_record(self, mock_email):
        """Accepting an invitation creates a ReviewerCompletion record."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer.email,
            inviter=self.owner,
            status="PENDING",
        )

        # Accept the invitation
        invitation.status = ReviewInvitation.STATUS_ACCEPTED
        invitation.invitee = self.reviewer
        invitation.save()

        self.assertTrue(
            ReviewerCompletion.objects.filter(
                session=self.session, reviewer=self.reviewer
            ).exists(),
            "ReviewerCompletion should be created on invitation acceptance",
        )

    @patch(
        "apps.review_results.signals.EmailNotificationService",
        autospec=True,
    )
    def test_duplicate_acceptance_does_not_create_second_completion(self, mock_email):
        """Re-saving an accepted invitation does not create a duplicate completion."""
        # Pre-create the completion record
        ReviewerCompletion.objects.create(
            session=self.session,
            reviewer=self.reviewer,
            total_results=5,
            reviewed_results=0,
        )

        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer.email,
            inviter=self.owner,
            invitee=self.reviewer,
            status=ReviewInvitation.STATUS_ACCEPTED,
        )

        # Re-save the invitation (simulates duplicate signal fire)
        invitation.save()

        self.assertEqual(
            ReviewerCompletion.objects.filter(
                session=self.session, reviewer=self.reviewer
            ).count(),
            1,
            "Should not create duplicate ReviewerCompletion",
        )


class IRRSummaryDenominatorTest(TestCase):
    """Test that IRR summary includes valid kappa pair count."""

    def setUp(self):
        self.organisation = Organisation.objects.create(
            name="Test Org", slug="test-irr-denom"
        )
        self.owner = create_test_user(username_prefix="irr-owner")
        self.reviewer1 = create_test_user(username_prefix="irr-r1")
        self.reviewer2 = create_test_user(username_prefix="irr-r2")

        for user in [self.owner, self.reviewer1, self.reviewer2]:
            OrganisationMembership.objects.create(
                user=user,
                organisation=self.organisation,
                role=OrganisationMembership.ROLE_REVIEWER,
            )

        self.session = SearchSession.objects.create(
            title="IRR Denominator Test",
            owner=self.owner,
            status="under_review",
            organisation=self.organisation,
        )

    def test_summary_includes_pairs_with_valid_kappa(self):
        """IRR summary contains pairs_with_valid_kappa for transparency."""
        # Create results and decisions for IRR calculation
        results = []
        for i in range(3):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i}",
                url=f"https://example.com/irr/{i}",
                snippet="Test",
            )
            results.append(result)

        # Both reviewers agree on all results
        for result in results:
            for reviewer in [self.reviewer1, self.reviewer2]:
                ReviewerAssignment.objects.create(
                    organisation=self.organisation,
                    result=result,
                    reviewer=reviewer,
                )
                ReviewerDecision.objects.create(
                    organisation=self.organisation,
                    result=result,
                    reviewer=reviewer,
                    decision="INCLUDE",
                    screening_stage="SCREENING",
                )

        service = InterRaterReliabilityService()
        service.calculate_cohens_kappa(
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            organisation=self.organisation,
            search_session=self.session,
        )

        summary = service.get_irr_summary(self.organisation, self.session)

        self.assertIn("pairs_with_valid_kappa", summary)
        self.assertEqual(summary["pairs_with_valid_kappa"], 1)
        self.assertEqual(summary["total_pairs"], 1)
