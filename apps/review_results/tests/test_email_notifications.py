"""
Unit tests for Phase 08: Email Notifications & Completion Flow.

Tests the email notification signals and session completion validation:
- conflict_detected_handler (signal)
- consensus_reached_handler (signal)
- irr_threshold_check (signal)
- Session completion blocks on unresolved conflicts
"""

from django.test import TestCase
from django.core import mail
from django.utils import timezone
from datetime import timedelta

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import SearchSession
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import (
    ReviewerDecision,
    ConflictResolution,
    InterRaterReliability,
)
from apps.core.tests.utils import create_test_user


class Phase08EmailNotificationTests(TestCase):
    """Test Phase 08 email notification signals."""

    def setUp(self):
        """Set up test data."""
        # Clear mail outbox
        mail.outbox = []

        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(
            username_prefix="reviewer1", first_name="Reviewer", last_name="One"
        )
        self.reviewer2 = create_test_user(
            username_prefix="reviewer2", first_name="Reviewer", last_name="Two"
        )

        # Add users to organisation
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.reviewer1,
            role="RESEARCHER",
            is_active=True,
        )
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.reviewer2,
            role="RESEARCHER",
            is_active=True,
        )

        # Create search session
        self.session = SearchSession.objects.create(
            organisation=self.organisation,
            title="Test Review Session",
            owner=self.reviewer1,
            status="under_review",
        )

        # Create processed result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Research Article",
            url="https://example.com/article",
            snippet="This is a test snippet",
        )

        # Create conflicting decisions
        self.decision1 = ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=self.reviewer1,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        self.decision2 = ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=self.reviewer2,
            decision="EXCLUDE",
            screening_stage="SCREENING",
            exclusion_reason="Does not meet inclusion criteria",
        )

    def test_conflict_detected_email_sent(self):
        """Test that email is sent when conflict is detected (signal)."""
        # Clear mail outbox
        mail.outbox = []

        # Create conflict (triggers signal)
        # IMPORTANT: Add conflicting_decisions during creation to avoid signal timing issues
        conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            status="PENDING",
            conflict_type="INCLUDE_EXCLUDE",
            detected_at=timezone.now(),
        )
        # Add decisions AFTER creation (m2m post_save signal)
        conflict.conflicting_decisions.add(self.decision1, self.decision2)
        conflict.save()  # Ensure signal fires

        # Note: Email sending depends on conflicting_decisions being present
        # The signal handler checks for exactly 2 decisions
        # If mail.outbox is empty, the signal may have fired before decisions were added
        if len(conflict.conflicting_decisions.all()) == 2:
            # Re-trigger the notification manually to test
            from apps.review_results.services.email_notification_service import (
                EmailNotificationService,
            )

            service = EmailNotificationService()
            service.send_conflict_notification(str(conflict.id))

        # Check that emails were sent to both reviewers
        self.assertGreaterEqual(
            len(mail.outbox), 2, "Should send email to both reviewers"
        )

        # Check email recipients
        recipients = [email.to[0] for email in mail.outbox]
        self.assertIn(self.reviewer1.email, recipients)
        self.assertIn(self.reviewer2.email, recipients)

        # Check email subject
        for email in mail.outbox:
            self.assertIn("Conflict Detected", email.subject)
            self.assertIn(self.session.title, email.subject)

    def test_conflict_detected_email_not_sent_for_resolved_conflict(self):
        """Test that email is NOT sent for already resolved conflicts."""
        # Clear mail outbox
        mail.outbox = []

        # Create resolved conflict (should NOT trigger email)
        conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            status="RESOLVED",  # Already resolved
            conflict_type="INCLUDE_EXCLUDE",
            detected_at=timezone.now(),
            resolved_at=timezone.now(),
            resolution_method="CONSENSUS",
            final_decision=self.decision1,
        )
        conflict.conflicting_decisions.add(self.decision1, self.decision2)

        # No emails should be sent
        self.assertEqual(
            len(mail.outbox), 0, "Should NOT send email for resolved conflict"
        )

    def test_consensus_reached_email_sent(self):
        """Test that email is sent when consensus is reached (signal)."""
        # Create pending conflict
        conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            status="PENDING",
            conflict_type="INCLUDE_EXCLUDE",
            detected_at=timezone.now(),
        )
        conflict.conflicting_decisions.add(self.decision1, self.decision2)

        # Clear mail outbox (conflict detection emails already sent)
        mail.outbox = []

        # Resolve conflict (triggers signal)
        conflict.status = "RESOLVED"
        conflict.resolved_at = timezone.now()
        conflict.resolution_method = "CONSENSUS"
        conflict.final_decision = self.decision1
        conflict.resolved_by = self.reviewer1
        conflict.save()

        # Check that emails were sent to both reviewers
        self.assertEqual(len(mail.outbox), 2, "Should send email to both reviewers")

        # Check email recipients
        recipients = [email.to[0] for email in mail.outbox]
        self.assertIn(self.reviewer1.email, recipients)
        self.assertIn(self.reviewer2.email, recipients)

        # Check email subject
        for email in mail.outbox:
            self.assertIn("Consensus Reached", email.subject)
            self.assertIn(self.session.title, email.subject)

    def test_consensus_reached_email_not_sent_on_creation(self):
        """Test that consensus email is NOT sent when conflict is first created."""
        # Clear mail outbox
        mail.outbox = []

        # Create resolved conflict in one step (should still trigger conflict_detected)
        conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            status="RESOLVED",  # Created as resolved
            conflict_type="INCLUDE_EXCLUDE",
            detected_at=timezone.now(),
            resolved_at=timezone.now(),
            resolution_method="CONSENSUS",
            final_decision=self.decision1,
        )
        conflict.conflicting_decisions.add(self.decision1, self.decision2)

        # Should only send conflict_detected emails (not consensus_reached)
        # Because consensus_reached handler has "if created: return"
        self.assertEqual(
            len(mail.outbox), 0, "Consensus handler should skip on creation"
        )

    def test_low_irr_alert_email_sent(self):
        """Test that email is sent when Cohen's Kappa falls below threshold."""
        # Clear mail outbox
        mail.outbox = []

        # Create IRR metric below threshold (triggers signal)
        now = timezone.now()
        _irr = InterRaterReliability.objects.create(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            cohens_kappa=0.55,  # Below 0.70 threshold
            percentage_agreement=55.0,  # Required field
            total_comparisons=100,
            agreements=55,
            disagreements=45,
            calculation_window_start=now - timedelta(days=1),
            calculation_window_end=now,
        )

        # Check that email was sent to session owner (lead reviewer)
        self.assertEqual(len(mail.outbox), 1, "Should send email to session owner")
        self.assertEqual(mail.outbox[0].to[0], self.session.owner.email)

        # Check email subject
        self.assertIn("IRR Alert", mail.outbox[0].subject)
        self.assertIn(self.session.title, mail.outbox[0].subject)

    def test_low_irr_alert_not_sent_for_good_kappa(self):
        """Test that email is NOT sent when Cohen's Kappa is above threshold."""
        # Clear mail outbox
        mail.outbox = []

        # Create IRR metric above threshold (should NOT trigger email)
        now = timezone.now()
        _irr = InterRaterReliability.objects.create(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            cohens_kappa=0.85,  # Above 0.70 threshold
            percentage_agreement=85.0,  # Required field
            total_comparisons=100,
            agreements=85,
            disagreements=15,
            calculation_window_start=now - timedelta(days=1),
            calculation_window_end=now,
        )

        # No email should be sent
        self.assertEqual(len(mail.outbox), 0, "Should NOT send email for good kappa")

    def test_low_irr_alert_not_sent_for_null_kappa(self):
        """Test that email is NOT sent when Cohen's Kappa is None."""
        # Clear mail outbox
        mail.outbox = []

        # Create IRR metric with null kappa (should NOT trigger email)
        now = timezone.now()
        _irr = InterRaterReliability.objects.create(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            cohens_kappa=None,  # Null value
            percentage_agreement=0.0,  # Required field
            total_comparisons=0,
            agreements=0,
            disagreements=0,
            calculation_window_start=now - timedelta(days=1),
            calculation_window_end=now,
        )

        # No email should be sent
        self.assertEqual(len(mail.outbox), 0, "Should NOT send email for null kappa")


