"""WF2 dual-screening consensus + discussion edge-case coverage.

Fills the zero-coverage gaps from the 2026-06-20 recon sweep. Several originally
listed gaps were already covered by existing suites and are NOT duplicated here:
  - gap #2 (UNANIMOUS vs MAJORITY for [I,I,E]):
        test_review_coordination_service.test_n3_unanimous_* / test_n3_majority_*
  - gap #7 (SLA reminders actually firing): test_sla_task.py (50%/90% + dedup)

This file adds only the genuinely-uncovered cases:
  - gap #1: Maybe/Maybe agreement reaches consensus (only Include/Maybe was tested)
  - gap #3: N=4 [I,I,I,E] MAJORITY reaches consensus (only the 2-2 tie was tested)
  - gap #4: ReviewerDecision immutability raise, version increment, revote constraint
  - gap #5: in-discussion straw polls (ProposeDiscussionVote / RespondToDiscussionVote)
  - gap #6: LEAD_ARBITRATION / DESIGNATED_ARBITRATOR resolution methods (service)
  - gap #8: resolving a conflict on a filtered/duplicate result (characterization)
  - F1/PMD #282: can_resolve permission flag mirrors the resolve POST's perm check
"""

import json

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.tests.utils import (
    DisablePersonalOrgSignalMixin,
    create_test_user,
    make_session_participant,
)
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.models import (
    ConflictComment,
    ConflictResolution,
    InDiscussionVote,
    InDiscussionVoteResponse,
    ReviewerDecision,
)
from apps.review_results.services.review_coordination_service import (
    ReviewCoordinationService,
)

User = get_user_model()


def _make_wf2_session(org, owner, criteria="MAJORITY", min_reviewers=2):
    """Create a WF2 session + current_configuration. Returns the session."""
    session = SearchSession.objects.create(
        title="Edge Case Session",
        owner=owner,
        status="under_review",
        organisation=org,
    )
    config = ReviewConfiguration.objects.create(
        session=session,
        version=1,
        min_reviewers_per_result=min_reviewers,
        consensus_criteria=criteria,
        blind_screening_enforced=True,
        conflict_resolution_method="CONSENSUS",
        organisation=org,
        created_by=owner,
    )
    session.current_configuration = config
    session.save(update_fields=["current_configuration"])
    return session


# ---------------------------------------------------------------------------
# Gap #1 + #3 — consensus arithmetic for the as-yet-untested combinations
# ---------------------------------------------------------------------------


class ConsensusEdgeCaseTest(DisablePersonalOrgSignalMixin, TestCase):
    """_evaluate_decisions for combinations not covered by the existing suite."""

    def setUp(self):
        self.org = Organisation.objects.create(
            name="Consensus Org", slug="consensus-edge"
        )
        self.owner = create_test_user(username_prefix="cons_owner")
        OrganisationMembership.objects.create(
            user=self.owner, organisation=self.org, role="LEAD_REVIEWER"
        )
        self.service = ReviewCoordinationService()

    def _result_with(self, session, decisions):
        """Create a result + N decisions and run _evaluate_decisions on it."""
        result = ProcessedResult.objects.create(
            session=session,
            title="R",
            url=f"https://example.com/{session.id}/{len(decisions)}",
            snippet="s",
            min_reviewers_required=len(decisions),
            reviewers_completed=len(decisions),
        )
        for i, value in enumerate(decisions):
            reviewer = create_test_user(username_prefix=f"r_{session.id}_{i}")
            OrganisationMembership.objects.create(
                user=reviewer, organisation=self.org, role="REVIEWER"
            )
            ReviewerDecision.objects.create(
                organisation=self.org,
                result=result,
                reviewer=reviewer,
                decision=value,
                screening_stage="SCREENING",
            )
        self.service._evaluate_decisions(result, "SCREENING")
        result.refresh_from_db()
        return result

    def test_maybe_maybe_agreement_is_consensus(self):
        """Gap #1: two MAYBE votes agree → consensus, no conflict."""
        session = _make_wf2_session(self.org, self.owner, min_reviewers=2)
        result = self._result_with(session, ["MAYBE", "MAYBE"])
        self.assertTrue(result.consensus_reached)
        self.assertEqual(ConflictResolution.objects.filter(result=result).count(), 0)

    def test_n4_majority_three_one_is_consensus(self):
        """Gap #3: N=4 [I,I,I,E] under MAJORITY → consensus (3 >= floor(4/2)+1)."""
        session = _make_wf2_session(self.org, self.owner, min_reviewers=4)
        result = self._result_with(
            session, ["INCLUDE", "INCLUDE", "INCLUDE", "EXCLUDE"]
        )
        self.assertTrue(result.consensus_reached)
        self.assertEqual(ConflictResolution.objects.filter(result=result).count(), 0)


