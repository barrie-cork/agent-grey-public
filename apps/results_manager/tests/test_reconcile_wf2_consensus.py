"""
Tests for management command reconcile_wf2_consensus (#204).

This command reconciles pre-#203 WF2 false-conflicts: results that carry a PENDING
ConflictResolution but actually have a real MAJORITY are flipped to consensus_reached=True
and the conflict is retired as RESOLVED.

Test trap (PMD #318): ProcessedResult.reviewers_completed is a DENORMALISED counter
incremented only by submit_reviewer_decision. ReviewerDecision rows seeded via
objects.create() do NOT increment it. Tests must set result.reviewers_completed
explicitly to match the number of non-abstain decisions, otherwise the
reviewers_completed >= min_reviewers_required gate silently fails.
"""

from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.models import ConflictResolution, ReviewerDecision


def _make_session(org, user, min_reviewers, consensus_criteria="MAJORITY"):
    """Create a SearchSession with a ReviewConfiguration."""
    session = SearchSession.objects.create(
        organisation=org,
        title=f"Reconcile WF2 test session (min={min_reviewers}, {consensus_criteria})",
        owner=user,
        status="ready_for_review",
    )
    config = ReviewConfiguration.objects.create(
        session=session,
        min_reviewers_per_result=min_reviewers,
        consensus_criteria=consensus_criteria,
        version=1,
        organisation=org,
        created_by=user,
    )
    session.current_configuration = config
    session.save(update_fields=["current_configuration"])
    return session


def _make_result(session, reviewers_completed=0, consensus_reached=False):
    """Create a ProcessedResult with denormalised counter set explicitly."""
    result = ProcessedResult.objects.create(
        session=session,
        title="Test result",
        url=f"https://example.com/test-{timezone.now().timestamp()}",
        snippet="Test snippet",
        review_mode="DUAL",
        min_reviewers_required=session.current_configuration.min_reviewers_per_result,
        reviewers_completed=reviewers_completed,
        consensus_reached=consensus_reached,
    )
    return result


def _make_decision(org, result, reviewer, decision):
    """Create a ReviewerDecision directly (no signal-driven counter increment)."""
    return ReviewerDecision.objects.create(
        organisation=org,
        result=result,
        reviewer=reviewer,
        decision=decision,
        exclusion_reason="not_relevant" if decision == "EXCLUDE" else "",
        confidence_level=2,
        screening_stage="SCREENING",
        is_blinded=False,
    )


def _make_pending_conflict(org, result, decisions):
    """Create a PENDING ConflictResolution linking the given decisions."""
    conflict = ConflictResolution.objects.create(
        organisation=org,
        result=result,
        conflict_type="INCLUDE_EXCLUDE",
        status=ConflictResolution.STATUS_PENDING,
    )
    conflict.conflicting_decisions.set(decisions)
    return conflict


