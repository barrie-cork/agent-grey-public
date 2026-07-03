"""Tests for ConflictResolution SLA time-boxing (R02-R05, R12)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.models import (
    ConflictResolution,
    ReviewerDecision,
    RevoteProposal,
)


class TestGetSlaInfo(TestCase):
    """Tests for ConflictResolution.get_sla_info() (R03-R05, R12)."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Test Org", slug="test-org-sla")
        self.reviewer1 = create_test_user(
            username_prefix="sla_r1", email="sla_r1@test.com"
        )
        self.reviewer2 = create_test_user(
            username_prefix="sla_r2", email="sla_r2@test.com"
        )
        OrganisationMembership.objects.create(
            organisation=self.org,
            user=self.reviewer1,
            role="RESEARCHER",
            is_active=True,
        )
        OrganisationMembership.objects.create(
            organisation=self.org,
            user=self.reviewer2,
            role="RESEARCHER",
            is_active=True,
        )

        # WF2 session + config
        self.session = SearchSession.objects.create(
            organisation=self.org,
            title="SLA Test Session",
            owner=self.reviewer1,
            status="under_review",
        )
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            version=1,
            organisation=self.org,
            created_by=self.reviewer1,
        )
        self.session.current_configuration = self.config
        self.session.save()

        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com",
            snippet="Test snippet",
        )
        self.decision1 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        self.decision2 = ReviewerDecision.objects.create(
            organisation=self.org,
            result=self.result,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            screening_stage="SCREENING",
            exclusion_reason="Not relevant",
        )
        self.conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=self.result,
            status="PENDING",
        )
        # auto_now_add prevents setting detected_at on create, so use update()
        ConflictResolution.objects.filter(id=self.conflict.id).update(
            detected_at=timezone.now() - timedelta(hours=36)
        )
        self.conflict.refresh_from_db()
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

    def test_returns_none_for_resolved_conflict_R05(self):
        """Resolved conflicts should not have SLA info."""
        self.conflict.status = "RESOLVED"
        self.conflict.save()
        self.assertIsNone(self.conflict.get_sla_info())

    def test_returns_none_for_workflow_1_session_R12(self):
        """WF1 sessions (no conflicts) should return None."""
        wf1_session = SearchSession.objects.create(
            organisation=self.org,
            title="WF1 Session",
            owner=self.reviewer1,
            status="under_review",
        )
        wf1_config = ReviewConfiguration.objects.create(
            session=wf1_session,
            min_reviewers_per_result=1,
            version=1,
            organisation=self.org,
            created_by=self.reviewer1,
        )
        wf1_session.current_configuration = wf1_config
        wf1_session.save()

        wf1_result = ProcessedResult.objects.create(
            session=wf1_session,
            title="WF1 Result",
            url="https://example.com/wf1",
        )
        wf1_conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=wf1_result,
            status="PENDING",
        )
        self.assertIsNone(wf1_conflict.get_sla_info())

    def test_discussion_sla_for_pending_conflict_R03_R04(self):
        """PENDING conflicts use discussion_sla_hours."""
        info = self.conflict.get_sla_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["sla_hours"], 72)  # Default discussion SLA

    def test_discussion_sla_for_in_discussion_conflict_R03_R04(self):
        """IN_DISCUSSION conflicts use discussion_sla_hours."""
        self.conflict.status = "IN_DISCUSSION"
        self.conflict.save()
        info = self.conflict.get_sla_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["sla_hours"], 72)

    def test_arbitration_sla_for_escalated_conflict_R04(self):
        """ESCALATED conflicts use arbitration_sla_hours."""
        self.conflict.status = "ESCALATED"
        self.conflict.save()
        info = self.conflict.get_sla_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["sla_hours"], 48)

    def test_revote_sla_when_active_revote_R04(self):
        """Conflicts with an active revote use revote_sla_hours."""
        RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Let us re-vote",
            status="PROPOSED",
            expires_at=timezone.now() + timedelta(hours=24),
        )
        info = self.conflict.get_sla_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["sla_hours"], 24)

    def test_is_approaching_at_50_percent_R03(self):
        """is_approaching should be True when >= 50% elapsed."""
        # 36h elapsed out of 72h = 50%
        info = self.conflict.get_sla_info()
        self.assertTrue(info["is_approaching"])
        self.assertFalse(info["is_critical"])
        self.assertFalse(info["is_overdue"])

    def test_is_critical_at_90_percent_R03(self):
        """is_critical should be True when >= 90% elapsed."""
        ConflictResolution.objects.filter(id=self.conflict.id).update(
            detected_at=timezone.now() - timedelta(hours=65)
        )
        self.conflict.refresh_from_db()
        info = self.conflict.get_sla_info()
        self.assertTrue(info["is_approaching"])
        self.assertTrue(info["is_critical"])
        self.assertFalse(info["is_overdue"])

    def test_is_overdue_past_deadline_R03(self):
        """is_overdue should be True when > 100% elapsed."""
        ConflictResolution.objects.filter(id=self.conflict.id).update(
            detected_at=timezone.now() - timedelta(hours=80)
        )
        self.conflict.refresh_from_db()
        info = self.conflict.get_sla_info()
        self.assertTrue(info["is_overdue"])
        self.assertGreater(info["hours_overdue"], 0)
        self.assertEqual(info["hours_remaining"], 0)

    def test_percent_elapsed_capped_at_999_R03(self):
        """percent_elapsed should be capped at 999."""
        ConflictResolution.objects.filter(id=self.conflict.id).update(
            detected_at=timezone.now() - timedelta(hours=72000)
        )
        self.conflict.refresh_from_db()
        info = self.conflict.get_sla_info()
        self.assertLessEqual(info["percent_elapsed"], 999)