# ---------------------------------------------------------------------------
# Gap #4 — ReviewerDecision immutability / version / revote constraint
# ---------------------------------------------------------------------------


class ReviewerDecisionImmutabilityTest(DisablePersonalOrgSignalMixin, TestCase):
    """The save() override (models.py:502) enforces an append-only audit trail."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Immut Org", slug="immut-edge")
        self.owner = create_test_user(username_prefix="immut_owner")
        OrganisationMembership.objects.create(
            user=self.owner, organisation=self.org, role="LEAD_REVIEWER"
        )
        self.reviewer = create_test_user(username_prefix="immut_rev")
        OrganisationMembership.objects.create(
            user=self.reviewer, organisation=self.org, role="REVIEWER"
        )
        self.session = _make_wf2_session(self.org, self.owner)
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="R",
            url="https://example.com/immut",
            snippet="s",
        )

    def _decision(self, **kwargs):
        return ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.reviewer,
            decision=kwargs.pop("decision", "INCLUDE"),
            screening_stage="SCREENING",
            **kwargs,
        )

    def test_update_without_allow_update_raises(self):
        """Re-saving an existing decision without allow_update raises ValueError."""
        decision = self._decision()
        decision.notes = "tampered"
        with self.assertRaises(ValueError):
            decision.save()

    def test_allow_update_increments_version(self):
        """save(allow_update=True) is permitted and bumps the version counter."""
        decision = self._decision()
        decision.refresh_from_db()
        before = decision.version
        decision.notes = "corrected"
        decision.save(allow_update=True)
        decision.refresh_from_db()
        self.assertEqual(decision.version, before + 1)

    def test_revote_allowed_but_second_initial_blocked(self):
        """Unique (result,reviewer,stage,is_revote) allows 1 initial + 1 revote only."""
        self._decision(is_revote=False)
        # A revote (is_revote=True) for the same reviewer/result/stage is allowed.
        revote = self._decision(decision="EXCLUDE", is_revote=True)
        self.assertTrue(revote.is_revote)
        # A second *initial* decision violates the unique constraint.
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                self._decision(is_revote=False)


# ---------------------------------------------------------------------------
# Gap #6 + #8 — resolution methods and resolving on a filtered result
# ---------------------------------------------------------------------------


class ResolveConflictServiceTest(DisablePersonalOrgSignalMixin, TestCase):
    """ReviewCoordinationService.resolve_conflict beyond the CONSENSUS happy path."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Resolve Org", slug="resolve-edge")
        self.owner = create_test_user(username_prefix="res_owner")
        OrganisationMembership.objects.create(
            user=self.owner, organisation=self.org, role="SENIOR_RESEARCHER"
        )
        self.r1 = create_test_user(username_prefix="res_r1")
        self.r2 = create_test_user(username_prefix="res_r2")
        for u in (self.r1, self.r2):
            OrganisationMembership.objects.create(
                user=u, organisation=self.org, role="REVIEWER"
            )
        self.session = _make_wf2_session(self.org, self.owner)
        self.service = ReviewCoordinationService()

    def _conflict(self, processing_status="success"):
        result = ProcessedResult.objects.create(
            session=self.session,
            title="R",
            url=f"https://example.com/{processing_status}",
            snippet="s",
            processing_status=processing_status,
            min_reviewers_required=2,
            reviewers_completed=2,
        )
        d1 = ReviewerDecision.objects.create(
            organisation=self.org, result=result, reviewer=self.r1, decision="INCLUDE"
        )
        d2 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=result,
            reviewer=self.r2,
            decision="EXCLUDE",
            exclusion_reason="not_relevant",
        )
        conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )
        conflict.conflicting_decisions.set([d1, d2])
        return conflict

    def test_resolve_with_lead_arbitration_method(self):
        """Gap #6: service stores the config-driven LEAD_ARBITRATION method.

        NOTE: 'LEAD_ARBITRATION' is a ReviewConfiguration.conflict_resolution_method
        value, not one of ConflictResolution.RESOLUTION_METHOD_CHOICES — the two
        choice sets diverge. It persists because Django does not enforce choices
        at the DB layer (recorded as a low-severity domain inconsistency).
        """
        conflict = self._conflict()
        resolved = self.service.resolve_conflict(
            conflict_id=str(conflict.id),
            resolver=self.owner,
            resolution_data={
                "decision": "INCLUDE",
                "resolution_method": "LEAD_ARBITRATION",
                "resolution_notes": "Lead decides include",
            },
            organisation=self.org,
        )
        self.assertEqual(resolved.status, "RESOLVED")
        self.assertEqual(resolved.resolution_method, "LEAD_ARBITRATION")
        self.assertIsNotNone(resolved.final_decision)
        self.assertEqual(resolved.final_decision.decision, "INCLUDE")
        resolved.result.refresh_from_db()
        self.assertTrue(resolved.result.consensus_reached)

    def test_resolve_with_designated_arbitrator_method(self):
        """Gap #6: DESIGNATED_ARBITRATOR resolution persists with an EXCLUDE outcome."""
        conflict = self._conflict()
        resolved = self.service.resolve_conflict(
            conflict_id=str(conflict.id),
            resolver=self.owner,
            resolution_data={
                "decision": "EXCLUDE",
                "resolution_method": "DESIGNATED_ARBITRATOR",
                "resolution_notes": "Arbitrator excludes",
                "exclusion_reason": "out_of_scope",
            },
            organisation=self.org,
        )
        self.assertEqual(resolved.resolution_method, "DESIGNATED_ARBITRATOR")
        self.assertEqual(resolved.final_decision.decision, "EXCLUDE")

    def test_resolve_on_filtered_result_succeeds(self):
        """Gap #8 (characterization): resolve_conflict does NOT guard on
        processing_status. A filtered/duplicate result still resolves.

        Not reachable in normal flow — filtering happens during processing,
        before review, and the review UI excludes filtered results — so this
        pins current behaviour rather than reporting a live bug.
        """
        conflict = self._conflict(processing_status="filtered")
        resolved = self.service.resolve_conflict(
            conflict_id=str(conflict.id),
            resolver=self.owner,
            resolution_data={
                "decision": "INCLUDE",
                "resolution_method": "CONSENSUS",
                "resolution_notes": "resolved despite filtered status",
            },
            organisation=self.org,
        )
        self.assertEqual(resolved.status, "RESOLVED")
        resolved.result.refresh_from_db()
        self.assertEqual(resolved.result.processing_status, "filtered")


