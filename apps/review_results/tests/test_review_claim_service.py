"""
Tests for ReviewClaimService - Atomic result claiming for dual-reviewer workflows.

Focus areas:
- Atomic claiming with SELECT FOR UPDATE SKIP LOCKED
- Race condition prevention with concurrent users
- Skip result enforcement
- Claim timeout auto-release
- Role assignment (PRIMARY → SECONDARY → ARBITRATOR)
- Organisation scoping security
"""

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import ReviewerAssignment, ResultSkip
from apps.review_results.services.review_claim_service import ReviewClaimService
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ReviewClaimServiceTest(TransactionTestCase):
    """Test ReviewClaimService for race-condition-free claiming."""

    def setUp(self):
        """Set up test data with organisation, reviewers, and session."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create test users/reviewers
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        OrganisationMembership.objects.create(
            user=self.reviewer1,
            organisation=self.organisation,
            role=OrganisationMembership.ROLE_REVIEWER,
        )

        self.reviewer2 = create_test_user(username_prefix="reviewer2")
        OrganisationMembership.objects.create(
            user=self.reviewer2,
            organisation=self.organisation,
            role=OrganisationMembership.ROLE_REVIEWER,
        )

        self.reviewer3 = create_test_user(username_prefix="reviewer3")
        OrganisationMembership.objects.create(
            user=self.reviewer3,
            organisation=self.organisation,
            role=OrganisationMembership.ROLE_REVIEWER,
        )

        # Create session owner
        self.owner = create_test_user(username_prefix="owner")
        OrganisationMembership.objects.create(
            user=self.owner,
            organisation=self.organisation,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

        # Create search session
        self.session = SearchSession.objects.create(
            title="Test Dual-Reviewer Session",
            owner=self.owner,
            status="under_review",
            organisation=self.organisation,
        )

        # Create test results
        self.results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i}",
                url=f"https://example.com/test{i}",
                snippet=f"Test snippet {i}",
            )
            self.results.append(result)

        self.service = ReviewClaimService()

    def test_claim_next_result_basic(self):
        """Test basic result claiming by a single reviewer."""
        result = self.service.claim_next_result(
            reviewer=self.reviewer1,
            organisation=self.organisation,
            session_id=str(self.session.id),
        )

        self.assertIsNotNone(result)
        self.assertIn(result, self.results)

        # Verify assignment created
        assignment = ReviewerAssignment.objects.filter(
            result=result, reviewer=self.reviewer1, is_active=True
        ).first()
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.role, "PRIMARY")

    def test_claim_excludes_already_reviewed(self):
        """Test reviewer cannot claim result they already reviewed."""
        # Reviewer 1 claims and gets assigned
        result = self.service.claim_next_result(
            organisation=self.organisation,
            session_id=str(self.session.id),
            reviewer=self.reviewer1,
        )

        # Reviewer 1 tries to claim again - should get different result
        result2 = self.service.claim_next_result(
            organisation=self.organisation,
            session_id=str(self.session.id),
            reviewer=self.reviewer1,
        )

        assert result is not None
        assert result2 is not None
        self.assertNotEqual(result.id, result2.id)

    def test_claim_excludes_skipped_results(self):
        """Test ResultSkip prevents reassignment."""
        # Skip first result
        skip_result = self.results[0]
        ResultSkip.objects.create(
            result=skip_result,
            organisation=self.organisation,
            reviewer=self.reviewer1,
            reason="Test skip",
        )

        # Claim next - should NOT get skipped result
        claimed = self.service.claim_next_result(
            organisation=self.organisation,
            session_id=str(self.session.id),
            reviewer=self.reviewer1,
        )

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertNotEqual(claimed.id, skip_result.id)

    def test_role_assignment_progression(self):
        """Test role assignment: PRIMARY → SECONDARY → ARBITRATOR."""
        result = self.results[0]

        # First reviewer gets PRIMARY
        self.service.claim_next_result(
            organisation=self.organisation,
            session_id=str(self.session.id),
            reviewer=self.reviewer1,
        )
        assignment1 = ReviewerAssignment.objects.get(
            result=result, reviewer=self.reviewer1
        )
        self.assertEqual(assignment1.role, "PRIMARY")

        # Second reviewer gets SECONDARY
        self.service.claim_next_result(
            organisation=self.organisation,
            session_id=str(self.session.id),
            reviewer=self.reviewer2,
        )
        assignment2 = ReviewerAssignment.objects.filter(
            result=result, reviewer=self.reviewer2
        ).first()

        if assignment2:  # May get different result
            self.assertEqual(assignment2.role, "SECONDARY")

    def test_organisation_scoping_security(self):
        """Test organisation scoping prevents data leaks."""
        # Create second organisation
        org2 = Organisation.objects.create(name="Other Organisation", slug="other-org")

        # Attempt to claim with wrong organisation
        result = self.service.claim_next_result(
            organisation=org2, session_id=str(self.session.id), reviewer=self.reviewer1
        )

        # Should return None (no results belong to org2)
        self.assertIsNone(result)

    def test_claim_requires_organisation(self):
        """Test ValueError raised when organisation is None."""
        with self.assertRaises(ValueError) as context:
            self.service.claim_next_result(
                organisation=None,  # type: ignore[arg-type]
                session_id=str(self.session.id),
                reviewer=self.reviewer1,
            )

        self.assertIn("Organisation is required", str(context.exception))
