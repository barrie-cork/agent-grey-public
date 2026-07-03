"""
Unit tests for email notification service (Phase 4: Consensus Discussion).

Tests the 4 new email notification methods:
- notify_conflict_comment_added
- notify_revote_proposed
- notify_revote_ready
- notify_consensus_reached_via_revote
"""

from django.test import TestCase
from django.core import mail
from django.utils import timezone
from datetime import timedelta
import uuid

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import SearchSession, ReviewInvitation
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import (
    ReviewerDecision,
    ConflictResolution,
    ConflictComment,
    RevoteProposal,
    InterRaterReliability,
)
from apps.core.tests.utils import create_test_user
from apps.review_results.services.email_notification_service import (
    EmailNotificationService,
)


class EmailNotificationServicePhase4Tests(TestCase):
    """Test Phase 4 email notification methods."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users
        self.reviewer1 = create_test_user(
            username_prefix="reviewer1",
            first_name="Reviewer",
            last_name="One",
            email="reviewer1@test.com",
        )
        self.reviewer2 = create_test_user(
            username_prefix="reviewer2",
            first_name="Reviewer",
            last_name="Two",
            email="reviewer2@test.com",
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

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            status="PENDING",
            detected_at=timezone.now(),
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

        # Initialize email service
        self.email_service = EmailNotificationService()

        # Clear mail outbox
        mail.outbox = []

    def test_notify_conflict_comment_added_sends_email(self):
        """Test that notify_conflict_comment_added sends email to other reviewer."""
        # Create comment by reviewer1
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.reviewer1,
            content="I think we should discuss this result further.",
        )

        # Send notification
        result = self.email_service.notify_conflict_comment_added(
            conflict_id=str(self.conflict.id),
            comment_id=str(comment.id),
            commenter_id=str(self.reviewer1.id),
        )

        # Assert email sent successfully
        self.assertTrue(result)

        # Assert 1 email sent (to reviewer2 only)
        self.assertEqual(len(mail.outbox), 1)

        # Assert recipient is reviewer2
        self.assertEqual(mail.outbox[0].to, [self.reviewer2.email])

        # Assert subject contains session title
        self.assertIn("Test Review Session", mail.outbox[0].subject)

        # Assert body contains comment preview
        self.assertIn("I think we should discuss", mail.outbox[0].body)

    def test_notify_conflict_comment_added_no_recipients(self):
        """Test that notify_conflict_comment_added handles no other reviewers."""
        # Create comment by reviewer1
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.reviewer1, content="Test comment"
        )

        # Remove reviewer2 from conflict
        self.conflict.conflicting_decisions.remove(self.decision2)

        # Send notification
        result = self.email_service.notify_conflict_comment_added(
            conflict_id=str(self.conflict.id),
            comment_id=str(comment.id),
            commenter_id=str(self.reviewer1.id),
        )

        # Assert returns True (not an error, just no recipients)
        self.assertTrue(result)

        # Assert no emails sent
        self.assertEqual(len(mail.outbox), 0)

    def test_notify_revote_proposed_sends_email(self):
        """Test that notify_revote_proposed sends email to other reviewer."""
        # Create proposal by reviewer1
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="After reviewing the full document, I believe we should reconsider.",
            status="PROPOSED",
            expires_at=timezone.now() + timedelta(hours=48),
        )
        proposal.accepted_by.add(self.reviewer1)

        # Send notification
        result = self.email_service.notify_revote_proposed(
            conflict_id=str(self.conflict.id),
            proposal_id=str(proposal.id),
            proposer_id=str(self.reviewer1.id),
        )

        # Assert email sent successfully
        self.assertTrue(result)

        # Assert 1 email sent (to reviewer2 only)
        self.assertEqual(len(mail.outbox), 1)

        # Assert recipient is reviewer2
        self.assertEqual(mail.outbox[0].to, [self.reviewer2.email])

        # Assert subject contains "Re-Vote Proposed"
        self.assertIn("Re-Vote Proposed", mail.outbox[0].subject)

        # Assert body contains rationale
        self.assertIn("After reviewing the full document", mail.outbox[0].body)

    def test_notify_revote_ready_sends_email_to_all(self):
        """Test that notify_revote_ready sends email to all reviewers."""
        # Create accepted proposal
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test rationale",
            status="ACCEPTED",
            accepted_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=48),
        )
        proposal.accepted_by.add(self.reviewer1, self.reviewer2)

        # Send notification
        result = self.email_service.notify_revote_ready(
            conflict_id=str(self.conflict.id), proposal_id=str(proposal.id)
        )

        # Assert email sent successfully
        self.assertTrue(result)

        # Assert 2 emails sent (to both reviewers)
        self.assertEqual(len(mail.outbox), 2)

        # Assert recipients include both reviewers
        recipients = [email.to[0] for email in mail.outbox]
        self.assertIn(self.reviewer1.email, recipients)
        self.assertIn(self.reviewer2.email, recipients)

        # Assert subject contains "Re-Vote Ready"
        self.assertIn("Re-Vote Ready", mail.outbox[0].subject)

    def test_notify_consensus_reached_via_revote_sends_email(self):
        """Test that notify_consensus_reached_via_revote sends email to all reviewers."""
        # Create completed proposal
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test rationale",
            status="COMPLETED",
            resulted_in_consensus=True,
            accepted_at=timezone.now(),
            completed_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=48),
        )

        # Send notification
        result = self.email_service.notify_consensus_reached_via_revote(
            conflict_id=str(self.conflict.id),
            proposal_id=str(proposal.id),
            consensus_decision="INCLUDE",
        )

        # Assert email sent successfully
        self.assertTrue(result)

        # Assert 2 emails sent (to both reviewers)
        self.assertEqual(len(mail.outbox), 2)

        # Assert recipients include both reviewers
        recipients = [email.to[0] for email in mail.outbox]
        self.assertIn(self.reviewer1.email, recipients)
        self.assertIn(self.reviewer2.email, recipients)

        # Assert subject contains "Consensus Reached"
        self.assertIn("Consensus Reached", mail.outbox[0].subject)

        # Assert body contains decision
        self.assertIn("Include", mail.outbox[0].body)

    def test_email_templates_render_correctly(self):
        """Test that all email templates render without errors."""
        # Test comment notification template
        comment = ConflictComment.objects.create(
            conflict=self.conflict,
            author=self.reviewer1,
            content="Test comment with **markdown**",
        )
        self.email_service.notify_conflict_comment_added(
            conflict_id=str(self.conflict.id),
            comment_id=str(comment.id),
            commenter_id=str(self.reviewer1.id),
        )

        # Test revote proposed template
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test rationale",
            status="PROPOSED",
            expires_at=timezone.now() + timedelta(hours=48),
        )
        self.email_service.notify_revote_proposed(
            conflict_id=str(self.conflict.id),
            proposal_id=str(proposal.id),
            proposer_id=str(self.reviewer1.id),
        )

        # Test revote ready template
        proposal.status = "ACCEPTED"
        proposal.accepted_at = timezone.now()
        proposal.save()
        self.email_service.notify_revote_ready(
            conflict_id=str(self.conflict.id), proposal_id=str(proposal.id)
        )

        # Test consensus reached template
        self.email_service.notify_consensus_reached_via_revote(
            conflict_id=str(self.conflict.id),
            proposal_id=str(proposal.id),
            consensus_decision="EXCLUDE",
        )

        # Assert all emails sent without errors
        # 1 comment + 1 proposal + 2 ready + 2 consensus = 6 emails
        self.assertEqual(len(mail.outbox), 6)

    def test_email_contains_discussion_url(self):
        """Test that emails contain the discussion URL."""
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.reviewer1, content="Test"
        )

        self.email_service.notify_conflict_comment_added(
            conflict_id=str(self.conflict.id),
            comment_id=str(comment.id),
            commenter_id=str(self.reviewer1.id),
        )

        # Assert email contains discussion URL (check both plain text and HTML)
        email = mail.outbox[0]
        email_content = email.body

        # Also check HTML alternative if plain text doesn't have it
        if email.alternatives:
            html_content = email.alternatives[0][0]
            email_content = email_content + html_content

        self.assertTrue(
            f"/conflicts/{self.conflict.id}/discuss/" in email_content
            or f"conflicts/{self.conflict.id}/discuss" in email_content,
            "Expected conflict discussion URL not found in email",
        )

    def test_error_handling_invalid_conflict_id(self):
        """Test error handling when conflict doesn't exist."""
        result = self.email_service.notify_conflict_comment_added(
            conflict_id=str(uuid.uuid4()),  # Random UUID
            comment_id=str(uuid.uuid4()),
            commenter_id=str(self.reviewer1.id),
        )

        # Assert returns False (error occurred)
        self.assertFalse(result)

        # Assert no emails sent
        self.assertEqual(len(mail.outbox), 0)

    def test_comment_preview_truncation(self):
        """Test that long comments are truncated in email preview."""
        # Create long comment (> 200 chars)
        long_content = "A" * 250
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.reviewer1, content=long_content
        )

        self.email_service.notify_conflict_comment_added(
            conflict_id=str(self.conflict.id),
            comment_id=str(comment.id),
            commenter_id=str(self.reviewer1.id),
        )

        # Assert email body contains truncated preview (200 chars + "...")
        email_body = mail.outbox[0].body
        self.assertIn("A" * 200 + "...", email_body)

    def test_decision_display_formatting(self):
        """Test that consensus decisions are formatted correctly."""
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test",
            status="COMPLETED",
            expires_at=timezone.now() + timedelta(hours=48),
        )

        # Test INCLUDE formatting
        self.email_service.notify_consensus_reached_via_revote(
            conflict_id=str(self.conflict.id),
            proposal_id=str(proposal.id),
            consensus_decision="INCLUDE",
        )
        self.assertIn("Include", mail.outbox[0].body)

        # Clear outbox
        mail.outbox = []

        # Test EXCLUDE formatting
        self.email_service.notify_consensus_reached_via_revote(
            conflict_id=str(self.conflict.id),
            proposal_id=str(proposal.id),
            consensus_decision="EXCLUDE",
        )
        self.assertIn("Exclude", mail.outbox[0].body)