# ---------------------------------------------------------------------------
# Gap #5 — in-discussion straw polls (zero prior coverage)
# ---------------------------------------------------------------------------


class StrawPollAPITest(DisablePersonalOrgSignalMixin, TestCase):
    """ProposeDiscussionVoteView / RespondToDiscussionVoteView."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Straw Org", slug="straw-edge")
        self.r1 = create_test_user(username_prefix="straw_r1")
        self.r2 = create_test_user(username_prefix="straw_r2")
        self.outsider = create_test_user(username_prefix="straw_out")
        for u in (self.r1, self.r2, self.outsider):
            OrganisationMembership.objects.create(
                user=u, organisation=self.org, role="REVIEWER", is_active=True
            )
        self.session = _make_wf2_session(self.org, self.r1)
        # r1 owns the session; r2 and outsider gain access as accepted reviewers
        # (org membership alone no longer grants session access -- GH #230).
        make_session_participant(self.session, self.r2)
        make_session_participant(self.session, self.outsider)
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="R",
            url="https://example.com/straw",
            snippet="s",
        )
        self.d1 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.r1,
            decision="INCLUDE",
        )
        self.d2 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.r2,
            decision="EXCLUDE",
            exclusion_reason="not_relevant",
        )
        self.conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )
        self.conflict.conflicting_decisions.set([self.d1, self.d2])
        self.client = Client()

    def _propose_url(self):
        return reverse(
            "review_results_api:propose-discussion-vote", args=[self.conflict.id]
        )

    def _respond_url(self, vote_id):
        return reverse(
            "review_results_api:respond-discussion-vote",
            args=[self.conflict.id, vote_id],
        )

    def _make_vote(self):
        """Create a straw poll directly (for response-path tests)."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.r1,
            content="**Straw Poll Proposed**",
            is_system_message=True,
        )
        return InDiscussionVote.objects.create(
            conflict=self.conflict,
            initiating_comment=comment,
            proposed_by=self.r1,
            rationale="check alignment",
        )

    def test_propose_creates_vote_and_flips_status(self):
        """A conflicting reviewer proposes → 201, vote + system comment, IN_DISCUSSION."""
        self.client.force_login(self.r1)
        resp = self.client.post(
            self._propose_url(),
            data=json.dumps({"rationale": "Let us gauge alignment"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            InDiscussionVote.objects.filter(conflict=self.conflict).count(), 1
        )
        self.assertTrue(
            ConflictComment.objects.filter(
                conflict=self.conflict, is_system_message=True
            ).exists()
        )
        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "IN_DISCUSSION")

    def test_propose_requires_rationale(self):
        """Empty rationale → 400."""
        self.client.force_login(self.r1)
        resp = self.client.post(
            self._propose_url(),
            data=json.dumps({"rationale": "   "}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_non_conflicting_reviewer_cannot_propose(self):
        """An org member who is not a conflicting reviewer → 403."""
        self.client.force_login(self.outsider)
        resp = self.client.post(
            self._propose_url(),
            data=json.dumps({"rationale": "I should not be allowed"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_respond_records_vote(self):
        """A conflicting reviewer responds → 201 and a response row is created."""
        vote = self._make_vote()
        self.client.force_login(self.r2)
        resp = self.client.post(
            self._respond_url(vote.id),
            data=json.dumps({"decision": "INCLUDE"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            InDiscussionVoteResponse.objects.filter(
                vote=vote, reviewer=self.r2, decision="INCLUDE"
            ).exists()
        )

    def test_respond_duplicate_returns_409(self):
        """Responding twice to the same straw poll → 409."""
        vote = self._make_vote()
        InDiscussionVoteResponse.objects.create(
            vote=vote, reviewer=self.r2, decision="INCLUDE"
        )
        self.client.force_login(self.r2)
        resp = self.client.post(
            self._respond_url(vote.id),
            data=json.dumps({"decision": "EXCLUDE"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)

    def test_respond_invalid_decision_returns_400(self):
        """An out-of-enum decision value → 400."""
        vote = self._make_vote()
        self.client.force_login(self.r2)
        resp = self.client.post(
            self._respond_url(vote.id),
            data=json.dumps({"decision": "BOGUS"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_non_conflicting_reviewer_cannot_respond(self):
        """A non-conflicting org member cannot respond → 403."""
        vote = self._make_vote()
        self.client.force_login(self.outsider)
        resp = self.client.post(
            self._respond_url(vote.id),
            data=json.dumps({"decision": "INCLUDE"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# F1 / PMD #282 — can_resolve must mirror the resolve POST's permission check
# ---------------------------------------------------------------------------


class ConflictResolvePermissionFlagTest(DisablePersonalOrgSignalMixin, TestCase):
    """ConflictDetailView.permissions.can_resolve vs the resolve POST's perm."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Perm Org", slug="perm-edge")
        # Session owner with LEAD_REVIEWER role — can view, cannot resolve.
        self.lead = create_test_user(username_prefix="perm_lead")
        OrganisationMembership.objects.create(
            user=self.lead, organisation=self.org, role="LEAD_REVIEWER", is_active=True
        )
        self.senior = create_test_user(username_prefix="perm_senior")
        OrganisationMembership.objects.create(
            user=self.senior,
            organisation=self.org,
            role="SENIOR_RESEARCHER",
            is_active=True,
        )
        self.r2 = create_test_user(username_prefix="perm_r2")
        OrganisationMembership.objects.create(
            user=self.r2, organisation=self.org, role="REVIEWER", is_active=True
        )
        self.session = _make_wf2_session(self.org, self.lead)
        self.result = ProcessedResult.objects.create(
            session=self.session, title="R", url="https://example.com/perm", snippet="s"
        )
        d1 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.lead,
            decision="INCLUDE",
        )
        d2 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.r2,
            decision="EXCLUDE",
            exclusion_reason="not_relevant",
        )
        self.conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
        )
        self.conflict.conflicting_decisions.set([d1, d2])
        self.client = Client()

    def _detail_url(self):
        return reverse("review_results_api:conflict-details", args=[self.conflict.id])

    def test_lead_reviewer_can_resolve_flag_is_false(self):
        """F1: a LEAD_REVIEWER (view but not resolve) gets can_resolve=False."""
        self.client.force_login(self.lead)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["permissions"]["can_resolve"])

    def test_lead_reviewer_resolve_post_is_403(self):
        """The flag now agrees with the POST, which 403s for a LEAD_REVIEWER."""
        self.client.force_login(self.lead)
        resp = self.client.post(
            reverse("review_results_api:resolve-conflict", args=[self.conflict.id]),
            data=json.dumps({"decision": "INCLUDE"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_senior_researcher_can_resolve_flag_is_true(self):
        """A SENIOR_RESEARCHER (has CONFLICT_RESOLVE) still gets can_resolve=True."""
        self.client.force_login(self.senior)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["permissions"]["can_resolve"])

    def test_conflicting_reviewer_can_escalate_flag_is_true(self):
        """F1: a conflicting reviewer (escalate, not resolve) gets can_escalate=True."""
        self.client.force_login(self.lead)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)
        perms = resp.json()["permissions"]
        # Mutually exclusive: this user escalates but cannot resolve.
        self.assertTrue(perms["can_escalate"])
        self.assertFalse(perms["can_resolve"])

    def test_senior_researcher_can_escalate_flag_is_false(self):
        """The resolver (not a conflicting reviewer) gets can_escalate=False."""
        self.client.force_login(self.senior)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["permissions"]["can_escalate"])

    def test_can_escalate_flag_is_false_once_escalated(self):
        """can_escalate mirrors the POST guard: false once status is ESCALATED."""
        self.conflict.status = "ESCALATED"
        self.conflict.save(update_fields=["status"])
        self.client.force_login(self.lead)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["permissions"]["can_escalate"])
