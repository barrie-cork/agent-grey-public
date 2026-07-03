"""
Tests for ReviewCoordinationService - Conflict detection and resolution orchestration.

Focus areas:
- Conflict detection triggers on 2nd disagreeing decision
- Consensus detection on 2nd agreeing decision
- Duplicate decision prevention (UniqueConstraint)
- Conflict type classification (INCLUDE_EXCLUDE, EXCLUDE_INCLUDE, MAYBE, etc.)
- IRR calculation trigger
- Organisation scoping security
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch

from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import (
    ReviewerAssignment,
    ReviewerDecision,
    ConflictResolution,
)
from apps.core.tests.utils import DisablePersonalOrgSignalMixin, create_test_user
from apps.review_manager.models import ReviewConfiguration
from apps.review_results.services.review_coordination_service import (
    ReviewCoordinationService,
)

User = get_user_model()


class ReviewCoordinationServiceTest(TestCase):
    """Test ReviewCoordinationService for conflict detection and resolution."""

    def setUp(self):
        """Set up test data with organisation, session, and reviewers."""
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        self.owner = create_test_user(username_prefix="owner")
        OrganisationMembership.objects.create(
            user=self.owner,
            organisation=self.organisation,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

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

        self.session = SearchSession.objects.create(
            title="Test Coordination Session",
            owner=self.owner,
            status="under_review",
            organisation=self.organisation,
        )

        # WF2 configuration required so consensus_criteria is readable
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            consensus_criteria="MAJORITY",
            version=1,
            organisation=self.organisation,
            created_by=self.owner,
        )
        self.session.current_configuration = self.config
        self.session.save()

        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet",
            min_reviewers_required=2,
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

        self.service = ReviewCoordinationService()

    def test_submit_decision_first_reviewer(self):
        """Test submitting first decision creates ReviewerDecision."""
        decision_data = {
            "decision": "INCLUDE",
            "exclusion_reason": "",
            "confidence_level": 2,
            "notes": "Relevant study",
            "screening_stage": "SCREENING",
            "time_spent_seconds": 120,
        }

        decision = self.service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer1,
            decision_data=decision_data,
            organisation=self.organisation,
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision.decision, "INCLUDE")
        self.assertEqual(decision.reviewer, self.reviewer1)

        # No conflict should be created yet (only 1 decision)
        conflicts = ConflictResolution.objects.filter(result=self.result)
        self.assertEqual(conflicts.count(), 0)

    def test_consensus_detection_agreeing_decisions(self):
        """Test consensus detection when both reviewers agree."""
        decision_data = {
            "decision": "INCLUDE",
            "exclusion_reason": "",
            "confidence_level": 2,
            "notes": "Relevant study",
            "screening_stage": "SCREENING",
        }

        # First decision
        self.service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer1,
            decision_data=decision_data,
            organisation=self.organisation,
        )

        # Second decision (agrees)
        self.service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer2,
            decision_data=decision_data,
            organisation=self.organisation,
        )

        # Check consensus reached
        self.result.refresh_from_db()
        self.assertTrue(self.result.consensus_reached)

        # Verify both decisions are INCLUDE
        decisions = ReviewerDecision.objects.filter(result=self.result)
        self.assertEqual(decisions.count(), 2)
        for decision in decisions:
            self.assertEqual(decision.decision, "INCLUDE")

        # No conflict should exist
        conflicts = ConflictResolution.objects.filter(result=self.result)
        self.assertEqual(conflicts.count(), 0)

    def test_conflict_detection_disagreeing_decisions(self):
        """Test conflict detection on 2nd disagreeing decision."""
        # First decision: INCLUDE
        decision_data_1 = {
            "decision": "INCLUDE",
            "exclusion_reason": "",
            "confidence_level": 2,
            "notes": "Relevant",
            "screening_stage": "SCREENING",
        }

        self.service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer1,
            decision_data=decision_data_1,
            organisation=self.organisation,
        )

        # Second decision: EXCLUDE (disagrees)
        decision_data_2 = {
            "decision": "EXCLUDE",
            "exclusion_reason": "Not relevant",
            "confidence_level": 3,
            "notes": "Out of scope",
            "screening_stage": "SCREENING",
        }

        self.service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer2,
            decision_data=decision_data_2,
            organisation=self.organisation,
        )

        # Verify conflict created
        conflict = ConflictResolution.objects.filter(result=self.result).first()
        self.assertIsNotNone(conflict)
        self.assertEqual(conflict.conflict_type, "INCLUDE_EXCLUDE")
        self.assertEqual(conflict.status, "PENDING")

        # Verify result NOT marked as consensus
        self.result.refresh_from_db()
        self.assertFalse(self.result.consensus_reached)

    def test_duplicate_decision_prevention(self):
        """Test UniqueConstraint prevents duplicate decisions."""
        decision_data = {
            "decision": "INCLUDE",
            "exclusion_reason": "",
            "confidence_level": 2,
            "notes": "Test",
            "screening_stage": "SCREENING",
        }

        # First submission
        self.service.submit_reviewer_decision(
            result_id=str(self.result.id),
            reviewer=self.reviewer1,
            decision_data=decision_data,
            organisation=self.organisation,
        )

        # Second submission by same reviewer - should raise ValueError (not IntegrityError)
        with self.assertRaises(ValueError):
            self.service.submit_reviewer_decision(
                result_id=str(self.result.id),
                reviewer=self.reviewer1,
                decision_data=decision_data,
                organisation=self.organisation,
            )

    def test_conflict_type_classification(self):
        """Test correct conflict_type assignment for different decision combinations."""
        test_cases = [
            ("INCLUDE", "EXCLUDE", "INCLUDE_EXCLUDE"),
            ("EXCLUDE", "INCLUDE", "INCLUDE_EXCLUDE"),  # Normalized to INCLUDE_EXCLUDE
            ("INCLUDE", "MAYBE", "LOW_CONFIDENCE"),  # Mixed decisions
            ("EXCLUDE", "MAYBE", "LOW_CONFIDENCE"),  # Mixed decisions
            ("MAYBE", "INCLUDE", "LOW_CONFIDENCE"),  # Mixed decisions
        ]

        for idx, (decision1, decision2, expected_type) in enumerate(test_cases):
            # Create new result for each test (min_reviewers_required=2 for WF2)
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {idx}",
                url=f"https://example.com/test{idx}",
                snippet="Test",
                min_reviewers_required=2,
            )

            # Create assignments
            ReviewerAssignment.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=self.reviewer1,
                role="PRIMARY",
                is_active=True,
            )
            ReviewerAssignment.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=self.reviewer2,
                role="SECONDARY",
                is_active=True,
            )

            # Submit decisions
            self.service.submit_reviewer_decision(
                result_id=str(result.id),
                reviewer=self.reviewer1,
                decision_data={"decision": decision1, "screening_stage": "SCREENING"},
                organisation=self.organisation,
            )

            self.service.submit_reviewer_decision(
                result_id=str(result.id),
                reviewer=self.reviewer2,
                decision_data={"decision": decision2, "screening_stage": "SCREENING"},
                organisation=self.organisation,
            )

            # Verify conflict type
            if decision1 != decision2:
                conflict = ConflictResolution.objects.get(result=result)
                self.assertEqual(
                    conflict.conflict_type,
                    expected_type,
                    f"Failed for {decision1} vs {decision2}",
                )

    @patch("apps.review_results.tasks.calculate_irr_task.delay")
    def test_irr_calculation_trigger(self, mock_irr_task):
        """Test IRR calculation triggers after sufficient dual screening decisions."""
        # Create 10 results to meet min_decisions_for_irr threshold
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i}",
                url=f"https://example.com/test{i}",
                snippet="Test",
            )

            # Create assignments for both reviewers
            ReviewerAssignment.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=self.reviewer1,
                role="PRIMARY",
                is_active=True,
            )
            ReviewerAssignment.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=self.reviewer2,
                role="SECONDARY",
                is_active=True,
            )

            # Submit decisions from both reviewers
            self.service.submit_reviewer_decision(
                result_id=str(result.id),
                reviewer=self.reviewer1,
                decision_data={"decision": "INCLUDE", "screening_stage": "SCREENING"},
                organisation=self.organisation,
            )

            # Second reviewer decision triggers IRR check
            self.service.submit_reviewer_decision(
                result_id=str(result.id),
                reviewer=self.reviewer2,
                decision_data={"decision": "INCLUDE", "screening_stage": "SCREENING"},
                organisation=self.organisation,
            )

        # Verify IRR task was triggered (at least once, after 10th pair)
        self.assertGreaterEqual(mock_irr_task.call_count, 1)

    def test_organisation_scoping_security(self):
        """Test organisation scoping prevents cross-organisation access."""
        org2 = Organisation.objects.create(name="Other Org", slug="other-org")

        decision_data = {"decision": "INCLUDE", "screening_stage": "SCREENING"}

        # Attempt to submit decision with wrong organisation
        with self.assertRaises(ValueError):
            self.service.submit_reviewer_decision(
                result_id=str(self.result.id),
                reviewer=self.reviewer1,
                decision_data=decision_data,
                organisation=org2,
            )

    def test_submit_decision_requires_organisation(self):
        """Test ValueError raised when organisation is None."""
        with self.assertRaises(ValueError) as context:
            self.service.submit_reviewer_decision(
                result_id=str(self.result.id),
                reviewer=self.reviewer1,
                decision_data={"decision": "INCLUDE"},
                organisation=None,  # type: ignore[arg-type]
            )

        self.assertIn("Organisation is required", str(context.exception))


class ConsensusCriteriaEvaluateDecisionsTest(DisablePersonalOrgSignalMixin, TestCase):
    """
    T10 service tests: _evaluate_decisions and detect_conflicts honour consensus_criteria.

    Truth table assertions:
    - N=3 MAJORITY: 2-of-3 INCLUDE → consensus (not conflict)
    - N=3 UNANIMOUS: 2-of-3 INCLUDE → conflict (not consensus)
    - N=4 MAJORITY: 2-of-4 INCLUDE+EXCLUDE → conflict (tie is not majority)
    - Partial completion: detect_conflicts skips result (completion gate)
    """

    def _make_session(self, n_reviewers, criteria):
        org = Organisation.objects.create(
            name=f"Org {n_reviewers} {criteria}",
            slug=f"org-{n_reviewers}-{criteria.lower()}",
        )
        owner = create_test_user(username_prefix=f"own_{n_reviewers}_{criteria[:3]}")
        OrganisationMembership.objects.create(
            user=owner,
            organisation=org,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )
        session = SearchSession.objects.create(
            title=f"Test {n_reviewers} {criteria}",
            owner=owner,
            status="under_review",
            organisation=org,
        )
        config = ReviewConfiguration.objects.create(
            session=session,
            min_reviewers_per_result=n_reviewers,
            consensus_criteria=criteria,
            version=1,
            organisation=org,
            created_by=owner,
        )
        session.current_configuration = config
        session.save()
        return session, org

    def _make_result_with_decisions(self, session, org, decisions_list):
        """Create a result with the given list of decision strings, returning result."""
        result = ProcessedResult.objects.create(
            session=session,
            title="Test Result",
            url=f"https://example.com/{session.id}/{len(decisions_list)}",
            snippet="test",
            min_reviewers_required=len(decisions_list),
            reviewers_completed=len(decisions_list),
        )
        for i, decision_str in enumerate(decisions_list):
            reviewer = create_test_user(username_prefix=f"rev_{session.id}_{i}")
            OrganisationMembership.objects.create(
                user=reviewer,
                organisation=org,
                role=OrganisationMembership.ROLE_REVIEWER,
            )
            assignment = ReviewerAssignment.objects.create(
                organisation=org,
                result=result,
                reviewer=reviewer,
                role="PRIMARY",
                is_active=True,
            )
            ReviewerDecision.objects.create(
                organisation=org,
                result=result,
                reviewer=reviewer,
                assignment=assignment,
                decision=decision_str,
                screening_stage="SCREENING",
            )
        return result

    def test_n3_majority_two_include_one_exclude_is_consensus(self):
        """2-of-3 INCLUDE under MAJORITY criteria → consensus_reached=True, no conflict."""
        session, org = self._make_session(3, "MAJORITY")
        result = self._make_result_with_decisions(
            session, org, ["INCLUDE", "INCLUDE", "EXCLUDE"]
        )
        service = ReviewCoordinationService()
        service._evaluate_decisions(result, "SCREENING")

        result.refresh_from_db()
        self.assertTrue(result.consensus_reached)
        self.assertEqual(ConflictResolution.objects.filter(result=result).count(), 0)

    def test_n3_unanimous_two_include_one_exclude_is_conflict(self):
        """2-of-3 INCLUDE under UNANIMOUS criteria → conflict, not consensus."""
        session, org = self._make_session(3, "UNANIMOUS")
        result = self._make_result_with_decisions(
            session, org, ["INCLUDE", "INCLUDE", "EXCLUDE"]
        )
        service = ReviewCoordinationService()
        service._evaluate_decisions(result, "SCREENING")

        result.refresh_from_db()
        self.assertFalse(result.consensus_reached)
        self.assertEqual(ConflictResolution.objects.filter(result=result).count(), 1)

    def test_n4_majority_tie_two_two_is_conflict(self):
        """2-of-4 INCLUDE, 2-of-4 EXCLUDE under MAJORITY → conflict (tie ≠ majority)."""
        session, org = self._make_session(4, "MAJORITY")
        result = self._make_result_with_decisions(
            session, org, ["INCLUDE", "INCLUDE", "EXCLUDE", "EXCLUDE"]
        )
        service = ReviewCoordinationService()
        service._evaluate_decisions(result, "SCREENING")

        result.refresh_from_db()
        self.assertFalse(result.consensus_reached)
        self.assertEqual(ConflictResolution.objects.filter(result=result).count(), 1)

    def test_detect_conflicts_completion_gate_skips_partial_result(self):
        """detect_conflicts must skip results where reviewers_completed < min_reviewers_required."""
        session, org = self._make_session(3, "MAJORITY")
        # Create result with only 2 of 3 required reviewers done
        result = ProcessedResult.objects.create(
            session=session,
            title="Partial Result",
            url="https://example.com/partial",
            snippet="test",
            min_reviewers_required=3,
            reviewers_completed=2,  # not yet complete
        )
        reviewer1 = create_test_user(username_prefix="gate_r1")
        reviewer2 = create_test_user(username_prefix="gate_r2")
        OrganisationMembership.objects.create(
            user=reviewer1, organisation=org, role="REVIEWER"
        )
        OrganisationMembership.objects.create(
            user=reviewer2, organisation=org, role="REVIEWER"
        )
        a1 = ReviewerAssignment.objects.create(
            organisation=org,
            result=result,
            reviewer=reviewer1,
            role="PRIMARY",
            is_active=True,
        )
        a2 = ReviewerAssignment.objects.create(
            organisation=org,
            result=result,
            reviewer=reviewer2,
            role="SECONDARY",
            is_active=True,
        )
        ReviewerDecision.objects.create(
            organisation=org,
            result=result,
            reviewer=reviewer1,
            assignment=a1,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        ReviewerDecision.objects.create(
            organisation=org,
            result=result,
            reviewer=reviewer2,
            assignment=a2,
            decision="EXCLUDE",
            screening_stage="SCREENING",
        )

        service = ReviewCoordinationService()
        conflicts = service.detect_conflicts(session)

        # No conflict should be created — panel incomplete
        self.assertEqual(len(conflicts), 0)
        self.assertEqual(ConflictResolution.objects.filter(result=result).count(), 0)
        result.refresh_from_db()
        self.assertFalse(result.consensus_reached)

    def test_detect_conflicts_n3_majority_consensus(self):
        """detect_conflicts marks consensus for 2-of-3 MAJORITY result."""
        session, org = self._make_session(3, "MAJORITY")
        result = self._make_result_with_decisions(
            session, org, ["INCLUDE", "INCLUDE", "EXCLUDE"]
        )
        # Update denormalized fields to match the 3 decisions
        result.min_reviewers_required = 3
        result.reviewers_completed = 3
        result.save(update_fields=["min_reviewers_required", "reviewers_completed"])

        service = ReviewCoordinationService()
        conflicts = service.detect_conflicts(session)

        self.assertEqual(len(conflicts), 0)
        result.refresh_from_db()
        self.assertTrue(result.consensus_reached)

    def test_detect_conflicts_n3_abstain_consensus_matches_live_evaluator(self):
        """Scanner and live evaluator must agree when one reviewer ABSTAINs.

        Regression for PR #205 CR (Codex P2 / CR Major): detect_conflicts'
        completion gate counts ALL submitted decisions (incl. ABSTAIN), so a
        2-INCLUDE + 1-ABSTAIN N=3 MAJORITY result is treated as a completed
        panel and reaches consensus, matching the live evaluator. Previously
        the gate used the non-abstain vote count and left this case as
        \"pending\".
        """
        session, org = self._make_session(3, "MAJORITY")
        result = self._make_result_with_decisions(
            session, org, ["INCLUDE", "INCLUDE", "ABSTAIN"]
        )
        # Panel of 3 completed (abstain counts toward completion); 2 non-abstain
        # INCLUDE votes meet the MAJORITY threshold floor(3/2)+1 = 2.
        result.min_reviewers_required = 3
        result.reviewers_completed = 3
        result.save(update_fields=["min_reviewers_required", "reviewers_completed"])

        service = ReviewCoordinationService()
        conflicts = service.detect_conflicts(session)

        self.assertEqual(len(conflicts), 0)
        result.refresh_from_db()
        self.assertTrue(result.consensus_reached)
