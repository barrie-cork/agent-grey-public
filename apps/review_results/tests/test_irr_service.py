"""
Tests for IRRService - Cohen's Kappa calculation for inter-rater reliability.

Focus areas:
- Cohen's Kappa calculation correctness (known test cases)
- Minimum common results threshold (< 2 returns None)
- ABSTAIN decision exclusion from calculations
- Cochrane threshold check (≥0.70)
- Percentage agreement calculation
- Organisation scoping security
"""

import math
import unittest

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import (
    ReviewerAssignment,
    ReviewerDecision,
    InterRaterReliability,
)
from apps.core.tests.utils import create_test_user
from apps.review_results.services.irr_service import (
    InterRaterReliabilityService,
    _cohens_kappa,
)

try:
    from sklearn.metrics import cohen_kappa_score

    _HAS_SKLEARN = True
except ImportError:  # scikit-learn removed in task 2-2
    _HAS_SKLEARN = False

User = get_user_model()


# (name, y1, y2, expected_kappa). Expected values are exact rationals that equal
# sklearn.metrics.cohen_kappa_score with default (unweighted) settings, since
# kappa = (po - pe) / (1 - pe) is algebraically identical to sklearn's formula.
# Used by the DQ-1 parity gate.
_KAPPA_FIXTURES = [
    (
        "eight_of_ten_agree",
        ["I", "I", "E", "E", "I", "E", "I", "E", "I", "E"],
        ["I", "I", "E", "E", "I", "E", "I", "E", "E", "I"],
        0.6,
    ),
    ("total_disagreement", ["I"] * 10, ["E"] * 10, 0.0),
    (
        "perfect_agreement_two_labels",
        ["I", "I", "E", "E", "I"],
        ["I", "I", "E", "E", "I"],
        1.0,
    ),
    # No variance: sklearn returns NaN here; _cohens_kappa returns 1.0 by design.
    ("single_label_both", ["I"] * 4, ["I"] * 4, 1.0),
    (
        "textbook_2x2_kappa_0_4",
        ["I"] * 20 + ["E"] * 15 + ["I"] * 5 + ["E"] * 10,
        ["I"] * 20 + ["E"] * 15 + ["E"] * 5 + ["I"] * 10,
        0.4,
    ),
    (
        "three_labels",
        ["I", "I", "E", "M", "I", "M"],
        ["I", "I", "E", "M", "E", "I"],
        11 / 23,
    ),
]


class CohensKappaParityTest(SimpleTestCase):
    """Parity tests for the stdlib _cohens_kappa helper (DQ-1).

    No database needed -- _cohens_kappa is a pure function over two label lists.
    """

    def test_cohens_kappa_parity_golden_values(self):
        """_cohens_kappa matches pre-computed exact (sklearn-equivalent) values."""
        for name, y1, y2, expected in _KAPPA_FIXTURES:
            with self.subTest(fixture=name):
                self.assertAlmostEqual(_cohens_kappa(y1, y2), expected, delta=1e-9)

    def test_cohens_kappa_empty_returns_zero(self):
        """Empty input returns 0.0 (no comparisons)."""
        self.assertEqual(_cohens_kappa([], []), 0.0)

    @unittest.skipUnless(
        _HAS_SKLEARN, "scikit-learn not installed (removed in task 2-2)"
    )
    def test_cohens_kappa_matches_sklearn(self):
        """Direct parity vs sklearn on every fixture -- the DQ-1 evidence.

        The only intentional divergence is the no-variance / single-shared-label
        case, where sklearn returns NaN and _cohens_kappa returns 1.0 (the service
        handles this via its `y1 == y2` short-circuit). Every finite sklearn value
        must match within 1e-9.
        """
        for name, y1, y2, _expected in _KAPPA_FIXTURES:
            with self.subTest(fixture=name):
                sk = float(cohen_kappa_score(y1, y2))
                ours = _cohens_kappa(y1, y2)
                if math.isnan(sk):
                    self.assertEqual(ours, 1.0)
                else:
                    self.assertAlmostEqual(ours, sk, delta=1e-9)


