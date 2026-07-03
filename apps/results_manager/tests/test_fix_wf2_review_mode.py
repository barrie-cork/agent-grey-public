"""
Regression tests for management command fix_wf2_review_mode (#192).

The command backfills WF2 ProcessedResults that were created before fix #178
and are therefore stuck at review_mode="SINGLE" / min_reviewers_required=1.
"""

from django.core.management import call_command
from django.test import TestCase

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.models import ReviewerDecision


def _make_session(org, user, min_reviewers):
    """Create a SearchSession with a ReviewConfiguration."""
    session = SearchSession.objects.create(
        organisation=org,
        title=f"Fix WF2 test session (min={min_reviewers})",
        owner=user,
        status="ready_for_review",
    )
    config = ReviewConfiguration.objects.create(
        session=session,
        min_reviewers_per_result=min_reviewers,
        version=1,
        organisation=org,
        created_by=user,
    )
    session.current_configuration = config
    session.save(update_fields=["current_configuration"])
    return session


def _make_result(
    session, review_mode="SINGLE", min_reviewers_required=1, consensus_reached=False
):
    return ProcessedResult.objects.create(
        session=session,
        title="Test result",
        url="https://example.com/test",
        snippet="Test snippet",
        review_mode=review_mode,
        min_reviewers_required=min_reviewers_required,
        consensus_reached=consensus_reached,
    )