class ReconcileWf2ConsensusTest(TestCase):
    """Tests for the reconcile_wf2_consensus management command."""

    def setUp(self):
        self.org = Organisation.objects.create(
            name="Reconcile WF2 Org", slug="reconcile-wf2-org"
        )
        self.user1 = create_test_user(
            username_prefix="rec_wf2_a", email="rec_wf2_a@test.com"
        )
        self.user2 = create_test_user(
            username_prefix="rec_wf2_b", email="rec_wf2_b@test.com"
        )
        self.user3 = create_test_user(
            username_prefix="rec_wf2_c", email="rec_wf2_c@test.com"
        )
        for user in [self.user1, self.user2, self.user3]:
            OrganisationMembership.objects.create(
                organisation=self.org, user=user, role="REVIEWER", is_active=True
            )

    # ------------------------------------------------------------------
    # Test 1: 2-of-3 INCLUDE MAJORITY false-conflict → flipped
    # ------------------------------------------------------------------
    def test_majority_false_conflict_is_flipped(self):
        """2-of-3 INCLUDE panel with PENDING conflict → consensus_reached=True, conflict RESOLVED."""
        session = _make_session(self.org, self.user1, min_reviewers=3)
        result = _make_result(session, reviewers_completed=3)

        d1 = _make_decision(self.org, result, self.user1, "INCLUDE")
        d2 = _make_decision(self.org, result, self.user2, "INCLUDE")
        d3 = _make_decision(self.org, result, self.user3, "EXCLUDE")
        conflict = _make_pending_conflict(self.org, result, [d1, d2, d3])

        call_command("reconcile_wf2_consensus")

        result.refresh_from_db()
        conflict.refresh_from_db()

        self.assertTrue(result.consensus_reached)
        self.assertEqual(conflict.status, ConflictResolution.STATUS_RESOLVED)
        self.assertEqual(conflict.resolution_method, "MAJORITY")
        self.assertIsNotNone(conflict.resolved_at)
        self.assertIsNotNone(conflict.final_decision)
        self.assertEqual(conflict.final_decision.decision, "INCLUDE")
        self.assertIn("#204", conflict.resolution_notes)

    # ------------------------------------------------------------------
    # Test 2: Genuine 1/1/1 three-way split → stays a conflict
    # ------------------------------------------------------------------
    def test_genuine_three_way_split_stays_as_conflict(self):
        """Three distinct decisions with no majority → conflict left untouched."""
        session = _make_session(self.org, self.user1, min_reviewers=3)
        result = _make_result(session, reviewers_completed=3)

        d1 = _make_decision(self.org, result, self.user1, "INCLUDE")
        d2 = _make_decision(self.org, result, self.user2, "EXCLUDE")
        # A MAYBE counts as a third distinct value, so no decision has >=2 votes
        # Use a second EXCLUDE to also test the 1 INCLUDE / 2 EXCLUDE → EXCLUDE majority
        # Actually for a true 3-way split we need 3 different values.
        # Django's ReviewerDecision.decision choices are INCLUDE / EXCLUDE / MAYBE / ABSTAIN.
        d3 = _make_decision(self.org, result, self.user3, "MAYBE")
        conflict = _make_pending_conflict(self.org, result, [d1, d2, d3])

        call_command("reconcile_wf2_consensus")

        result.refresh_from_db()
        conflict.refresh_from_db()

        self.assertFalse(result.consensus_reached)
        self.assertEqual(conflict.status, ConflictResolution.STATUS_PENDING)

    # ------------------------------------------------------------------
    # Test 3: UNANIMOUS-config session → left alone
    # ------------------------------------------------------------------
    def test_unanimous_config_session_is_skipped(self):
        """UNANIMOUS sessions were already correct pre-#203; must not be touched."""
        session = _make_session(
            self.org, self.user1, min_reviewers=2, consensus_criteria="UNANIMOUS"
        )
        result = _make_result(session, reviewers_completed=2)

        d1 = _make_decision(self.org, result, self.user1, "INCLUDE")
        d2 = _make_decision(self.org, result, self.user2, "EXCLUDE")
        conflict = _make_pending_conflict(self.org, result, [d1, d2])

        call_command("reconcile_wf2_consensus")

        result.refresh_from_db()
        conflict.refresh_from_db()

        self.assertFalse(result.consensus_reached)
        self.assertEqual(conflict.status, ConflictResolution.STATUS_PENDING)

    # ------------------------------------------------------------------
    # Test 4: Idempotency — second run is a no-op
    # ------------------------------------------------------------------
    def test_idempotent_second_run_is_noop(self):
        """Running the command twice produces the same result; second run flips nothing."""
        session = _make_session(self.org, self.user1, min_reviewers=2)
        result = _make_result(session, reviewers_completed=2)

        d1 = _make_decision(self.org, result, self.user1, "INCLUDE")
        d2 = _make_decision(self.org, result, self.user2, "INCLUDE")
        conflict = _make_pending_conflict(self.org, result, [d1, d2])

        call_command("reconcile_wf2_consensus")

        result.refresh_from_db()
        conflict.refresh_from_db()
        self.assertTrue(result.consensus_reached)
        self.assertEqual(conflict.status, ConflictResolution.STATUS_RESOLVED)

        # Second run: the conflict is now RESOLVED, not PENDING → qs matches nothing
        call_command("reconcile_wf2_consensus")

        result.refresh_from_db()
        conflict.refresh_from_db()
        self.assertTrue(result.consensus_reached)
        self.assertEqual(conflict.status, ConflictResolution.STATUS_RESOLVED)

    # ------------------------------------------------------------------
    # Test 5: --dry-run reports but writes nothing
    # ------------------------------------------------------------------
    def test_dry_run_writes_nothing(self):
        """--dry-run must not modify any rows."""
        session = _make_session(self.org, self.user1, min_reviewers=2)
        result = _make_result(session, reviewers_completed=2)

        d1 = _make_decision(self.org, result, self.user1, "INCLUDE")
        d2 = _make_decision(self.org, result, self.user2, "INCLUDE")
        conflict = _make_pending_conflict(self.org, result, [d1, d2])

        call_command("reconcile_wf2_consensus", dry_run=True)

        result.refresh_from_db()
        conflict.refresh_from_db()

        # Nothing should have changed
        self.assertFalse(result.consensus_reached)
        self.assertEqual(conflict.status, ConflictResolution.STATUS_PENDING)

    # ------------------------------------------------------------------
    # Test 6: ESCALATED conflict that WOULD be a majority → skipped
    # ------------------------------------------------------------------
    def test_escalated_conflict_not_flipped(self):
        """ESCALATED conflicts are human-active; the command must not touch them."""
        session = _make_session(self.org, self.user1, min_reviewers=2)
        result = _make_result(session, reviewers_completed=2)

        d1 = _make_decision(self.org, result, self.user1, "INCLUDE")
        d2 = _make_decision(self.org, result, self.user2, "INCLUDE")

        # Create an ESCALATED conflict (not PENDING)
        conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=result,
            conflict_type="INCLUDE_EXCLUDE",
            status=ConflictResolution.STATUS_ESCALATED,
        )
        conflict.conflicting_decisions.set([d1, d2])

        call_command("reconcile_wf2_consensus")

        result.refresh_from_db()
        conflict.refresh_from_db()

        # Majority would hold (2 INCLUDE), but ESCALATED → must not flip
        self.assertFalse(result.consensus_reached)
        self.assertEqual(conflict.status, ConflictResolution.STATUS_ESCALATED)

    # ------------------------------------------------------------------
    # Extra: session-id scoping
    # ------------------------------------------------------------------
    def test_session_id_scope(self):
        """--session-id limits the command to one session only."""
        session_a = _make_session(self.org, self.user1, min_reviewers=2)
        session_b = _make_session(self.org, self.user1, min_reviewers=2)

        result_a = _make_result(session_a, reviewers_completed=2)
        result_b = _make_result(session_b, reviewers_completed=2)

        for session, result in [(session_a, result_a), (session_b, result_b)]:
            d1 = _make_decision(self.org, result, self.user1, "INCLUDE")
            d2 = _make_decision(self.org, result, self.user2, "INCLUDE")
            _make_pending_conflict(self.org, result, [d1, d2])

        call_command("reconcile_wf2_consensus", session_id=str(session_a.pk))

        result_a.refresh_from_db()
        result_b.refresh_from_db()

        self.assertTrue(result_a.consensus_reached)  # in scope → flipped
        self.assertFalse(result_b.consensus_reached)  # out of scope → untouched

    # ------------------------------------------------------------------
    # Extra: WF1 result never touched
    # ------------------------------------------------------------------
    def test_wf1_result_not_touched(self):
        """WF1 sessions (min_reviewers_per_result=1) are excluded from the filter."""
        session = _make_session(self.org, self.user1, min_reviewers=1)
        result = _make_result(session, reviewers_completed=1)

        d1 = _make_decision(self.org, result, self.user1, "INCLUDE")
        conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=result,
            conflict_type="INCLUDE_EXCLUDE",
            status=ConflictResolution.STATUS_PENDING,
        )
        conflict.conflicting_decisions.set([d1])

        call_command("reconcile_wf2_consensus")

        result.refresh_from_db()
        conflict.refresh_from_db()

        self.assertFalse(result.consensus_reached)
        self.assertEqual(conflict.status, ConflictResolution.STATUS_PENDING)

    # ------------------------------------------------------------------
    # Extra: reconciliation must NOT email reviewers (CodeRabbit P1, #207)
    # ------------------------------------------------------------------
    def test_flip_does_not_send_consensus_email(self):
        """Retiring a conflict via .update() must not fire the consensus email signal.

        consensus_reached_handler (apps/review_results/signals.py) emails all
        reviewers on ConflictResolution post_save when status -> RESOLVED. This is a
        historical backfill; using QuerySet.update() bypasses post_save so no email
        goes out. Patch the email service the handler would call and assert it never
        fires.
        """
        session = _make_session(self.org, self.user1, min_reviewers=3)
        result = _make_result(session, reviewers_completed=3)

        d1 = _make_decision(self.org, result, self.user1, "INCLUDE")
        d2 = _make_decision(self.org, result, self.user2, "INCLUDE")
        d3 = _make_decision(self.org, result, self.user3, "EXCLUDE")
        _make_pending_conflict(self.org, result, [d1, d2, d3])

        with mock.patch(
            "apps.review_results.signals.EmailNotificationService"
        ) as mock_email_cls:
            call_command("reconcile_wf2_consensus")

        result.refresh_from_db()
        self.assertTrue(result.consensus_reached)  # the flip still happened
        mock_email_cls.return_value.send_consensus_notification.assert_not_called()
