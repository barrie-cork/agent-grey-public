"""
Tests for review completion workflow with invited reviewers.

Ensures that sessions cannot be completed until all invited reviewers
have finished their work, preventing premature transitions to reporting phase.
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.review_manager.models import SearchSession, ReviewInvitation
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import SimpleReviewDecision
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ReviewCompletionWorkflowTest(TestCase):
    """Test review completion validation with invited reviewers."""

    def setUp(self):
        """Set up test data."""
        # Create users
        self.owner = create_test_user(username_prefix="owner")
        self.invited_reviewer = create_test_user(username_prefix="invited")

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.owner,
            status="under_review",
        )

        # Create test results
        self.results = []
        for i in range(5):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i}",
                snippet="Test snippet",
                url=f"http://test.com/{i}",
            )
            self.results.append(result)

        # Create invitation (accepted)
        self.invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.invited_reviewer,
            invitee_email="invited@test.com",
            invitee_name="Invited Reviewer",
            token="test-token-123",
            status=ReviewInvitation.STATUS_ACCEPTED,
            invited_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=7),
            responded_at=timezone.now(),
        )

        # Set up client
        self.client = Client()

    def test_cannot_complete_with_pending_invited_reviewer(self):
        """Test that session cannot be completed if invited reviewer hasn't finished."""
        # Owner reviews all results
        for result in self.results:
            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.owner,
                decision="include",
            )

        # Try to complete review
        self.client.login(username=self.owner.username, password="testpass123")
        response = self.client.post(
            reverse("review_results:complete_review", args=[self.session.id])
        )

        # Should redirect back to overview with error
        self.assertEqual(response.status_code, 302)
        self.assertIn("overview", response.url)

        # Check session is still under review
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "under_review")

    def test_cannot_complete_with_partial_invited_reviewer_progress(self):
        """Test that session cannot be completed if invited reviewer only partially finished.

        Note: SimpleReviewDecision has OneToOne relationship with ProcessedResult,
        so owner and invited reviewer review different subsets of results.
        """
        # Owner reviews first 2 results (results 0-1)
        for result in self.results[:2]:
            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.owner,
                decision="include",
            )

        # Invited reviewer only reviews 3 out of 5 results (results 2-4)
        # This leaves total unreviewed, but invited reviewer hasn't finished all 5
        for i in range(2, 5):
            SimpleReviewDecision.objects.create(
                result=self.results[i],
                session=self.session,
                reviewer=self.invited_reviewer,
                decision="exclude",
                exclusion_reason="not_relevant",
            )

        # Try to complete review
        self.client.login(username=self.owner.username, password="testpass123")
        response = self.client.post(
            reverse("review_results:complete_review", args=[self.session.id])
        )

        # Should redirect back to overview with error (invited reviewer needs to review all 5)
        self.assertEqual(response.status_code, 302)
        self.assertIn("overview", response.url)

        # Check session is still under review
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "under_review")

    def test_can_complete_when_all_reviewers_finished(self):
        """Test that session can be completed when all reviewers (owner + invited) finished.

        Note: SimpleReviewDecision has OneToOne relationship with ProcessedResult,
        so each result can only have one decision. The invited reviewer reviewing all
        5 results means they've completed their assigned work.
        """
        # Invited reviewer reviews all 5 results
        # (In single-reviewer workflow, invited reviewers work independently)
        for result in self.results:
            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.invited_reviewer,
                decision="exclude",
                exclusion_reason="not_relevant",
            )

        # Try to complete review
        self.client.login(username=self.owner.username, password="testpass123")
        response = self.client.post(
            reverse("review_results:complete_review", args=[self.session.id])
        )

        # Should redirect to reporting dashboard
        self.assertEqual(response.status_code, 302)
        self.assertIn("reporting", response.url)

        # Check session is completed
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")

    def test_can_complete_with_no_invited_reviewers(self):
        """Test that session can be completed when there are no invited reviewers."""
        # Delete the invitation
        self.invitation.delete()

        # Owner reviews all results
        for result in self.results:
            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.owner,
                decision="include",
            )

        # Try to complete review
        self.client.login(username=self.owner.username, password="testpass123")
        response = self.client.post(
            reverse("review_results:complete_review", args=[self.session.id])
        )

        # Should redirect to reporting dashboard
        self.assertEqual(response.status_code, 302)
        self.assertIn("reporting", response.url)

        # Check session is completed
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")

    def test_blocks_completion_with_pending_invitations(self):
        """Test that PENDING invitations block completion."""
        # Change invitation to PENDING (not yet accepted)
        self.invitation.status = ReviewInvitation.STATUS_PENDING
        self.invitation.invitee = None  # Not yet accepted
        self.invitation.save()

        # Owner reviews all results
        for result in self.results:
            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.owner,
                decision="include",
            )

        # Try to complete review
        self.client.login(username=self.owner.username, password="testpass123")
        response = self.client.post(
            reverse("review_results:complete_review", args=[self.session.id])
        )

        # Should redirect back to overview with error (PENDING invitations block completion)
        self.assertEqual(response.status_code, 302)
        self.assertIn("overview", response.url)

        # Check session is still under review
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "under_review")

    def test_ignores_declined_invitations(self):
        """Test that DECLINED invitations don't block completion."""
        # Change invitation to DECLINED
        self.invitation.status = ReviewInvitation.STATUS_DECLINED
        self.invitation.save()

        # Owner reviews all results
        for result in self.results:
            SimpleReviewDecision.objects.create(
                result=result,
                session=self.session,
                reviewer=self.owner,
                decision="include",
            )

        # Try to complete review
        self.client.login(username=self.owner.username, password="testpass123")
        response = self.client.post(
            reverse("review_results:complete_review", args=[self.session.id])
        )

        # Should redirect to reporting dashboard (DECLINED invitations are ignored)
        self.assertEqual(response.status_code, 302)
        self.assertIn("reporting", response.url)

        # Check session is completed
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")