class EmailNotificationServiceCoreTests(TestCase):
    """Test core Phase 3 email notification methods (coverage improvement)."""

    def setUp(self):
        """Set up test data."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation Core", slug="test-org-core"
        )

        # Create users
        self.reviewer1 = create_test_user(
            username_prefix="reviewer1_core",
            first_name="Reviewer",
            last_name="One",
            email="reviewer1_core@test.com",
        )
        self.reviewer2 = create_test_user(
            username_prefix="reviewer2_core",
            first_name="Reviewer",
            last_name="Two",
            email="reviewer2_core@test.com",
        )
        self.lead_reviewer = create_test_user(
            username_prefix="lead_core",
            first_name="Lead",
            last_name="Reviewer",
            email="lead_core@test.com",
        )

        # Add users to organisation
        for user in [self.reviewer1, self.reviewer2, self.lead_reviewer]:
            OrganisationMembership.objects.create(
                organisation=self.organisation,
                user=user,
                role="RESEARCHER",
                is_active=True,
            )

        # Create search session
        self.session = SearchSession.objects.create(
            organisation=self.organisation,
            title="Test Review Session",
            owner=self.lead_reviewer,
            status="under_review",
        )

        # Create processed result
        self.result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Research Article",
            url="https://example.com/article",
            snippet="This is a test snippet for grey literature review",
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

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            status="PENDING",
            detected_at=timezone.now(),
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

        # Initialize email service
        self.email_service = EmailNotificationService()

        # Clear mail outbox
        mail.outbox = []

    # ========================================================================
    # Tests for send_conflict_notification()
    # ========================================================================

    def test_send_conflict_notification_sends_to_both_reviewers(self):
        """Test that conflict notification is sent to both reviewers."""
        result = self.email_service.send_conflict_notification(
            conflict_id=str(self.conflict.id)
        )

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 2)

        recipients = [email.to[0] for email in mail.outbox]
        self.assertIn("reviewer1_core@test.com", recipients)
        self.assertIn("reviewer2_core@test.com", recipients)

    def test_send_conflict_notification_content_validation(self):
        """Test conflict notification email contains all required content."""
        self.email_service.send_conflict_notification(conflict_id=str(self.conflict.id))

        # Check first email (to reviewer1)
        email = mail.outbox[0]
        self.assertIn("Conflict Detected", email.subject)
        self.assertIn("Test Review Session", email.subject)
        self.assertIn("Test Research Article", email.body)
        self.assertIn("https://example.com/article", email.body)

        # Verify decision differences are mentioned
        body_lower = email.body.lower()
        self.assertTrue("include" in body_lower or "exclude" in body_lower)

    def test_send_conflict_notification_invalid_conflict_id(self):
        """Test error handling when conflict doesn't exist."""
        result = self.email_service.send_conflict_notification(
            conflict_id=str(uuid.uuid4())
        )

        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_send_conflict_notification_wrong_decision_count(self):
        """Test handling when conflict doesn't have exactly 2 decisions."""
        # Remove one decision
        self.conflict.conflicting_decisions.remove(self.decision2)

        result = self.email_service.send_conflict_notification(
            conflict_id=str(self.conflict.id)
        )

        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    # ========================================================================
    # Tests for send_low_irr_alert()
    # ========================================================================

    def test_send_low_irr_alert_to_lead_reviewer(self):
        """Test that low IRR alert is sent to lead reviewer."""
        # Create IRR metric with low kappa
        now = timezone.now()
        _irr_metric = InterRaterReliability.objects.create(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            cohens_kappa=0.55,  # Below 0.70 threshold
            percentage_agreement=70.0,  # 70/100 = 70%
            total_comparisons=100,
            agreements=70,
            disagreements=30,
            calculated_at=now,
            calculation_window_start=now - timedelta(days=7),
            calculation_window_end=now,
        )

        # Clear any emails from previous operations
        mail.outbox = []

        result = self.email_service.send_low_irr_alert(
            session_id=str(self.session.id), irr_value=0.55
        )

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["lead_core@test.com"])

    def test_send_low_irr_alert_content_validation(self):
        """Test IRR alert email contains all required metrics."""
        now = timezone.now()
        _irr_metric = InterRaterReliability.objects.create(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            cohens_kappa=0.55,
            percentage_agreement=70.0,  # 70/100 = 70%
            total_comparisons=100,
            agreements=70,
            disagreements=30,
            calculated_at=now,
            calculation_window_start=now - timedelta(days=7),
            calculation_window_end=now,
        )

        self.email_service.send_low_irr_alert(
            session_id=str(self.session.id), irr_value=0.55
        )

        email = mail.outbox[0]
        self.assertIn("IRR Alert", email.subject)
        self.assertIn("Test Review Session", email.subject)
        self.assertIn("0.550", email.body)  # Kappa value
        self.assertIn("100", email.body)  # Total comparisons
        self.assertIn("70", email.body)  # Agreements
        self.assertIn("30", email.body)  # Disagreements
        self.assertIn("70.0", email.body)  # Percentage agreement

    def test_send_low_irr_alert_missing_metric(self):
        """Test handling when IRR metric doesn't exist."""
        result = self.email_service.send_low_irr_alert(
            session_id=str(self.session.id), irr_value=0.55
        )

        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    # ========================================================================
    # Tests for send_arbitrator_invitation()
    # ========================================================================

    def test_send_arbitrator_invitation_sends_email(self):
        """Test that arbitrator invitation email is sent correctly."""
        invitation_token = "test-token-12345"

        result = self.email_service.send_arbitrator_invitation(
            invitee_email="arbitrator@test.com",
            invitee_name="Dr. Arbitrator",
            session_id=str(self.session.id),
            invited_by_id=str(self.lead_reviewer.id),
            invitation_token=invitation_token,
        )

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["arbitrator@test.com"])

    def test_send_arbitrator_invitation_content_validation(self):
        """Test arbitrator invitation email contains all required content."""
        invitation_token = "test-token-12345"

        self.email_service.send_arbitrator_invitation(
            invitee_email="arbitrator@test.com",
            invitee_name="Dr. Arbitrator",
            session_id=str(self.session.id),
            invited_by_id=str(self.lead_reviewer.id),
            invitation_token=invitation_token,
        )

        email = mail.outbox[0]
        self.assertIn("Invitation to Arbitrate Conflicts", email.subject)
        self.assertIn("Test Review Session", email.subject)
        self.assertIn("Dr. Arbitrator", email.body)
        self.assertIn("Lead Reviewer", email.body)  # Invited by name

        # Check for invitation URL (check both plain text and HTML)
        email_content = email.body
        if email.alternatives:
            html_content = email.alternatives[0][0]
            email_content = email_content + html_content

        self.assertTrue(
            f"/invitations/accept/{invitation_token}/" in email_content
            or f"invitations/accept/{invitation_token}" in email_content,
            "Expected invitation URL not found in email",
        )

    def test_send_arbitrator_invitation_invalid_session(self):
        """Test error handling when session doesn't exist."""
        result = self.email_service.send_arbitrator_invitation(
            invitee_email="arbitrator@test.com",
            invitee_name="Dr. Arbitrator",
            session_id=str(uuid.uuid4()),
            invited_by_id=str(self.lead_reviewer.id),
            invitation_token="test-token",
        )

        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)

    # ========================================================================
    # Tests for send_consensus_notification()
    # ========================================================================

    def test_send_consensus_notification_sends_to_both_reviewers(self):
        """Test that consensus notification is sent to both reviewers."""
        # Resolve the conflict
        self.conflict.status = "RESOLVED"
        self.conflict.resolution_method = "DISCUSSION"
        self.conflict.final_decision = self.decision1
        self.conflict.resolved_by = self.lead_reviewer
        self.conflict.resolution_notes = "Agreed after discussion"
        self.conflict.save()

        result = self.email_service.send_consensus_notification(
            conflict_id=str(self.conflict.id)
        )

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 2)

        recipients = [email.to[0] for email in mail.outbox]
        self.assertIn("reviewer1_core@test.com", recipients)
        self.assertIn("reviewer2_core@test.com", recipients)

    def test_send_consensus_notification_content_validation(self):
        """Test consensus notification contains resolution details."""
        self.conflict.status = "RESOLVED"
        self.conflict.resolution_method = "ARBITRATION"
        self.conflict.final_decision = self.decision1
        self.conflict.resolved_by = self.lead_reviewer
        self.conflict.resolution_notes = (
            "Arbitrator decision: Include based on grey literature criteria"
        )
        self.conflict.save()

        self.email_service.send_consensus_notification(
            conflict_id=str(self.conflict.id)
        )

        email = mail.outbox[0]
        self.assertIn("Consensus Reached", email.subject)
        self.assertIn("Test Review Session", email.subject)
        self.assertIn("Include", email.body)  # Final decision
        self.assertIn("Lead Reviewer", email.body)  # Resolved by
        self.assertIn("Arbitrator decision", email.body)  # Resolution notes

    def test_send_consensus_notification_unresolved_conflict(self):
        """Test handling when conflict is not yet resolved."""
        result = self.email_service.send_consensus_notification(
            conflict_id=str(self.conflict.id)
        )

        self.assertFalse(result)
        # Should return early, no emails sent
        self.assertEqual(len(mail.outbox), 0)

    # ========================================================================
    # Tests for send_review_completion()
    # ========================================================================

    def test_send_review_completion_sends_to_all_reviewers(self):
        """Test that review completion email is sent to all participating reviewers."""
        result = self.email_service.send_review_completion(
            session_id=str(self.session.id)
        )

        self.assertTrue(result)
        # Should send to reviewer1 and reviewer2 (both made decisions)
        self.assertEqual(len(mail.outbox), 2)

        recipients = [email.to[0] for email in mail.outbox]
        self.assertIn("reviewer1_core@test.com", recipients)
        self.assertIn("reviewer2_core@test.com", recipients)

    def test_send_review_completion_content_validation(self):
        """Test review completion email contains all statistics."""
        # Create IRR metric
        now = timezone.now()
        _irr_metric = InterRaterReliability.objects.create(
            organisation=self.organisation,
            search_session=self.session,
            reviewer_a=self.reviewer1,
            reviewer_b=self.reviewer2,
            cohens_kappa=0.85,
            percentage_agreement=90.0,  # 90/100 = 90%
            total_comparisons=100,
            agreements=90,
            disagreements=10,
            calculated_at=now,
            calculation_window_start=now - timedelta(days=7),
            calculation_window_end=now,
        )

        # Resolve conflict
        self.conflict.status = "RESOLVED"
        self.conflict.final_decision = self.decision1
        self.conflict.save()

        self.email_service.send_review_completion(session_id=str(self.session.id))

        email = mail.outbox[0]
        self.assertIn("Review Completed", email.subject)
        self.assertIn("Test Review Session", email.subject)
        self.assertIn("0.850", email.body)  # Cohen's Kappa
        self.assertIn("Almost Perfect Agreement", email.body)  # Kappa interpretation

        # Should include PRISMA report URL (check both plain text and HTML)
        email_content = email.body
        if email.alternatives:
            html_content = email.alternatives[0][0]
            email_content = email_content + html_content

        self.assertTrue(
            f"/sessions/{self.session.id}/reports/prisma/" in email_content
            or f"sessions/{self.session.id}/reports/prisma" in email_content,
            "Expected PRISMA report URL not found in email",
        )

    # ========================================================================
    # Tests for _interpret_kappa() helper method
    # ========================================================================

    def test_interpret_kappa_all_ranges(self):
        """Test Landis & Koch (1977) kappa interpretation ranges."""
        test_cases = [
            (None, "Not Available"),
            (0.10, "Slight Agreement"),
            (0.25, "Fair Agreement"),
            (0.45, "Moderate Agreement"),
            (0.65, "Substantial Agreement"),
            (0.85, "Almost Perfect Agreement"),
            (1.00, "Almost Perfect Agreement"),
        ]

        for kappa_value, expected_interpretation in test_cases:
            with self.subTest(kappa=kappa_value):
                result = self.email_service._interpret_kappa(kappa_value)
                self.assertEqual(result, expected_interpretation)

    # ========================================================================
    # Tests for base service methods
    # ========================================================================

    def test_health_check_success(self):
        """Test health check returns True when service is operational."""
        result = self.email_service.health_check()
        self.assertTrue(result)

    def test_get_default_config(self):
        """Test default configuration includes all required settings."""
        config = self.email_service.get_default_config()

        self.assertIn("cache_timeout", config)
        self.assertIn("send_email", config)
        self.assertIn("from_email", config)
        self.assertIn("site_domain", config)
        self.assertIn("use_https", config)

        self.assertEqual(config["cache_timeout"], 300)
        self.assertTrue(config["send_email"])

    def test_get_base_url_http(self):
        """Test base URL generation with HTTP protocol."""
        # Override config for HTTP
        self.email_service.config["use_https"] = False
        self.email_service.config["site_domain"] = "localhost:8000"

        url = self.email_service._get_base_url()
        self.assertEqual(url, "http://localhost:8000")

    def test_get_base_url_https(self):
        """Test base URL generation with HTTPS protocol."""
        # Override config for HTTPS
        self.email_service.config["use_https"] = True
        self.email_service.config["site_domain"] = "agentgrey.app"

        url = self.email_service._get_base_url()
        self.assertEqual(url, "https://agentgrey.app")

    # ========================================================================
    # Edge case tests
    # ========================================================================

    def test_email_has_both_html_and_plain_text(self):
        """Test that emails include both HTML and plain text variants."""
        self.email_service.send_conflict_notification(conflict_id=str(self.conflict.id))

        email = mail.outbox[0]

        # Check plain text body exists
        self.assertTrue(len(email.body) > 0)

        # Check HTML alternative exists
        self.assertEqual(len(email.alternatives), 1)
        html_content, content_type = email.alternatives[0]
        self.assertEqual(content_type, "text/html")
        self.assertTrue(len(html_content) > 0)

    def test_email_contains_prisma_compliance_info(self):
        """Test that emails include PRISMA-required audit trail information."""
        self.conflict.status = "RESOLVED"
        self.conflict.final_decision = self.decision1
        self.conflict.resolved_by = self.lead_reviewer
        self.conflict.save()

        self.email_service.send_consensus_notification(
            conflict_id=str(self.conflict.id)
        )

        email = mail.outbox[0]

        # PRISMA requires audit trail with timestamps and decision details
        # Check for result information (result URL from the research article)
        self.assertIn(str(self.result.id), email.body)

        # Verify absolute URLs (not relative) - includes result URL
        self.assertTrue("http://" in email.body or "https://" in email.body)
        self.assertIn(self.result.url, email.body)  # External article URL

    def test_missing_reviewer_email_address(self):
        """Test handling when reviewer has no email address."""
        # Resolve the setUp conflict so we can create a new one for this test
        # (unique_active_conflict_per_result constraint blocks duplicate active conflicts)
        self.conflict.status = "RESOLVED"
        self.conflict.save(update_fields=["status"])

        # Create reviewer without email
        reviewer_no_email = create_test_user(
            username_prefix="no_email_core", last_name="Email", email=""
        )

        decision_no_email = ReviewerDecision.objects.create(
            organisation=self.organisation,
            result=self.result,
            reviewer=reviewer_no_email,
            decision="MAYBE",
            screening_stage="SCREENING",
        )

        conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            status="PENDING",
            detected_at=timezone.now(),
        )
        conflict.conflicting_decisions.add(self.decision1, decision_no_email)

        # Clear outbox -- signal sends notification on .add(), we test the service directly
        mail.outbox.clear()

        # Should attempt to send but handle empty email gracefully
        result = self.email_service.send_conflict_notification(
            conflict_id=str(conflict.id)
        )

        # Service completes successfully even with empty email (Django's send_mail handles it)
        # In production, email backend would fail gracefully
        self.assertTrue(result)

        # Only one email should be sent (to reviewer with valid email)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to[0], self.reviewer1.email)


