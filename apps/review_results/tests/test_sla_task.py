"""Tests for conflict SLA reminder Celery task (R06, R07)."""

import contextlib
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation, OrganisationMembership
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.review_results.models import ConflictResolution, ReviewerDecision
from apps.review_results.tasks import check_conflict_sla_reminders


class TestCheckConflictSlaReminders(TestCase):
    """Tests for the check_conflict_sla_reminders periodic task (R06, R07)."""

    def setUp(self):
        self.org = Organisation.objects.create(
            name="Test Org", slug="test-org-sla-task"
        )
        self.reviewer1 = create_test_user(
            username_prefix="sla_task_r1", email="sla_task_r1@test.com"
        )
        self.reviewer2 = create_test_user(
            username_prefix="sla_task_r2", email="sla_task_r2@test.com"
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

        # WF2 session with config
        self.session = SearchSession.objects.create(
            organisation=self.org,
            title="SLA Task Test",
            owner=self.reviewer1,
            status="under_review",
        )
        self.config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            version=1,
            organisation=self.org,
            created_by=self.reviewer1,
            discussion_sla_hours=72,
        )
        self.session.current_configuration = self.config
        self.session.save()

        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com",
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

    def _create_conflict(self, hours_ago: float, **kwargs) -> ConflictResolution:
        """Helper to create a conflict detected a certain number of hours ago."""
        conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=self.result,
            status=kwargs.get("status", "PENDING"),
        )
        # auto_now_add prevents setting detected_at on create, so use update()
        ConflictResolution.objects.filter(id=conflict.id).update(
            detected_at=timezone.now() - timedelta(hours=hours_ago)
        )
        conflict.refresh_from_db()
        conflict.conflicting_decisions.add(self.decision1, self.decision2)
        return conflict

    @patch("apps.review_results.tasks.redis_lock")
    def test_sends_50_percent_reminder_R06_R07(self, mock_lock):
        """Task should send 50% reminder when threshold reached."""

        @contextlib.contextmanager
        def fake_lock(*args, **kwargs):
            yield True

        mock_lock.side_effect = fake_lock

        # 36h elapsed out of 72h = 50%
        self._create_conflict(hours_ago=36)
        result = check_conflict_sla_reminders()

        self.assertEqual(result["sent_50"], 1)
        self.assertEqual(result["sent_90"], 0)
        self.assertGreater(len(mail.outbox), 0)

    @patch("apps.review_results.tasks.redis_lock")
    def test_sends_90_percent_reminder_R06_R07(self, mock_lock):
        """Task should send 90% reminder when threshold reached."""

        @contextlib.contextmanager
        def fake_lock(*args, **kwargs):
            yield True

        mock_lock.side_effect = fake_lock

        # 65h elapsed out of 72h = ~90%
        self._create_conflict(hours_ago=65)
        result = check_conflict_sla_reminders()

        self.assertEqual(result["sent_50"], 1)  # Also triggers 50%
        self.assertEqual(result["sent_90"], 1)

    @patch("apps.review_results.tasks.redis_lock")
    def test_does_not_resend_already_sent_threshold_R07(self, mock_lock):
        """Task should not resend a threshold that was already sent."""

        @contextlib.contextmanager
        def fake_lock(*args, **kwargs):
            yield True

        mock_lock.side_effect = fake_lock

        conflict = self._create_conflict(hours_ago=36)
        conflict.sla_reminders_sent = {"50": timezone.now().isoformat()}
        conflict.save()

        result = check_conflict_sla_reminders()

        self.assertEqual(result["sent_50"], 0)
        self.assertEqual(result["sent_90"], 0)

    @patch("apps.review_results.tasks.redis_lock")
    def test_skips_resolved_conflicts_R06(self, mock_lock):
        """Task should skip resolved conflicts."""

        @contextlib.contextmanager
        def fake_lock(*args, **kwargs):
            yield True

        mock_lock.side_effect = fake_lock

        self._create_conflict(hours_ago=36, status="RESOLVED")
        result = check_conflict_sla_reminders()

        self.assertEqual(result["sent_50"], 0)
        self.assertEqual(result["sent_90"], 0)

    @patch("apps.review_results.tasks.redis_lock")
    def test_skips_workflow_1_conflicts_R06(self, mock_lock):
        """Task should skip conflicts in WF1 sessions."""

        @contextlib.contextmanager
        def fake_lock(*args, **kwargs):
            yield True

        mock_lock.side_effect = fake_lock

        # Create a WF1 session
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
            session=wf1_session, title="WF1 Result", url="https://example.com/wf1"
        )
        conflict = ConflictResolution.objects.create(
            organisation=self.org,
            result=wf1_result,
            status="PENDING",
        )
        conflict.conflicting_decisions.add(self.decision1, self.decision2)

        result = check_conflict_sla_reminders()
        self.assertEqual(result["sent_50"], 0)

    @patch("apps.review_results.tasks.redis_lock")
    def test_updates_sla_reminders_sent_field_R07(self, mock_lock):
        """Task should update sla_reminders_sent after sending."""

        @contextlib.contextmanager
        def fake_lock(*args, **kwargs):
            yield True

        mock_lock.side_effect = fake_lock

        conflict = self._create_conflict(hours_ago=36)
        check_conflict_sla_reminders()

        conflict.refresh_from_db()
        self.assertIn("50", conflict.sla_reminders_sent)

    @patch("apps.review_results.tasks.redis_lock")
    def test_handles_no_pending_conflicts_R06(self, mock_lock):
        """Task should handle gracefully when no conflicts exist."""

        @contextlib.contextmanager
        def fake_lock(*args, **kwargs):
            yield True

        mock_lock.side_effect = fake_lock

        result = check_conflict_sla_reminders()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sent_50"], 0)
        self.assertEqual(result["sent_90"], 0)
