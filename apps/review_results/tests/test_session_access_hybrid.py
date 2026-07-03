"""Regression tests for the GH #230 hybrid session-access model.

Screening surfaces (work queue, result detail, claim, submit) require
*participation* (session owner or accepted-invitation reviewer). Oversight
surfaces (conflict resolution, dashboards) additionally admit holders of the
relevant org role. Bare organisation membership no longer grants access -- this
closes the read leak AND the claim->submit write leak the org fast-path allowed.
"""

import json

from django.test import TestCase
from django.urls import reverse

from apps.core.tests.utils import (
    DisablePersonalOrgSignalMixin,
    create_test_user,
    make_session_participant,
)
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.models import ConflictResolution, ReviewerDecision


class HybridSessionAccessTest(DisablePersonalOrgSignalMixin, TestCase):
    """Participation gates screening; org role gates oversight (GH #230)."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Org", slug="hybrid-230")

        # owner (also a conflicting reviewer); invited reviewer; and three
        # non-invited org members at different roles.
        self.owner = create_test_user(username_prefix="owner")
        self.invited = create_test_user(username_prefix="invited")
        self.bystander = create_test_user(username_prefix="bystander")  # plain member
        self.senior = create_test_user(username_prefix="senior")  # arbitrator role
        self.lead = create_test_user(username_prefix="lead")  # dashboard role
        for user, role in (
            (self.owner, "LEAD_REVIEWER"),
            (self.invited, "REVIEWER"),
            (self.bystander, "REVIEWER"),
            (self.senior, "SENIOR_RESEARCHER"),
            (self.lead, "LEAD_REVIEWER"),
        ):
            OrganisationMembership.objects.create(
                user=user, organisation=self.org, role=role, is_active=True
            )

        self.session = SearchSession.objects.create(
            owner=self.owner,
            organisation=self.org,
            title="WF2 Session",
            status="under_review",
        )
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            version=1,
            min_reviewers_per_result=2,
            blind_screening_enforced=True,
            conflict_resolution_method="CONSENSUS",
            consensus_criteria="MAJORITY",
            created_by=self.owner,
            organisation=self.org,
        )
        self.session.current_configuration = self.config
        self.session.save(update_fields=["current_configuration"])

        # Only the invited reviewer accepts -- bystander/senior/lead never do.
        make_session_participant(self.session, self.invited)

        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="R1",
            url="https://example.com/r1",
            snippet="s",
            processing_status="success",
            min_reviewers_required=2,
        )
        self.d_owner = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.owner,
            decision="INCLUDE",
            confidence_level=3,
        )
        self.d_invited = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.invited,
            decision="EXCLUDE",
            exclusion_reason="not_relevant",
            confidence_level=3,
        )
        self.conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=self.result,
            conflict_type="INCLUDE_EXCLUDE",
            status="PENDING",
            resolution_method="CONSENSUS",
        )
        self.conflict.conflicting_decisions.add(self.d_owner, self.d_invited)

    # ----- screening: participation only -------------------------------------

    def test_noninvited_member_cannot_read_work_queue(self):
        """The #230 read leak: a non-invited org member is denied the queue."""
        self.client.force_login(self.bystander)
        resp = self.client.get(
            reverse("review_results_api:work-queue"),
            {"session_id": str(self.session.id)},
        )
        self.assertEqual(resp.status_code, 404)

    def test_noninvited_member_cannot_read_result_detail(self):
        self.client.force_login(self.bystander)
        resp = self.client.get(
            reverse("review_results_api:result-detail", args=[self.result.id])
        )
        self.assertEqual(resp.status_code, 404)

    def test_noninvited_member_cannot_claim(self):
        """The #230 write leak: claiming created an assignment for any member."""
        self.client.force_login(self.bystander)
        resp = self.client.post(
            reverse("review_results_api:claim-result"),
            data=json.dumps({"session_id": str(self.session.id)}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_noninvited_member_cannot_submit_decision(self):
        self.client.force_login(self.bystander)
        resp = self.client.post(
            reverse("review_results_api:submit-decision", args=[self.result.id]),
            data=json.dumps({"decision": "INCLUDE", "confidence_level": 3}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_invited_reviewer_can_read_work_queue(self):
        self.client.force_login(self.invited)
        resp = self.client.get(
            reverse("review_results_api:work-queue"),
            {"session_id": str(self.session.id)},
        )
        self.assertEqual(resp.status_code, 200)

    def test_owner_can_read_work_queue(self):
        self.client.force_login(self.owner)
        resp = self.client.get(
            reverse("review_results_api:work-queue"),
            {"session_id": str(self.session.id)},
        )
        self.assertEqual(resp.status_code, 200)

    # ----- oversight: participation OR org role ------------------------------

    def test_senior_researcher_can_resolve_without_invitation(self):
        """Arbitration reaches the conflict via CONFLICT_RESOLVE, not invitation."""
        self.client.force_login(self.senior)
        resp = self.client.post(
            reverse("review_results_api:resolve-conflict", args=[self.conflict.id]),
            data=json.dumps({"decision": "INCLUDE", "resolution_notes": "Arbitrated"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.conflict.refresh_from_db()
        self.assertEqual(self.conflict.status, "RESOLVED")

    def test_noninvited_plain_member_cannot_resolve(self):
        """A plain REVIEWER has neither participation nor CONFLICT_VIEW -> 404."""
        self.client.force_login(self.bystander)
        resp = self.client.post(
            reverse("review_results_api:resolve-conflict", args=[self.conflict.id]),
            data=json.dumps({"decision": "INCLUDE", "resolution_notes": "nope"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_lead_reviewer_can_view_dashboard_without_invitation(self):
        """Org dashboard oversight is granted by role, not per-session invitation."""
        self.client.force_login(self.lead)
        resp = self.client.get(
            reverse("review_results_api:dashboard-stats"),
            {"session_id": str(self.session.id)},
        )
        self.assertEqual(resp.status_code, 200)

    def test_noninvited_plain_member_cannot_view_dashboard(self):
        """A plain REVIEWER lacks the dashboard role and participation -> 404."""
        self.client.force_login(self.bystander)
        resp = self.client.get(
            reverse("review_results_api:dashboard-stats"),
            {"session_id": str(self.session.id)},
        )
        self.assertEqual(resp.status_code, 404)

    def test_orgless_session_denies_role_based_oversight(self):
        """A session with no organisation must fail closed on the role tier.

        RoleBasedPermissionBackend.has_perm() falls back to the requester's
        *ambient* org context (their own most-recent membership) when checked
        against a None organisation. Without the guard, a role holder in an
        unrelated org could pass oversight checks on a session tied to no org
        at all, since the permission check is silently redirected to their own
        org instead of failing.
        """
        orgless_session = SearchSession.objects.create(
            owner=self.owner,
            organisation=None,
            title="Orgless Session",
            status="under_review",
        )
        self.client.force_login(self.senior)
        resp = self.client.get(
            reverse("review_results_api:dashboard-stats"),
            {"session_id": str(orgless_session.id)},
        )
        self.assertEqual(resp.status_code, 404)