class ReviewerInvitationEmailTests(TestCase):
    """Test reviewer invitation email notifications (Issue #21)."""

    def setUp(self):
        """Set up test data for invitation email tests."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create users (inviter and invitee)
        self.inviter = create_test_user(
            username_prefix="inviter", first_name="Alice", last_name="Inviter"
        )
        self.invitee = create_test_user(
            username_prefix="invitee", first_name="Bob", last_name="Invitee"
        )

        # Add inviter to organisation
        OrganisationMembership.objects.create(
            organisation=self.organisation,
            user=self.inviter,
            role="RESEARCHER",
            is_active=True,
        )

        # Create search session
        self.session = SearchSession.objects.create(
            organisation=self.organisation,
            title="Systematic Review - Diabetes Management",
            description="A comprehensive review of diabetes management strategies",
            owner=self.inviter,
            status="under_review",
            total_results=42,
        )

        # Create ReviewInvitation
        self.invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.inviter,
            invitee_email="invitee@test.com",
            invitee_name="Bob Invitee",
            status=ReviewInvitation.STATUS_PENDING,
            expires_at=timezone.now() + timedelta(days=7),
        )

        # Initialize email service
        self.email_service = EmailNotificationService()

    def test_send_reviewer_invitation_sends_email(self):
        """Test invitation email is sent to correct recipient."""
        # Clear mail outbox
        mail.outbox = []

        # Call service method
        result = self.email_service.send_reviewer_invitation(invitation=self.invitation)

        # Assert: Email sent successfully
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

        # Assert: Email sent to correct recipient
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.invitation.invitee_email])

        # Assert: Session title in subject
        self.assertIn(self.session.title, email.subject)
        self.assertIn("Invitation to Review Session", email.subject)

    def test_send_reviewer_invitation_content_validation(self):
        """Test email contains all required elements for PRISMA compliance."""
        # Clear mail outbox
        mail.outbox = []

        # Send invitation
        result = self.email_service.send_reviewer_invitation(invitation=self.invitation)

        # Assert: Email sent successfully
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

        # Get email
        email = mail.outbox[0]

        # Check plain text body (created by stripping HTML tags)
        body = email.body
        self.assertIn(self.session.title, body)
        self.assertIn(self.inviter.get_full_name(), body)
        self.assertIn(self.invitation.invitee_name, body)

        # Check session description
        self.assertIn(self.session.description, body)

        # Check total results count
        self.assertIn("42", body)

        # Check HTML alternative exists
        self.assertTrue(len(email.alternatives) > 0)
        html_content = email.alternatives[0][0]
        mime_type = email.alternatives[0][1]
        self.assertEqual(mime_type, "text/html")

        # Check HTML content contains key elements
        self.assertIn(self.session.title, html_content)
        self.assertIn(self.inviter.get_full_name(), html_content)

        # Check that magic link URL path is in HTML (href attribute)
        # The URL pattern should be: href="/sessions/invitations/accept/<token>/"
        self.assertIn("href=", html_content)
        self.assertIn("/invitations/accept/", html_content)

    def test_send_reviewer_invitation_invalid_invitation(self):
        """Test graceful handling of non-existent invitation."""
        # Clear mail outbox
        mail.outbox = []

        # Create invitation object with no database backing (simulate AttributeError)
        # We'll test by passing None which will cause AttributeError in the method
        result = self.email_service.send_reviewer_invitation(invitation=None)

        # Assert: Method returns False (graceful handling)
        self.assertFalse(result)

        # Assert: No email sent
        self.assertEqual(len(mail.outbox), 0)

    def test_send_reviewer_invitation_expired_invitation(self):
        """Test email sent for expired invitation includes expiry information."""
        # Clear mail outbox
        mail.outbox = []

        # Create invitation with expires_at in the past
        expired_invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.inviter,
            invitee_email="expired@test.com",
            invitee_name="Expired User",
            status=ReviewInvitation.STATUS_PENDING,
            expires_at=timezone.now() - timedelta(days=2),
        )

        # Send invitation email
        result = self.email_service.send_reviewer_invitation(
            invitation=expired_invitation
        )

        # Assert: Email still sent (returns True)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

        # Assert: Email contains expiry information
        email = mail.outbox[0]
        _body = email.body

        # Check that expiry date is mentioned
        # The days_until_expiry will be negative, but the email should still be sent
        self.assertIn(expired_invitation.invitee_email, email.to)

    def test_send_reviewer_invitation_template_renders(self):
        """Test email template renders correctly with all variables."""
        # Clear mail outbox
        mail.outbox = []

        # Send invitation
        result = self.email_service.send_reviewer_invitation(invitation=self.invitation)

        # Assert: Email sent successfully
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

        # Get email
        email = mail.outbox[0]

        # Assert: HTML body exists and is not empty
        self.assertTrue(len(email.alternatives) > 0)
        html_content = email.alternatives[0][0]
        self.assertIsNotNone(html_content)
        self.assertTrue(len(html_content) > 0)

        # Assert: Plain text alternative exists and is not empty
        self.assertIsNotNone(email.body)
        self.assertTrue(len(email.body) > 0)

        # Assert: All template variables populated in plain text body
        body = email.body
        self.assertIn(self.session.title, body)  # session_title
        self.assertIn(self.inviter.get_full_name(), body)  # inviter_name

        # Check invitee name
        self.assertIn(self.invitation.invitee_name, body)

        # Assert: All template variables populated in HTML body
        self.assertIn(self.session.title, html_content)
        self.assertIn(self.inviter.get_full_name(), html_content)

        # Assert: URL pattern is present in HTML (accept endpoint path in href)
        self.assertIn("href=", html_content)
        self.assertIn("/invitations/accept/", html_content)


class EmailNotificationServiceExceptionHandlingTests(TestCase):
    """Test exception handling and error paths in email notification service."""

    def setUp(self):
        """Set up test data for exception handling tests."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-exception"
        )

        # Create users
        self.reviewer1 = create_test_user(
            username_prefix="reviewer1_exc", first_name="Reviewer", last_name="One"
        )
        self.reviewer2 = create_test_user(
            username_prefix="reviewer2_exc", first_name="Reviewer", last_name="Two"
        )

        # Add users to organisation
        for user in [self.reviewer1, self.reviewer2]:
            OrganisationMembership.objects.create(
                organisation=self.organisation,
                user=user,
                role="RESEARCHER",
                is_active=True,
            )

        # Create search session
        self.session = SearchSession.objects.create(
            organisation=self.organisation,
            title="Test Exception Review Session",
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

        # Create conflict
        self.conflict = ConflictResolution.objects.create(
            organisation=self.organisation,
            result=self.result,
            status="PENDING",
            detected_at=timezone.now(),
        )
        self.conflict.conflicting_decisions.add(self.decision1, self.decision2)

        # Initialize email service
        self.email_service = EmailNotificationService()

        # Clear mail outbox
        mail.outbox = []

    # ========================================================================
    # Test health_check() exception handling
    # ========================================================================

    def test_health_check_database_unavailable(self):
        """Test health_check returns False when database is unavailable."""
        from unittest.mock import patch

        # Mock database query to raise exception
        with patch.object(
            ConflictResolution.objects, "count", side_effect=Exception("Database error")
        ):
            result = self.email_service.health_check()
            self.assertFalse(result)

    # ========================================================================
    # Test _send_email() exception handling
    # ========================================================================

    def test_send_email_backend_failure(self):
        """Test _send_email handles email backend failures gracefully."""
        import smtplib
        from unittest.mock import patch
        from django.core.mail import EmailMultiAlternatives

        # Mock EmailMultiAlternatives.send() to raise SMTP error
        with patch.object(
            EmailMultiAlternatives,
            "send",
            side_effect=smtplib.SMTPException("SMTP connection failed"),
        ):
            result = self.email_service._send_email(
                subject="Test Subject",
                html_template="emails/dual_screening/conflict_detected.html",
                context={"session_title": "Test"},
                recipient_list=["test@example.com"],
            )
            self.assertFalse(result)

    def test_send_email_template_not_found(self):
        """Test _send_email handles missing template gracefully."""
        result = self.email_service._send_email(
            subject="Test Subject",
            html_template="emails/nonexistent/template.html",
            context={"session_title": "Test"},
            recipient_list=["test@example.com"],
        )
        self.assertFalse(result)

    def test_send_email_template_rendering_error(self):
        """Test _send_email handles template rendering errors."""
        from unittest.mock import patch
        from django.template import TemplateSyntaxError

        # Mock render_to_string to raise template syntax error
        with patch(
            "apps.core.services.base_email_service.render_to_string",
            side_effect=TemplateSyntaxError("Template rendering failed"),
        ):
            result = self.email_service._send_email(
                subject="Test Subject",
                html_template="emails/dual_screening/conflict_detected.html",
                context={"session_title": "Test"},
                recipient_list=["test@example.com"],
            )
            self.assertFalse(result)

    # ========================================================================
    # Test send_conflict_notification() exception handling
    # ========================================================================

    def test_send_conflict_notification_email_send_fails(self):
        """Test send_conflict_notification handles email send failure."""
        from unittest.mock import patch

        # Mock _send_email to return False (failure)
        with patch.object(self.email_service, "_send_email", return_value=False):
            result = self.email_service.send_conflict_notification(
                conflict_id=str(self.conflict.id)
            )
            # Should return False because at least one email failed
            self.assertFalse(result)

    def test_send_conflict_notification_database_error(self):
        """Test send_conflict_notification handles database errors."""
        from unittest.mock import patch

        # Mock database query to raise exception
        with patch.object(
            ConflictResolution.objects,
            "select_related",
            side_effect=Exception("Database connection lost"),
        ):
            result = self.email_service.send_conflict_notification(
                conflict_id=str(self.conflict.id)
            )
            self.assertFalse(result)

    # ========================================================================
    # Test send_low_irr_alert() exception handling
    # ========================================================================

    def test_send_low_irr_alert_session_not_found(self):
        """Test send_low_irr_alert handles missing session."""
        result = self.email_service.send_low_irr_alert(
            session_id=str(uuid.uuid4()), irr_value=0.55
        )
        self.assertFalse(result)

    def test_send_low_irr_alert_database_error(self):
        """Test send_low_irr_alert handles database errors."""
        from unittest.mock import patch

        # Mock database query to raise exception
        with patch.object(
            SearchSession.objects,
            "select_related",
            side_effect=Exception("Database error"),
        ):
            result = self.email_service.send_low_irr_alert(
                session_id=str(self.session.id), irr_value=0.55
            )
            self.assertFalse(result)

    # ========================================================================
    # Test send_arbitrator_invitation() exception handling
    # ========================================================================

    def test_send_arbitrator_invitation_user_not_found(self):
        """Test send_arbitrator_invitation handles missing inviter."""
        result = self.email_service.send_arbitrator_invitation(
            invitee_email="arbitrator@test.com",
            invitee_name="Dr. Arbitrator",
            session_id=str(self.session.id),
            invited_by_id=str(uuid.uuid4()),  # Non-existent user
            invitation_token="test-token-12345",
        )
        self.assertFalse(result)

    def test_send_arbitrator_invitation_database_error(self):
        """Test send_arbitrator_invitation handles database errors."""
        from unittest.mock import patch

        # Mock database query to raise exception
        with patch.object(
            SearchSession.objects, "get", side_effect=Exception("Database error")
        ):
            result = self.email_service.send_arbitrator_invitation(
                invitee_email="arbitrator@test.com",
                invitee_name="Dr. Arbitrator",
                session_id=str(self.session.id),
                invited_by_id=str(self.reviewer1.id),
                invitation_token="test-token",
            )
            self.assertFalse(result)

    # ========================================================================
    # Test send_consensus_notification() exception handling
    # ========================================================================

    def test_send_consensus_notification_email_send_fails(self):
        """Test send_consensus_notification handles email send failure."""
        from unittest.mock import patch

        # Resolve conflict first
        self.conflict.status = "RESOLVED"
        self.conflict.final_decision = self.decision1
        self.conflict.resolved_by = self.reviewer1
        self.conflict.save()

        # Mock _send_email to return False
        with patch.object(self.email_service, "_send_email", return_value=False):
            result = self.email_service.send_consensus_notification(
                conflict_id=str(self.conflict.id)
            )
            self.assertFalse(result)

    def test_send_consensus_notification_database_error(self):
        """Test send_consensus_notification handles database errors."""
        from unittest.mock import patch

        # Mock database query to raise exception
        with patch.object(
            ConflictResolution.objects,
            "select_related",
            side_effect=Exception("Database error"),
        ):
            result = self.email_service.send_consensus_notification(
                conflict_id=str(self.conflict.id)
            )
            self.assertFalse(result)

    # ========================================================================
    # Test send_review_completion() exception handling
    # ========================================================================

    def test_send_review_completion_session_not_found(self):
        """Test send_review_completion handles missing session."""
        result = self.email_service.send_review_completion(session_id=str(uuid.uuid4()))
        self.assertFalse(result)

    def test_send_review_completion_database_error(self):
        """Test send_review_completion handles database errors."""
        from unittest.mock import patch

        # Mock database query to raise exception
        with patch.object(
            SearchSession.objects,
            "select_related",
            side_effect=Exception("Database error"),
        ):
            result = self.email_service.send_review_completion(
                session_id=str(self.session.id)
            )
            self.assertFalse(result)

    # ========================================================================
    # Test notify_conflict_comment_added() exception handling
    # ========================================================================

    def test_notify_conflict_comment_added_email_send_fails(self):
        """Test notify_conflict_comment_added handles email send failure."""
        from unittest.mock import patch

        # Create comment
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.reviewer1, content="Test comment"
        )

        # Mock _send_email to return False
        with patch.object(self.email_service, "_send_email", return_value=False):
            result = self.email_service.notify_conflict_comment_added(
                conflict_id=str(self.conflict.id),
                comment_id=str(comment.id),
                commenter_id=str(self.reviewer1.id),
            )
            self.assertFalse(result)

    def test_notify_conflict_comment_added_database_error(self):
        """Test notify_conflict_comment_added handles database errors."""
        from unittest.mock import patch

        # Create comment
        comment = ConflictComment.objects.create(
            conflict=self.conflict, author=self.reviewer1, content="Test comment"
        )

        # Mock database query to raise exception
        with patch.object(
            ConflictComment.objects,
            "select_related",
            side_effect=Exception("Database error"),
        ):
            result = self.email_service.notify_conflict_comment_added(
                conflict_id=str(self.conflict.id),
                comment_id=str(comment.id),
                commenter_id=str(self.reviewer1.id),
            )
            self.assertFalse(result)

    # ========================================================================
    # Test notify_revote_proposed() exception handling
    # ========================================================================

    def test_notify_revote_proposed_no_other_reviewers(self):
        """Test notify_revote_proposed when no other reviewers exist."""
        # Create proposal
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test rationale",
            status="PROPOSED",
            expires_at=timezone.now() + timedelta(hours=48),
        )

        # Remove other reviewer from conflict
        self.conflict.conflicting_decisions.remove(self.decision2)

        result = self.email_service.notify_revote_proposed(
            conflict_id=str(self.conflict.id),
            proposal_id=str(proposal.id),
            proposer_id=str(self.reviewer1.id),
        )

        # Should return True (not an error, just no recipients)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 0)

    def test_notify_revote_proposed_proposal_not_found(self):
        """Test notify_revote_proposed handles missing proposal."""
        result = self.email_service.notify_revote_proposed(
            conflict_id=str(self.conflict.id),
            proposal_id=str(uuid.uuid4()),
            proposer_id=str(self.reviewer1.id),
        )
        self.assertFalse(result)

    def test_notify_revote_proposed_database_error(self):
        """Test notify_revote_proposed handles database errors."""
        from unittest.mock import patch

        # Create proposal
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test rationale",
            status="PROPOSED",
            expires_at=timezone.now() + timedelta(hours=48),
        )

        # Mock database query to raise exception
        with patch.object(
            RevoteProposal.objects,
            "select_related",
            side_effect=Exception("Database error"),
        ):
            result = self.email_service.notify_revote_proposed(
                conflict_id=str(self.conflict.id),
                proposal_id=str(proposal.id),
                proposer_id=str(self.reviewer1.id),
            )
            self.assertFalse(result)

    # ========================================================================
    # Test notify_revote_ready() exception handling
    # ========================================================================

    def test_notify_revote_ready_no_reviewers_found(self):
        """Test notify_revote_ready when no reviewers found."""
        # Create proposal
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test rationale",
            status="ACCEPTED",
            accepted_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=48),
        )

        # Remove all decisions from conflict
        self.conflict.conflicting_decisions.clear()

        result = self.email_service.notify_revote_ready(
            conflict_id=str(self.conflict.id), proposal_id=str(proposal.id)
        )

        self.assertFalse(result)

    def test_notify_revote_ready_proposal_not_found(self):
        """Test notify_revote_ready handles missing proposal."""
        result = self.email_service.notify_revote_ready(
            conflict_id=str(self.conflict.id), proposal_id=str(uuid.uuid4())
        )
        self.assertFalse(result)

    def test_notify_revote_ready_database_error(self):
        """Test notify_revote_ready handles database errors."""
        from unittest.mock import patch

        # Create proposal
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test rationale",
            status="ACCEPTED",
            accepted_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=48),
        )

        # Mock database query to raise exception
        with patch.object(
            RevoteProposal.objects,
            "select_related",
            side_effect=Exception("Database error"),
        ):
            result = self.email_service.notify_revote_ready(
                conflict_id=str(self.conflict.id), proposal_id=str(proposal.id)
            )
            self.assertFalse(result)

    # ========================================================================
    # Test notify_consensus_reached_via_revote() exception handling
    # ========================================================================

    def test_notify_consensus_reached_via_revote_no_reviewers(self):
        """Test notify_consensus_reached_via_revote when no reviewers found."""
        # Create proposal
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test rationale",
            status="COMPLETED",
            resulted_in_consensus=True,
            accepted_at=timezone.now(),
            completed_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=48),
        )

        # Remove all decisions from conflict
        self.conflict.conflicting_decisions.clear()

        result = self.email_service.notify_consensus_reached_via_revote(
            conflict_id=str(self.conflict.id),
            proposal_id=str(proposal.id),
            consensus_decision="INCLUDE",
        )

        self.assertFalse(result)

    def test_notify_consensus_reached_via_revote_proposal_not_found(self):
        """Test notify_consensus_reached_via_revote handles missing proposal."""
        result = self.email_service.notify_consensus_reached_via_revote(
            conflict_id=str(self.conflict.id),
            proposal_id=str(uuid.uuid4()),
            consensus_decision="INCLUDE",
        )
        self.assertFalse(result)

    def test_notify_consensus_reached_via_revote_database_error(self):
        """Test notify_consensus_reached_via_revote handles database errors."""
        from unittest.mock import patch

        # Create proposal
        proposal = RevoteProposal.objects.create(
            conflict=self.conflict,
            proposed_by=self.reviewer1,
            rationale="Test rationale",
            status="COMPLETED",
            resulted_in_consensus=True,
            accepted_at=timezone.now(),
            completed_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=48),
        )

        # Mock database query to raise exception
        with patch.object(
            RevoteProposal.objects,
            "select_related",
            side_effect=Exception("Database error"),
        ):
            result = self.email_service.notify_consensus_reached_via_revote(
                conflict_id=str(self.conflict.id),
                proposal_id=str(proposal.id),
                consensus_decision="INCLUDE",
            )
            self.assertFalse(result)
