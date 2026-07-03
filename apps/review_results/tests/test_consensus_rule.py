"""
Pure unit tests for decide_consensus / consensus_value helpers.

No database required — these tests exercise the helper maths only.

Truth table (§2 of PRPs/plans/203-wf2-consensus.plan.md):
  N=2 MAJORITY  II  → consensus
  N=2 MAJORITY  IE  → conflict
  N=3 MAJORITY  IIE → consensus
  N=3 MAJORITY  IEM → conflict
  N=4 MAJORITY  IIIE → consensus
  N=4 MAJORITY  IIEE → conflict (tie is not majority)
  N=2 UNANIMOUS II  → consensus
  N=2 UNANIMOUS IE  → conflict
  N=3 UNANIMOUS IIE → conflict (2/3 is not unanimous)
  any            reviewers_completed < min_req → pending
  any            all-abstain → pending (empty decision_values)
"""

from django.test import SimpleTestCase

from apps.review_results.services.review_coordination_service import (
    consensus_value,
    decide_consensus,
)


class TestDecideConsensus(SimpleTestCase):
    # --- Completion gate ---

    def test_pending_when_reviewers_incomplete(self):
        self.assertEqual(
            decide_consensus(["INCLUDE"], "MAJORITY", 2, 1),
            "pending",
        )

    def test_pending_when_all_abstained(self):
        # reviewers_completed == min_req but no non-abstain votes
        self.assertEqual(
            decide_consensus([], "MAJORITY", 2, 2),
            "pending",
        )

    def test_pending_all_abstain_unanimous(self):
        self.assertEqual(
            decide_consensus([], "UNANIMOUS", 3, 3),
            "pending",
        )

    # --- N=2 MAJORITY ---

    def test_n2_majority_both_include_consensus(self):
        self.assertEqual(
            decide_consensus(["INCLUDE", "INCLUDE"], "MAJORITY", 2, 2),
            "consensus",
        )

    def test_n2_majority_include_exclude_conflict(self):
        self.assertEqual(
            decide_consensus(["INCLUDE", "EXCLUDE"], "MAJORITY", 2, 2),
            "conflict",
        )

    def test_n2_majority_both_exclude_consensus(self):
        self.assertEqual(
            decide_consensus(["EXCLUDE", "EXCLUDE"], "MAJORITY", 2, 2),
            "consensus",
        )

    # --- N=3 MAJORITY ---

    def test_n3_majority_two_include_one_exclude_consensus(self):
        # 2 >= floor(3/2)+1 = 2 → consensus
        self.assertEqual(
            decide_consensus(["INCLUDE", "INCLUDE", "EXCLUDE"], "MAJORITY", 3, 3),
            "consensus",
        )

    def test_n3_majority_split_three_way_conflict(self):
        # max count = 1 < 2 → conflict
        self.assertEqual(
            decide_consensus(["INCLUDE", "EXCLUDE", "MAYBE"], "MAJORITY", 3, 3),
            "conflict",
        )

    def test_n3_majority_partial_pending(self):
        self.assertEqual(
            decide_consensus(["INCLUDE", "INCLUDE"], "MAJORITY", 3, 2),
            "pending",
        )

    # --- N=4 MAJORITY ---

    def test_n4_majority_three_include_one_exclude_consensus(self):
        # 3 >= floor(4/2)+1 = 3 → consensus
        self.assertEqual(
            decide_consensus(
                ["INCLUDE", "INCLUDE", "INCLUDE", "EXCLUDE"], "MAJORITY", 4, 4
            ),
            "consensus",
        )

    def test_n4_majority_tie_two_two_conflict(self):
        # 2 < floor(4/2)+1 = 3 → conflict (tie is NOT majority)
        self.assertEqual(
            decide_consensus(
                ["INCLUDE", "INCLUDE", "EXCLUDE", "EXCLUDE"], "MAJORITY", 4, 4
            ),
            "conflict",
        )

    def test_n4_majority_partial_pending(self):
        self.assertEqual(
            decide_consensus(["INCLUDE", "INCLUDE", "INCLUDE"], "MAJORITY", 4, 3),
            "pending",
        )

    # --- N=2 UNANIMOUS ---

    def test_n2_unanimous_both_include_consensus(self):
        self.assertEqual(
            decide_consensus(["INCLUDE", "INCLUDE"], "UNANIMOUS", 2, 2),
            "consensus",
        )

    def test_n2_unanimous_include_exclude_conflict(self):
        self.assertEqual(
            decide_consensus(["INCLUDE", "EXCLUDE"], "UNANIMOUS", 2, 2),
            "conflict",
        )

    # --- N=3 UNANIMOUS ---

    def test_n3_unanimous_two_include_one_exclude_conflict(self):
        # 2-of-3 INCLUDE is not unanimous
        self.assertEqual(
            decide_consensus(["INCLUDE", "INCLUDE", "EXCLUDE"], "UNANIMOUS", 3, 3),
            "conflict",
        )

    def test_n3_unanimous_all_include_consensus(self):
        self.assertEqual(
            decide_consensus(["INCLUDE", "INCLUDE", "INCLUDE"], "UNANIMOUS", 3, 3),
            "consensus",
        )

    def test_n3_unanimous_partial_pending(self):
        self.assertEqual(
            decide_consensus(["INCLUDE", "INCLUDE"], "UNANIMOUS", 3, 2),
            "pending",
        )


class TestConsensusValue(SimpleTestCase):
    def test_returns_majority_winner(self):
        self.assertEqual(
            consensus_value(["INCLUDE", "INCLUDE", "EXCLUDE"], "MAJORITY", 3),
            "INCLUDE",
        )

    def test_returns_none_on_conflict(self):
        # N=2 MAJORITY: 1 INCLUDE vs 1 EXCLUDE — no majority
        self.assertIsNone(
            consensus_value(["INCLUDE", "EXCLUDE"], "MAJORITY", 2),
        )

    def test_returns_none_on_tie_n4(self):
        # N=4 MAJORITY: 2/4 is a tie, not majority
        self.assertIsNone(
            consensus_value(
                ["INCLUDE", "INCLUDE", "EXCLUDE", "EXCLUDE"], "MAJORITY", 4
            ),
        )

    def test_returns_exclude_unanimous(self):
        self.assertEqual(
            consensus_value(["EXCLUDE", "EXCLUDE"], "UNANIMOUS", 2),
            "EXCLUDE",
        )

    def test_returns_none_when_unanimous_fails(self):
        self.assertIsNone(
            consensus_value(["INCLUDE", "INCLUDE", "EXCLUDE"], "UNANIMOUS", 3),
        )

    def test_returns_none_on_empty_decisions(self):
        self.assertIsNone(
            consensus_value([], "MAJORITY", 2),
        )

    def test_returns_maybe_majority(self):
        self.assertEqual(
            consensus_value(["MAYBE", "MAYBE", "INCLUDE"], "MAJORITY", 3),
            "MAYBE",
        )