class IRRServiceTest(TestCase):
    """Test IRRService for Cohen's Kappa calculation."""

    def setUp(self):
        """Set up test data with organisation and reviewers."""
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        self.owner = create_test_user(username_prefix="owner")
        OrganisationMembership.objects.create(
            user=self.owner, organisation=self.organisation, role="LEAD_REVIEWER"
        )

        self.reviewer_a = create_test_user(username_prefix="reviewer_a")
        OrganisationMembership.objects.create(
            user=self.reviewer_a, organisation=self.organisation, role="REVIEWER"
        )

        self.reviewer_b = create_test_user(username_prefix="reviewer_b")
        OrganisationMembership.objects.create(
            user=self.reviewer_b, organisation=self.organisation, role="REVIEWER"
        )

        self.session = SearchSession.objects.create(
            title="Test IRR Session",
            owner=self.owner,
            status="under_review",
            organisation=self.organisation,
        )

        self.service = InterRaterReliabilityService()

    def _create_decision_pair(self, result, decision_a, decision_b):
        """Helper to create a pair of decisions for IRR testing."""
        # Create assignments
        assignment_a = ReviewerAssignment.objects.create(
            organisation=self.organisation,
            result=result,
            reviewer=self.reviewer_a,
            role="PRIMARY",
            is_active=True,
        )

        assignment_b = ReviewerAssignment.objects.create(
            organisation=self.organisation,
            result=result,
            reviewer=self.reviewer_b,
            role="SECONDARY",
            is_active=True,
        )

        # Create decisions
        ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=result,
            reviewer=self.reviewer_a,
            assignment=assignment_a,
            decision=decision_a,
            screening_stage="SCREENING",
            is_revote=False,  # Initial decision for IRR calculation
        )

        ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=result,
            reviewer=self.reviewer_b,
            assignment=assignment_b,
            decision=decision_b,
            screening_stage="SCREENING",
            is_revote=False,  # Initial decision for IRR calculation
        )

    def test_perfect_agreement_kappa_1_0(self):
        """Test perfect agreement yields Kappa = 1.0."""
        # Create 10 results where both reviewers always agree
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i}",
                url=f"https://example.com/test{i}",
                snippet="Test",
            )

            # Both reviewers INCLUDE
            decision = "INCLUDE" if i < 5 else "EXCLUDE"
            self._create_decision_pair(result, decision, decision)

        # Calculate IRR
        irr_result = self.service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        )

        self.assertIsNotNone(irr_result)
        assert irr_result is not None
        self.assertAlmostEqual(irr_result.cohens_kappa, 1.0, places=2)
        self.assertEqual(irr_result.percentage_agreement, 100.0)
        self.assertEqual(irr_result.total_comparisons, 10)

    def test_zero_agreement_kappa_low(self):
        """Test complete disagreement yields low/zero Kappa."""
        # Create 10 results where reviewers always disagree
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i}",
                url=f"https://example.com/test{i}",
                snippet="Test",
            )

            # Opposite decisions
            self._create_decision_pair(result, "INCLUDE", "EXCLUDE")

        irr_result = self.service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        )

        self.assertIsNotNone(irr_result)
        # Perfect disagreement yields Kappa = 0.0 (no agreement beyond chance)
        assert irr_result is not None
        self.assertAlmostEqual(irr_result.cohens_kappa, 0.0, places=2)
        self.assertEqual(irr_result.percentage_agreement, 0.0)

    def test_known_kappa_values(self):
        """Test Cohen's Kappa calculation against known values."""
        # Known test case: 8 agree, 2 disagree = 80% agreement
        # Expected Kappa ≈ 0.60 (moderate agreement)

        decisions = [
            ("INCLUDE", "INCLUDE"),  # Agree
            ("INCLUDE", "INCLUDE"),  # Agree
            ("EXCLUDE", "EXCLUDE"),  # Agree
            ("EXCLUDE", "EXCLUDE"),  # Agree
            ("INCLUDE", "INCLUDE"),  # Agree
            ("EXCLUDE", "EXCLUDE"),  # Agree
            ("INCLUDE", "INCLUDE"),  # Agree
            ("EXCLUDE", "EXCLUDE"),  # Agree
            ("INCLUDE", "EXCLUDE"),  # Disagree
            ("EXCLUDE", "INCLUDE"),  # Disagree
        ]

        for idx, (decision_a, decision_b) in enumerate(decisions):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {idx}",
                url=f"https://example.com/test{idx}",
                snippet="Test",
            )
            self._create_decision_pair(result, decision_a, decision_b)

        irr_result = self.service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        )

        self.assertIsNotNone(irr_result)
        assert irr_result is not None
        self.assertEqual(irr_result.percentage_agreement, 80.0)
        # Kappa should be moderate (0.4-0.8 range)
        self.assertGreater(irr_result.cohens_kappa, 0.4)
        self.assertLess(irr_result.cohens_kappa, 0.8)

    def test_minimum_common_results_threshold(self):
        """Test returns None when < 2 common results."""
        # Create only 1 result
        result = ProcessedResult.objects.create(
            session=self.session,
            title="Single Result",
            url="https://example.com/test",
            snippet="Test",
        )
        self._create_decision_pair(result, "INCLUDE", "INCLUDE")

        irr_result = self.service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        )

        # Service returns None when fewer than min_common_results (2)
        self.assertIsNone(irr_result)

    def test_abstain_decision_exclusion(self):
        """Test ABSTAIN decisions are excluded from Kappa calculation."""
        decisions = [
            ("INCLUDE", "INCLUDE"),  # Count
            ("EXCLUDE", "EXCLUDE"),  # Count
            ("ABSTAIN", "INCLUDE"),  # Skip
            ("INCLUDE", "ABSTAIN"),  # Skip
            ("EXCLUDE", "EXCLUDE"),  # Count
        ]

        for idx, (decision_a, decision_b) in enumerate(decisions):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {idx}",
                url=f"https://example.com/test{idx}",
                snippet="Test",
            )
            self._create_decision_pair(result, decision_a, decision_b)

        irr_result = self.service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        )

        # Should only count 3 results (excluding ABSTAIN)
        assert irr_result is not None
        self.assertEqual(irr_result.total_comparisons, 3)

    def test_cochrane_threshold_check(self):
        """Test meets_cochrane_threshold flag for Kappa ≥ 0.70."""
        # Create 20 results with balanced high agreement for reliable Kappa
        # 5 INCLUDE/INCLUDE, 5 EXCLUDE/EXCLUDE, 1 disagreement each way
        decisions = [
            ("INCLUDE", "INCLUDE"),  # 1-9: Agreement
            ("INCLUDE", "INCLUDE"),
            ("INCLUDE", "INCLUDE"),
            ("INCLUDE", "INCLUDE"),
            ("INCLUDE", "INCLUDE"),
            ("INCLUDE", "INCLUDE"),
            ("INCLUDE", "INCLUDE"),
            ("INCLUDE", "INCLUDE"),
            ("INCLUDE", "INCLUDE"),
            ("EXCLUDE", "EXCLUDE"),  # 10-18: Agreement
            ("EXCLUDE", "EXCLUDE"),
            ("EXCLUDE", "EXCLUDE"),
            ("EXCLUDE", "EXCLUDE"),
            ("EXCLUDE", "EXCLUDE"),
            ("EXCLUDE", "EXCLUDE"),
            ("EXCLUDE", "EXCLUDE"),
            ("EXCLUDE", "EXCLUDE"),
            ("EXCLUDE", "EXCLUDE"),
            ("INCLUDE", "EXCLUDE"),  # 19-20: Disagreement
            ("EXCLUDE", "INCLUDE"),
        ]

        for i, (decision_a, decision_b) in enumerate(decisions):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i}",
                url=f"https://example.com/test{i}",
                snippet="Test",
            )
            self._create_decision_pair(result, decision_a, decision_b)

        irr_result = self.service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        )

        # 90% agreement (18/20) with balanced categories should yield Kappa ≥ 0.70
        assert irr_result is not None
        self.assertGreaterEqual(irr_result.cohens_kappa, 0.70)
        # Verify percentage agreement
        self.assertEqual(irr_result.percentage_agreement, 90.0)

    def test_percentage_agreement_calculation(self):
        """Test percentage agreement calculation accuracy."""
        # 7 agree, 3 disagree = 70%
        decisions = [
            ("INCLUDE", "INCLUDE"),
            ("INCLUDE", "INCLUDE"),
            ("INCLUDE", "INCLUDE"),
            ("INCLUDE", "INCLUDE"),
            ("EXCLUDE", "EXCLUDE"),
            ("EXCLUDE", "EXCLUDE"),
            ("EXCLUDE", "EXCLUDE"),
            ("INCLUDE", "EXCLUDE"),
            ("INCLUDE", "EXCLUDE"),
            ("EXCLUDE", "INCLUDE"),
        ]

        for idx, (decision_a, decision_b) in enumerate(decisions):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {idx}",
                url=f"https://example.com/test{idx}",
                snippet="Test",
            )
            self._create_decision_pair(result, decision_a, decision_b)

        irr_result = self.service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        )

        assert irr_result is not None
        self.assertEqual(irr_result.percentage_agreement, 70.0)

    def test_organisation_scoping_security(self):
        """Test organisation scoping prevents cross-organisation IRR."""
        org2 = Organisation.objects.create(name="Other Org", slug="other-org")

        result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test",
        )
        self._create_decision_pair(result, "INCLUDE", "INCLUDE")

        # Attempt to calculate IRR with wrong organisation
        # Should return None due to no matching decisions for org2
        irr_result = self.service.calculate_cohens_kappa(
            organisation=org2,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        )
        self.assertIsNone(irr_result)  # No data for this org

    def test_calculate_irr_requires_organisation(self):
        """Test ValueError raised when organisation is None."""
        with self.assertRaises(ValueError) as context:
            self.service.calculate_cohens_kappa(
                organisation=None,  # type: ignore[arg-type]
                search_session=self.session,
                reviewer_a=self.reviewer_a,
                reviewer_b=self.reviewer_b,
            )

        self.assertIn("Organisation is required", str(context.exception))

    def test_irr_persistence_to_database(self):
        """Test IRR results are persisted to InterRaterReliability model."""
        # Create decisions with balanced categories (3 INCLUDE, 2 EXCLUDE, all agree)
        decisions = ["INCLUDE", "INCLUDE", "INCLUDE", "EXCLUDE", "EXCLUDE"]
        for i, decision in enumerate(decisions):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i}",
                url=f"https://example.com/test{i}",
                snippet="Test",
            )
            self._create_decision_pair(result, decision, decision)

        # Calculate IRR
        self.service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        )

        # Verify saved to database
        irr_record = InterRaterReliability.objects.filter(
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        ).first()

        self.assertIsNotNone(irr_record)
        self.assertAlmostEqual(irr_record.cohens_kappa, 1.0, places=2)
        self.assertEqual(irr_record.total_comparisons, 5)

    def test_get_per_reviewer_breakdown_returns_grouped_data(self):
        """Test per-reviewer breakdown groups IRR records by reviewer."""
        # Create a second reviewer pair
        reviewer_c = create_test_user(username_prefix="reviewer_c")
        OrganisationMembership.objects.create(
            user=reviewer_c, organisation=self.organisation, role="REVIEWER"
        )

        # Create decisions for reviewer_a vs reviewer_b
        for i in range(3):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Result AB {i}",
                url=f"https://example.com/ab{i}",
                snippet="Test",
            )
            self._create_decision_pair(result, "INCLUDE", "INCLUDE")

        # Calculate IRR for a-b pair
        self.service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=self.reviewer_b,
        )

        # Create decisions for reviewer_a vs reviewer_c
        for i in range(3):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Result AC {i}",
                url=f"https://example.com/ac{i}",
                snippet="Test",
            )
            assignment_a = ReviewerAssignment.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=self.reviewer_a,
                role="PRIMARY",
                is_active=True,
            )
            assignment_c = ReviewerAssignment.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=reviewer_c,
                role="SECONDARY",
                is_active=True,
            )
            ReviewerDecision.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=self.reviewer_a,
                assignment=assignment_a,
                decision="INCLUDE",
                screening_stage="SCREENING",
                is_revote=False,
            )
            ReviewerDecision.objects.create(
                organisation=self.organisation,
                result=result,
                reviewer=reviewer_c,
                assignment=assignment_c,
                decision="EXCLUDE",
                screening_stage="SCREENING",
                is_revote=False,
            )

        # Calculate IRR for a-c pair
        self.service.calculate_cohens_kappa(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer_a,
            reviewer_b=reviewer_c,
        )

        breakdown = self.service.get_per_reviewer_breakdown(
            organisation=self.organisation,
            search_session=self.session,
        )

        self.assertIsInstance(breakdown, list)
        # reviewer_a appears in both pairs, reviewer_b and reviewer_c each in one
        self.assertEqual(len(breakdown), 3)

        # Check structure of each entry
        for entry in breakdown:
            self.assertIn("reviewer_id", entry)
            self.assertIn("reviewer_name", entry)
            self.assertIn("reviewer_email", entry)
            self.assertIn("average_kappa", entry)
            self.assertIn("average_agreement", entry)
            self.assertIn("pairwise_comparisons", entry)
            self.assertIn("total_comparisons", entry)
            self.assertIn("meets_cochrane_average", entry)

    def test_get_per_reviewer_breakdown_empty_records(self):
        """Test per-reviewer breakdown returns empty list when no IRR records."""
        breakdown = self.service.get_per_reviewer_breakdown(
            organisation=self.organisation,
            search_session=self.session,
        )

        self.assertEqual(breakdown, [])

    def test_get_per_reviewer_breakdown_requires_organisation(self):
        """Test ValueError raised when organisation is None."""
        with self.assertRaises(ValueError):
            self.service.get_per_reviewer_breakdown(
                organisation=None,  # type: ignore[arg-type]
                search_session=self.session,
            )