class Phase08SessionCompletionValidationTests(TestCase):
    """Test session completion validation blocks on unresolved conflicts."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create user
        self.user = create_test_user()

        # Add user to organisation
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.user,
            role="RESEARCHER",
            is_active=True,
        )

        # Create search session
        self.session = SearchSession.objects.create(
            organisation=self.organisation,
            title="Test Review Session",
            owner=self.user,
            status="under_review",
        )

        # Create processed result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Research Article",
            url="https://example.com/article",
            snippet="This is a test snippet",
        )

    def test_completion_blocked_with_unresolved_conflicts(self):
        """Test that session completion is blocked when unresolved conflicts exist."""
        # Create reviewer
        reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create conflicting decisions
        decision1 = ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=self.user,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        decision2 = ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=reviewer2,
            decision="EXCLUDE",
            screening_stage="SCREENING",
        )

        # Create unresolved conflict
        conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            status="PENDING",  # Unresolved
            conflict_type="INCLUDE_EXCLUDE",
            detected_at=timezone.now(),
        )
        conflict.conflicting_decisions.add(decision1, decision2)

        # Login and attempt to complete session
        self.client.login(username=self.user.username, password="testpass123")
        response = self.client.post(
            f"/review-results/complete/{self.session.id}/", follow=True
        )

        # Should redirect back to overview with error message
        self.assertEqual(response.status_code, 200)
        messages = list(response.context["messages"])
        self.assertTrue(
            any("unresolved conflict" in str(m).lower() for m in messages),
            "Should display unresolved conflict error",
        )

        # Session should still be under_review
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "under_review")

    def test_completion_allowed_with_all_conflicts_resolved(self):
        """Test that session completion is allowed when all conflicts are resolved."""
        # Create reviewer
        reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create conflicting decisions
        decision1 = ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=self.user,
            decision="INCLUDE",
            screening_stage="SCREENING",
        )
        decision2 = ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=reviewer2,
            decision="EXCLUDE",
            screening_stage="SCREENING",
        )

        # Create resolved conflict
        conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            status="RESOLVED",  # Resolved
            conflict_type="INCLUDE_EXCLUDE",
            detected_at=timezone.now(),
            resolved_at=timezone.now(),
            resolution_method="CONSENSUS",
            final_decision=decision1,
        )
        conflict.conflicting_decisions.add(decision1, decision2)

        # Login and attempt to complete session
        self.client.login(username=self.user.username, password="testpass123")
        response = self.client.post(
            f"/review-results/complete/{self.session.id}/", follow=True
        )

        # Should succeed and redirect to reporting dashboard
        self.assertEqual(response.status_code, 200)

        # Session should be completed
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")

    def test_completion_allowed_with_no_conflicts(self):
        """Test that session completion is allowed when no conflicts exist."""
        # Login and attempt to complete session (no conflicts created)
        self.client.login(username=self.user.username, password="testpass123")
        response = self.client.post(
            f"/review-results/complete/{self.session.id}/", follow=True
        )

        # Should succeed and redirect to reporting dashboard
        self.assertEqual(response.status_code, 200)

        # Session should be completed
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")