class FixWf2ReviewModeCommandTest(TestCase):
    """Tests for the fix_wf2_review_mode management command."""

    def setUp(self):
        self.org = Organisation.objects.create(
            name="Fix WF2 Test Org", slug="fix-wf2-test-org"
        )
        self.user = create_test_user(
            username_prefix="fix_wf2", email="fix_wf2@test.com"
        )
        OrganisationMembership.objects.create(
            organisation=self.org,
            user=self.user,
            role="RESEARCHER",
            is_active=True,
        )

    def test_wf2_result_gets_correct_mode_and_consensus_reset(self):
        """WF2 result stuck at SINGLE/1 is fixed to DUAL/2; false consensus is reset."""
        session = _make_session(self.org, self.user, min_reviewers=2)
        result = _make_result(
            session,
            review_mode="SINGLE",
            min_reviewers_required=1,
            consensus_reached=True,
        )
        # 1 decision → was falsely marked consensus_reached=True
        ReviewerDecision.objects.create(
            organisation=self.org,
            result=result,
            reviewer=self.user,
            decision="INCLUDE",
            confidence_level=2,
            screening_stage="SCREENING",
            is_blinded=False,
        )

        call_command("fix_wf2_review_mode")

        result.refresh_from_db()
        self.assertEqual(result.review_mode, "DUAL")
        self.assertEqual(result.min_reviewers_required, 2)
        self.assertFalse(result.consensus_reached)

    def test_wf1_result_is_unchanged(self):
        """WF1 session results are never touched."""
        session = _make_session(self.org, self.user, min_reviewers=1)
        result = _make_result(
            session,
            review_mode="SINGLE",
            min_reviewers_required=1,
            consensus_reached=False,
        )

        call_command("fix_wf2_review_mode")

        result.refresh_from_db()
        self.assertEqual(result.review_mode, "SINGLE")
        self.assertEqual(result.min_reviewers_required, 1)
        self.assertFalse(result.consensus_reached)

    def test_dry_run_writes_nothing(self):
        """--dry-run must not modify any rows."""
        session = _make_session(self.org, self.user, min_reviewers=2)
        result = _make_result(
            session,
            review_mode="SINGLE",
            min_reviewers_required=1,
            consensus_reached=True,
        )

        call_command("fix_wf2_review_mode", dry_run=True)

        result.refresh_from_db()
        self.assertEqual(result.review_mode, "SINGLE")
        self.assertEqual(result.min_reviewers_required, 1)
        self.assertTrue(result.consensus_reached)

    def test_consensus_not_reset_when_two_decisions_exist(self):
        """consensus_reached is not reset when 2+ non-abstain decisions exist."""
        session = _make_session(self.org, self.user, min_reviewers=2)
        result = _make_result(
            session,
            review_mode="SINGLE",
            min_reviewers_required=1,
            consensus_reached=True,
        )
        user2 = create_test_user(
            username_prefix="fix_wf2_b", email="fix_wf2_b@test.com"
        )
        # 2 agreeing decisions — this consensus IS real
        for reviewer in [self.user, user2]:
            ReviewerDecision.objects.create(
                organisation=self.org,
                result=result,
                reviewer=reviewer,
                decision="INCLUDE",
                confidence_level=2,
                screening_stage="SCREENING",
                is_blinded=False,
            )

        call_command("fix_wf2_review_mode")

        result.refresh_from_db()
        self.assertEqual(result.review_mode, "DUAL")
        self.assertEqual(result.min_reviewers_required, 2)
        # consensus_reached must remain True — two reviewers agreed
        self.assertTrue(result.consensus_reached)

    def test_consensus_reset_when_two_decisions_conflict(self):
        """consensus_reached IS reset when 2 non-abstain decisions disagree.

        Regression for the #201 CodeRabbit P1: a count-only guard would treat
        a falsely-set consensus on conflicting decisions as real. Real consensus
        requires unanimity, so a disagreeing pair must be reset to pending.
        """
        session = _make_session(self.org, self.user, min_reviewers=2)
        result = _make_result(
            session,
            review_mode="SINGLE",
            min_reviewers_required=1,
            consensus_reached=True,
        )
        user2 = create_test_user(
            username_prefix="fix_wf2_c", email="fix_wf2_c@test.com"
        )
        # 2 disagreeing decisions — this consensus is NOT real
        for reviewer, decision in [(self.user, "INCLUDE"), (user2, "EXCLUDE")]:
            ReviewerDecision.objects.create(
                organisation=self.org,
                result=result,
                reviewer=reviewer,
                decision=decision,
                exclusion_reason="not_relevant" if decision == "EXCLUDE" else "",
                confidence_level=2,
                screening_stage="SCREENING",
                is_blinded=False,
            )

        call_command("fix_wf2_review_mode")

        result.refresh_from_db()
        self.assertEqual(result.review_mode, "DUAL")
        self.assertEqual(result.min_reviewers_required, 2)
        # consensus_reached must be reset — the two reviewers disagreed
        self.assertFalse(result.consensus_reached)

    def test_consensus_threshold_scales_with_min_reviewers(self):
        """For a TRIPLE session, consensus needs >= 3 unanimous decisions.

        Guards against a 2-hardcoded threshold: a 3-reviewer session where only
        2 reviewers have (agreeing) decisions is still in-progress, so a stale
        consensus flag must be reset; a full unanimous trio is preserved.
        """
        session = _make_session(self.org, self.user, min_reviewers=3)
        user2 = create_test_user(
            username_prefix="fix_wf2_d", email="fix_wf2_d@test.com"
        )
        user3 = create_test_user(
            username_prefix="fix_wf2_e", email="fix_wf2_e@test.com"
        )

        # Result A: only 2 of 3 reviewers decided (agreeing) -> not real yet -> reset
        partial = _make_result(
            session,
            review_mode="SINGLE",
            min_reviewers_required=1,
            consensus_reached=True,
        )
        for reviewer in [self.user, user2]:
            ReviewerDecision.objects.create(
                organisation=self.org,
                result=partial,
                reviewer=reviewer,
                decision="INCLUDE",
                confidence_level=2,
                screening_stage="SCREENING",
                is_blinded=False,
            )

        # Result B: full unanimous trio -> real consensus -> preserved
        full = _make_result(
            session,
            review_mode="SINGLE",
            min_reviewers_required=1,
            consensus_reached=True,
        )
        for reviewer in [self.user, user2, user3]:
            ReviewerDecision.objects.create(
                organisation=self.org,
                result=full,
                reviewer=reviewer,
                decision="INCLUDE",
                confidence_level=2,
                screening_stage="SCREENING",
                is_blinded=False,
            )

        call_command("fix_wf2_review_mode")

        partial.refresh_from_db()
        full.refresh_from_db()
        self.assertEqual(partial.review_mode, "TRIPLE")
        self.assertEqual(partial.min_reviewers_required, 3)
        self.assertFalse(partial.consensus_reached)  # 2 of 3 -> reset
        self.assertEqual(full.min_reviewers_required, 3)
        self.assertTrue(full.consensus_reached)  # 3 of 3 unanimous -> kept

    def test_session_id_scope(self):
        """--session-id limits the command to one session only."""
        session_a = _make_session(self.org, self.user, min_reviewers=2)
        session_b = _make_session(self.org, self.user, min_reviewers=2)
        result_a = _make_result(
            session_a, review_mode="SINGLE", min_reviewers_required=1
        )
        result_b = _make_result(
            session_b, review_mode="SINGLE", min_reviewers_required=1
        )

        call_command("fix_wf2_review_mode", session_id=str(session_a.pk))

        result_a.refresh_from_db()
        result_b.refresh_from_db()
        self.assertEqual(result_a.review_mode, "DUAL")
        # session_b was not in scope
        self.assertEqual(result_b.review_mode, "SINGLE")

    def test_idempotent_second_run_is_noop(self):
        """Running the command twice leaves rows unchanged after the first run."""
        session = _make_session(self.org, self.user, min_reviewers=2)
        _make_result(session, review_mode="SINGLE", min_reviewers_required=1)

        call_command("fix_wf2_review_mode")
        call_command("fix_wf2_review_mode")

        results = list(ProcessedResult.objects.filter(session=session))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].review_mode, "DUAL")
