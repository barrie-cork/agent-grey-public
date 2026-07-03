"""
End-to-end tests for dual screening workflow.

Tests the complete workflow from configuration to IRR calculation, ensuring
all components work together correctly for PRISMA 2020 compliance.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import SearchSession, ReviewConfiguration
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import (
    ReviewerAssignment,
    ConflictResolution,
)
from apps.core.tests.utils import create_test_user
from apps.review_results.services.review_claim_service import ReviewClaimService
from apps.review_results.services.review_coordination_service import (
    ReviewCoordinationService,
)
from apps.review_results.services.irr_service import InterRaterReliabilityService

User = get_user_model()


class DualScreeningE2ETest(TestCase):
    """Test complete dual screening workflow."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation",
            slug="test-org",
            require_dual_review=True,
            default_min_reviewers=2,
        )

        # Create users
        self.lead = create_test_user(username_prefix="lead")
        self.reviewer1 = create_test_user(username_prefix="reviewer1")
        self.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create memberships
        OrganisationMembership.objects.create(
            user=self.lead, organisation=self.org, role="LEAD_REVIEWER"
        )
        OrganisationMembership.objects.create(
            user=self.reviewer1, organisation=self.org, role="REVIEWER"
        )
        OrganisationMembership.objects.create(
            user=self.reviewer2, organisation=self.org, role="REVIEWER"
        )

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            organisation=self.org,
            owner=self.lead,
            status="ready_for_review",
        )

        # Create configuration
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            created_by=self.lead,
            organisation=self.org,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
        )
        self.session.current_configuration = self.config
        self.session.save()

        # Create test result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            snippet="Test snippet",
            url="http://test.com",
            min_reviewers_required=2,
        )

        # Services
        self.claim_service = ReviewClaimService()
        self.coord_service = ReviewCoordinationService()
        self.irr_service = InterRaterReliabilityService()

    def test_dual_screening_workflow_with_conflict(self):
        """Test complete workflow from claim to conflict resolution."""

        # Step 1: Reviewer 1 claims and decides INCLUDE
        claimed1 = self.claim_service.claim_next_result(
            reviewer=self.reviewer1,
            organisation=self.org,
            session_id=str(self.session.id),
        )
        self.assertIsNotNone(claimed1)
        assert claimed1 is not None
        self.assertEqual(str(claimed1.id), str(self.result.id))

        decision1 = self.coord_service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer1,
            decision_data={
                "decision": "INCLUDE",
                "confidence_level": 3,
                "screening_stage": "SCREENING",
            },
            organisation=self.org,
        )
        self.assertEqual(decision1.decision, "INCLUDE")

        # Step 2: Reviewer 2 claims and decides EXCLUDE (CONFLICT)
        claimed2 = self.claim_service.claim_next_result(
            reviewer=self.reviewer2,
            organisation=self.org,
            session_id=str(self.session.id),
        )
        assert claimed2 is not None
        self.assertEqual(str(claimed2.id), str(self.result.id))  # Same result

        decision2 = self.coord_service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer2,
            decision_data={
                "decision": "EXCLUDE",
                "confidence_level": 2,
                "screening_stage": "SCREENING",
            },
            organisation=self.org,
        )
        self.assertEqual(decision2.decision, "EXCLUDE")

        # Step 3: Verify conflict created
        conflicts = ConflictResolution.objects.filter(result=self.result)
        self.assertEqual(conflicts.count(), 1)

        conflict = conflicts.first()
        self.assertEqual(conflict.conflict_type, "INCLUDE_EXCLUDE")
        self.assertEqual(conflict.status, "PENDING")
        self.assertEqual(conflict.conflicting_decisions.count(), 2)

        # Step 4: Resolve conflict
        resolved = self.coord_service.resolve_conflict(
            conflict_id=str(conflict.id),
            resolver=self.lead,
            resolution_data={
                "resolution_method": "CONSENSUS",
                "decision": "EXCLUDE",
                "resolution_notes": "After discussion, agreed to exclude",
            },
            organisation=self.org,
        )

        self.assertEqual(resolved.status, "RESOLVED")
        self.assertEqual(resolved.final_decision.decision, "EXCLUDE")
        self.assertEqual(resolved.resolution_method, "CONSENSUS")
        self.assertIsNotNone(resolved.resolved_at)

    def test_dual_screening_workflow_with_consensus(self):
        """Test workflow when both reviewers agree."""

        # Step 1: Reviewer 1 claims and decides INCLUDE
        claimed1 = self.claim_service.claim_next_result(
            reviewer=self.reviewer1,
            organisation=self.org,
            session_id=str(self.session.id),
        )
        self.assertIsNotNone(claimed1)

        _decision1 = self.coord_service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer1,
            decision_data={
                "decision": "INCLUDE",
                "confidence_level": 3,
                "screening_stage": "SCREENING",
            },
            organisation=self.org,
        )

        # Step 2: Reviewer 2 claims and decides INCLUDE (CONSENSUS)
        _claimed2 = self.claim_service.claim_next_result(
            reviewer=self.reviewer2,
            organisation=self.org,
            session_id=str(self.session.id),
        )

        _decision2 = self.coord_service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer2,
            decision_data={
                "decision": "INCLUDE",
                "confidence_level": 3,
                "screening_stage": "SCREENING",
            },
            organisation=self.org,
        )

        # Step 3: Verify no conflict created
        conflicts = ConflictResolution.objects.filter(result=self.result)
        self.assertEqual(conflicts.count(), 0)

        # Step 4: Verify consensus reached
        self.result.refresh_from_db()
        self.assertTrue(self.result.consensus_reached)

    def test_irr_calculation_trigger(self):
        """Test IRR calculation triggered after 10 decisions."""
        # Create 10 results
        results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i}",
                snippet="Test",
                url=f"http://test{i}.com",
                min_reviewers_required=2,
            )
            results.append(result)

        # Submit 10 decisions from both reviewers (all INCLUDE for perfect agreement)
        # Use direct assignment to ensure both reviewers assess the SAME results
        for result in results:
            # Create assignments directly (bypasses claim service for IRR testing)
            _assignment1 = ReviewerAssignment.objects.create(
                organisation=self.org,
                result=result,
                reviewer=self.reviewer1,
                role="PRIMARY",
                is_active=True,
            )
            _assignment2 = ReviewerAssignment.objects.create(
                organisation=self.org,
                result=result,
                reviewer=self.reviewer2,
                role="SECONDARY",
                is_active=True,
            )

            # Submit decisions for the same result
            self.coord_service.submit_reviewer_decision(
                result_id=str(result.id),
                reviewer=self.reviewer1,
                decision_data={
                    "decision": "INCLUDE",
                    "confidence_level": 3,
                    "screening_stage": "SCREENING",
                },
                organisation=self.org,
            )

            self.coord_service.submit_reviewer_decision(
                result_id=str(result.id),
                reviewer=self.reviewer2,
                decision_data={
                    "decision": "INCLUDE",
                    "confidence_level": 3,
                    "screening_stage": "SCREENING",
                },
                organisation=self.org,
            )

        # Manually trigger IRR calculation (in production this is async via Celery)
        irr = self.irr_service.calculate_cohens_kappa(
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            organisation=self.org,
            search_session=self.session,
        )

        # Verify IRR calculated
        self.assertIsNotNone(irr)
        assert irr is not None
        self.assertGreaterEqual(irr.cohens_kappa, 0.9)  # Perfect agreement
        self.assertEqual(irr.total_comparisons, 10)
        self.assertTrue(irr.cohens_kappa >= 0.70)  # Cochrane threshold

    def test_irr_calculation_with_mixed_decisions(self):
        """Test IRR calculation with some disagreements."""
        # Create 10 results
        results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i}",
                snippet="Test",
                url=f"http://test{i}.com",
                min_reviewers_required=2,
            )
            results.append(result)

        # Submit mixed decisions: 7 agreements, 3 disagreements
        # Use direct assignment to ensure both reviewers assess the SAME results
        for i, result in enumerate(results):
            # Create assignments directly
            ReviewerAssignment.objects.create(
                organisation=self.org,
                result=result,
                reviewer=self.reviewer1,
                role="PRIMARY",
                is_active=True,
            )
            ReviewerAssignment.objects.create(
                organisation=self.org,
                result=result,
                reviewer=self.reviewer2,
                role="SECONDARY",
                is_active=True,
            )

            # Create balanced scenario for realistic Cohen's Kappa calculation
            # Both reviewers must show variance (use both INCLUDE and EXCLUDE)
            # to avoid degenerate cases where Kappa = 0.0 or NaN
            #
            # Reviewer 1: INCLUDE for results 0-5 (6 results), EXCLUDE for 6-9 (4 results)
            # Reviewer 2: INCLUDE for results 0-2 (3 results), EXCLUDE for 3-9 (7 results)
            # Agreements: Results 0,1,2 (both INCLUDE), 6,7,8,9 (both EXCLUDE) = 7 agreements (70%)
            # Disagreements: Results 3,4,5 (INCLUDE vs EXCLUDE) = 3 disagreements (30%)
            #
            # This produces moderate Kappa (~0.4) suitable for testing IRR calculations
            r1_decision = "EXCLUDE" if i >= 6 else "INCLUDE"
            r1_decision_data = {
                "decision": r1_decision,
                "confidence_level": 3,
                "screening_stage": "SCREENING",
            }
            if r1_decision == "EXCLUDE":
                r1_decision_data["exclusion_reason"] = "NOT_RELEVANT"

            self.coord_service.submit_reviewer_decision(
                result_id=str(result.id),
                reviewer=self.reviewer1,
                decision_data=r1_decision_data,
                organisation=self.org,
            )

            # Reviewer 2 decisions for 70% agreement with balanced labels
            decision = "EXCLUDE" if i >= 3 else "INCLUDE"
            decision_data = {
                "decision": decision,
                "confidence_level": 2,
                "screening_stage": "SCREENING",
            }
            if decision == "EXCLUDE":
                decision_data["exclusion_reason"] = "METHODOLOGY"

            self.coord_service.submit_reviewer_decision(
                result_id=str(result.id),
                reviewer=self.reviewer2,
                decision_data=decision_data,
                organisation=self.org,
            )

        # Calculate IRR
        irr = self.irr_service.calculate_cohens_kappa(
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            organisation=self.org,
            search_session=self.session,
        )

        # Verify IRR calculated
        self.assertIsNotNone(irr)
        assert irr is not None
        self.assertEqual(irr.total_comparisons, 10)
        self.assertEqual(irr.agreements, 7)
        self.assertEqual(irr.disagreements, 3)
        self.assertEqual(irr.percentage_agreement, 70.0)
        # Kappa should be moderate (0.4-0.6) due to 70% agreement
        self.assertGreater(irr.cohens_kappa, 0.4)

    def test_insufficient_data_for_irr(self):
        """Test that IRR calculation returns None with insufficient data."""
        # Only 1 overlapping decision
        self.claim_service.claim_next_result(
            reviewer=self.reviewer1,
            organisation=self.org,
            session_id=str(self.session.id),
        )
        self.coord_service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer1,
            decision_data={
                "decision": "INCLUDE",
                "confidence_level": 3,
                "screening_stage": "SCREENING",
            },
            organisation=self.org,
        )

        # Attempt IRR calculation
        irr = self.irr_service.calculate_cohens_kappa(
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            organisation=self.org,
            search_session=self.session,
        )

        # Should return None due to insufficient common results
        self.assertIsNone(irr)

    def test_get_irr_summary(self):
        """Test IRR summary generation."""
        # Create and calculate IRR for multiple pairs
        results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i}",
                snippet="Test",
                url=f"http://test{i}.com",
                min_reviewers_required=2,
            )
            results.append(result)

        # Submit decisions - use direct assignment for predictable IRR testing
        for result in results:
            # Create assignments directly
            ReviewerAssignment.objects.create(
                organisation=self.org,
                result=result,
                reviewer=self.reviewer1,
                role="PRIMARY",
                is_active=True,
            )
            ReviewerAssignment.objects.create(
                organisation=self.org,
                result=result,
                reviewer=self.reviewer2,
                role="SECONDARY",
                is_active=True,
            )

            # Both reviewers submit decisions for the same result
            self.coord_service.submit_reviewer_decision(
                result_id=str(result.id),
                reviewer=self.reviewer1,
                decision_data={
                    "decision": "INCLUDE",
                    "confidence_level": 3,
                    "screening_stage": "SCREENING",
                },
                organisation=self.org,
            )

            self.coord_service.submit_reviewer_decision(
                result_id=str(result.id),
                reviewer=self.reviewer2,
                decision_data={
                    "decision": "INCLUDE",
                    "confidence_level": 3,
                    "screening_stage": "SCREENING",
                },
                organisation=self.org,
            )

        # Calculate IRR
        _irr = self.irr_service.calculate_cohens_kappa(
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            organisation=self.org,
            search_session=self.session,
        )

        # Get summary
        summary = self.irr_service.get_irr_summary(
            organisation=self.org, search_session=self.session
        )

        # Verify summary
        self.assertIsNotNone(summary["average_kappa"])
        self.assertEqual(summary["total_pairs"], 1)
        self.assertTrue(summary["meets_cochrane"])
        self.assertEqual(summary["pairs_below_threshold"], 0)
