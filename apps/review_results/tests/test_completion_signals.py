"""
Tests for ReviewerCompletion signal handlers (Phase 2: Completion Tracking Integration).

Tests the automatic creation and updating of ReviewerCompletion records via signals:
- create_reviewer_completion_on_acceptance: Creates ReviewerCompletion when invitation accepted
- update_reviewer_completion_progress: Updates progress when SimpleReviewDecision saved
"""

from django.test import TestCase
from django.utils import timezone

from apps.organisation.models import Organisation
from apps.review_manager.models import SearchSession, ReviewInvitation
from apps.review_results.models import (
    ReviewerCompletion,
    ReviewerDecision,
    SimpleReviewDecision,
)
from apps.core.tests.utils import create_test_user
from apps.results_manager.models import ProcessedResult


class ReviewerCompletionSignalTest(TestCase):
    """Test signal handlers for automatic ReviewerCompletion tracking."""

    def setUp(self):
        """Set up test data for signal tests."""
        # Create test users
        self.owner = create_test_user(
            username_prefix="owner", first_name="Owner", last_name="User"
        )
        self.invitee = create_test_user(
            username_prefix="invitee", first_name="Invited", last_name="Reviewer"
        )

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test session for signal testing",
            owner=self.owner,
            status="ready_for_review",
            total_results=10,
        )

        # Create test results
        self.results = []
        for i in range(10):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"https://example.com/{i + 1}",
                snippet=f"Test snippet {i + 1}",
            )
            self.results.append(result)

    def test_reviewer_completion_created_on_invitation_acceptance(self):
        """Test that ReviewerCompletion is automatically created when invitation is accepted."""
        # Create invitation in PENDING status
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee_email="invitee@example.com",
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Verify no ReviewerCompletion exists yet
        self.assertFalse(
            ReviewerCompletion.objects.filter(invitation=invitation).exists()
        )

        # Accept invitation (this should trigger the signal)
        invitation.invitee = self.invitee
        invitation.status = ReviewInvitation.STATUS_ACCEPTED
        invitation.responded_at = timezone.now()
        invitation.save()

        # Verify ReviewerCompletion was created
        self.assertTrue(
            ReviewerCompletion.objects.filter(invitation=invitation).exists()
        )

        completion = ReviewerCompletion.objects.get(invitation=invitation)
        self.assertEqual(completion.session, self.session)
        self.assertEqual(completion.reviewer, self.invitee)
        self.assertEqual(completion.total_results, 10)
        self.assertEqual(completion.reviewed_results, 0)
        self.assertFalse(completion.is_complete)

    def test_reviewer_completion_not_created_for_pending_invitation(self):
        """Test that ReviewerCompletion is NOT created for PENDING invitations."""
        # Create invitation in PENDING status
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee_email="invitee@example.com",
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Save again (shouldn't trigger completion creation)
        invitation.save()

        # Verify no ReviewerCompletion exists
        self.assertFalse(
            ReviewerCompletion.objects.filter(invitation=invitation).exists()
        )

    def test_reviewer_completion_not_duplicated_on_subsequent_saves(self):
        """Test that ReviewerCompletion is not duplicated on subsequent saves of accepted invitation."""
        # Create and accept invitation
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.invitee,
            invitee_email="invitee@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        # Verify one ReviewerCompletion exists
        self.assertEqual(
            ReviewerCompletion.objects.filter(invitation=invitation).count(), 1
        )

        # Save invitation again
        invitation.save()

        # Verify still only one ReviewerCompletion exists
        self.assertEqual(
            ReviewerCompletion.objects.filter(invitation=invitation).count(), 1
        )

    def test_progress_updated_on_decision_save(self):
        """Test that ReviewerCompletion progress is updated when SimpleReviewDecision is saved."""
        # Create accepted invitation and ReviewerCompletion
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.invitee,
            invitee_email="invitee@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        completion = ReviewerCompletion.objects.get(invitation=invitation)
        self.assertEqual(completion.reviewed_results, 0)

        # Create a decision (this should trigger progress update)
        SimpleReviewDecision.objects.create(
            result=self.results[0],
            session=self.session,
            reviewer=self.invitee,
            decision="include",
        )

        # Verify progress updated
        completion.refresh_from_db()
        self.assertEqual(completion.reviewed_results, 1)
        self.assertFalse(completion.is_complete)

        # Create more decisions
        for i in range(1, 5):
            SimpleReviewDecision.objects.create(
                result=self.results[i],
                session=self.session,
                reviewer=self.invitee,
                decision="include",
            )

        # Verify progress updated again
        completion.refresh_from_db()
        self.assertEqual(completion.reviewed_results, 5)
        self.assertFalse(completion.is_complete)

    def test_completion_marked_complete_when_all_results_reviewed(self):
        """Test that ReviewerCompletion is marked complete when all results are reviewed."""
        # Create accepted invitation and ReviewerCompletion
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.invitee,
            invitee_email="invitee@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        completion = ReviewerCompletion.objects.get(invitation=invitation)

        # Review all results
        for i in range(10):
            SimpleReviewDecision.objects.create(
                result=self.results[i],
                session=self.session,
                reviewer=self.invitee,
                decision="include" if i % 2 == 0 else "exclude",
                exclusion_reason="not_relevant" if i % 2 != 0 else "",
            )

        # Verify completion marked as complete
        completion.refresh_from_db()
        self.assertEqual(completion.reviewed_results, 10)
        self.assertTrue(completion.is_complete)
        self.assertIsNotNone(completion.completed_at)

    def test_no_error_when_updating_progress_for_non_invited_reviewer(self):
        """Test that no error occurs when updating progress for reviewer without ReviewerCompletion."""
        # Create a decision for session owner (who is NOT invited)
        # This should not cause an error, just silently skip
        _decision = SimpleReviewDecision.objects.create(
            result=self.results[0],
            session=self.session,
            reviewer=self.owner,  # Owner, not invited reviewer
            decision="include",
        )

        # Verify no ReviewerCompletion exists for owner
        self.assertFalse(
            ReviewerCompletion.objects.filter(
                session=self.session, reviewer=self.owner
            ).exists()
        )

        # Test passes if no exception is raised

    def test_progress_percentage_calculation(self):
        """Test that progress_percentage property is calculated correctly."""
        # Create accepted invitation
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.invitee,
            invitee_email="invitee@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        completion = ReviewerCompletion.objects.get(invitation=invitation)

        # Test 0% progress
        self.assertEqual(completion.progress_percentage, 0)

        # Review 5 of 10 results (50%)
        for i in range(5):
            SimpleReviewDecision.objects.create(
                result=self.results[i],
                session=self.session,
                reviewer=self.invitee,
                decision="include",
            )

        completion.refresh_from_db()
        self.assertEqual(completion.progress_percentage, 50.0)

        # Review remaining 5 results (100%)
        for i in range(5, 10):
            SimpleReviewDecision.objects.create(
                result=self.results[i],
                session=self.session,
                reviewer=self.invitee,
                decision="exclude",
                exclusion_reason="not_relevant",
            )

        completion.refresh_from_db()
        self.assertEqual(completion.progress_percentage, 100.0)

    def test_multiple_reviewers_tracked_independently(self):
        """Test that multiple invited reviewers are tracked independently.

        Note: SimpleReviewDecision has OneToOne relationship with ProcessedResult,
        so each result can only have one decision. In real dual-screening workflow,
        ReviewerDecision is used (many decisions per result). This test validates
        that ReviewerCompletion tracks each reviewer independently when they
        review different subsets of results.
        """
        # Create second invitee
        invitee2 = create_test_user(username_prefix="invitee2")

        # Create and accept invitations for both reviewers
        invitation1 = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.invitee,
            invitee_email="invitee@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        invitation2 = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=invitee2,
            invitee_email="invitee2@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        # Reviewer 1 reviews first 3 results (0-2)
        for i in range(3):
            SimpleReviewDecision.objects.create(
                result=self.results[i],
                session=self.session,
                reviewer=self.invitee,
                decision="include",
            )

        # Reviewer 2 reviews different 7 results (3-9)
        # Note: Each result can only have ONE SimpleReviewDecision (OneToOne)
        for i in range(3, 10):
            SimpleReviewDecision.objects.create(
                result=self.results[i],
                session=self.session,
                reviewer=invitee2,
                decision="include",
            )

        # Verify independent tracking
        completion1 = ReviewerCompletion.objects.get(invitation=invitation1)
        completion2 = ReviewerCompletion.objects.get(invitation=invitation2)

        self.assertEqual(completion1.reviewed_results, 3)
        self.assertEqual(completion1.progress_percentage, 30.0)
        self.assertFalse(completion1.is_complete)

        self.assertEqual(completion2.reviewed_results, 7)
        self.assertEqual(completion2.progress_percentage, 70.0)
        self.assertFalse(completion2.is_complete)


class ReviewerCompletionEdgeCaseTest(TestCase):
    """Test edge cases and error handling for ReviewerCompletion signals."""

    def setUp(self):
        """Set up test data."""
        self.owner = create_test_user(username_prefix="owner")
        self.invitee = create_test_user(username_prefix="invitee")

    def test_completion_handles_session_with_zero_results(self):
        """Test ReviewerCompletion created for session with 0 results."""
        # Create session with 0 results
        session = SearchSession.objects.create(
            title="Empty Session",
            owner=self.owner,
            status="ready_for_review",
            total_results=0,
        )

        # Create and accept invitation
        invitation = ReviewInvitation.objects.create(
            session=session,
            inviter=self.owner,
            invitee=self.invitee,
            invitee_email="invitee@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        # Verify ReviewerCompletion created
        completion = ReviewerCompletion.objects.get(invitation=invitation)
        self.assertEqual(completion.total_results, 0)
        self.assertEqual(completion.reviewed_results, 0)
        self.assertEqual(completion.progress_percentage, 0)
        # Note: is_complete should be False even with 0/0 because completed_at is None
        self.assertFalse(completion.is_complete)

    def test_declined_invitation_does_not_create_completion(self):
        """Test that declining invitation doesn't create ReviewerCompletion."""
        session = SearchSession.objects.create(
            title="Test Session",
            owner=self.owner,
            status="ready_for_review",
            total_results=5,
        )

        # Create invitation and decline it
        invitation = ReviewInvitation.objects.create(
            session=session,
            inviter=self.owner,
            invitee_email="invitee@example.com",
            status=ReviewInvitation.STATUS_PENDING,
        )

        invitation.status = ReviewInvitation.STATUS_DECLINED
        invitation.responded_at = timezone.now()
        invitation.save()

        # Verify no ReviewerCompletion created
        self.assertFalse(
            ReviewerCompletion.objects.filter(invitation=invitation).exists()
        )


class ReviewerDecisionSignalTest(TestCase):
    """Test signal handlers for ReviewerDecision (Workflow #2: Independent Screening)."""

    def setUp(self):
        """Set up test data for ReviewerDecision signal tests."""
        # Create organisation
        self.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create test users
        self.owner = create_test_user(
            username_prefix="owner", first_name="Owner", last_name="User"
        )
        self.reviewer = create_test_user(
            username_prefix="reviewer1", first_name="Invited", last_name="Reviewer"
        )

        # Create test session (dual-screening workflow)
        self.session = SearchSession.objects.create(
            title="Test Dual Screening Session",
            description="Test session for dual-screening signal testing",
            owner=self.owner,
            status="under_review",
            total_results=5,
        )

        # Create test results
        self.results = []
        for i in range(5):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Test Result {i + 1}",
                url=f"https://example.com/{i + 1}",
                snippet=f"Test snippet {i + 1}",
            )
            self.results.append(result)

    def test_signal_fires_for_reviewer_decision(self):
        """Test signal updates progress for ReviewerDecision (Workflow #2)."""
        # Create ReviewerCompletion via invitation pattern
        _invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.reviewer,
            invitee_email="reviewer1@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        # ReviewerCompletion created by invitation acceptance signal
        completion = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer
        )

        # Initial state
        self.assertEqual(completion.reviewed_results, 0)

        # Create ReviewerDecision (triggers signal)
        ReviewerDecision.objects.create(
            result=self.results[0],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="INCLUDE",
            notes="Meets inclusion criteria",
        )

        # Refresh and verify progress updated
        completion.refresh_from_db()
        self.assertEqual(completion.reviewed_results, 1)

        # Create another decision on different result
        ReviewerDecision.objects.create(
            result=self.results[1],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="EXCLUDE",
            exclusion_reason="Does not meet criteria",
            notes="Out of scope",
        )

        completion.refresh_from_db()
        self.assertEqual(completion.reviewed_results, 2)

    def test_signal_counts_distinct_results_not_total_decisions(self):
        """
        Test signal counts distinct results, not total decision count.

        This is critical for Workflow #2 where reviewers may revote on same result.
        """
        _invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.reviewer,
            invitee_email="reviewer1@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        # Create multiple decisions on same result (revote scenario)
        ReviewerDecision.objects.create(
            result=self.results[0],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="INCLUDE",
            notes="Initial decision",
            is_revote=False,
        )

        # Reviewer changes their mind (re-vote during consensus)
        ReviewerDecision.objects.create(
            result=self.results[0],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="EXCLUDE",
            exclusion_reason="Changed after discussion",
            notes="Re-evaluated criteria",
            is_revote=True,  # This is a re-vote
        )

        completion = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer
        )

        # Should count 1 result (not 2 decisions)
        # Re-vote decisions are excluded from progress tracking
        self.assertEqual(completion.reviewed_results, 1)

        # Now vote on a different result
        ReviewerDecision.objects.create(
            result=self.results[1],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="INCLUDE",
            notes="Clear inclusion",
            is_revote=False,
        )

        completion.refresh_from_db()
        self.assertEqual(completion.reviewed_results, 2)  # 2 distinct results

    def test_signal_excludes_revote_decisions_from_progress(self):
        """Test signal only counts initial decisions (is_revote=False)."""
        _invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.reviewer,
            invitee_email="reviewer1@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        # Create initial decision
        ReviewerDecision.objects.create(
            result=self.results[0],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="INCLUDE",
            notes="Initial screening decision",
            is_revote=False,
        )

        completion = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer
        )
        self.assertEqual(completion.reviewed_results, 1)

        # Create re-vote decision on same result
        ReviewerDecision.objects.create(
            result=self.results[0],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="EXCLUDE",
            exclusion_reason="Changed during consensus",
            notes="Re-vote after discussion",
            is_revote=True,
        )

        completion.refresh_from_db()
        # Should still count 1 (re-vote excluded from progress)
        self.assertEqual(completion.reviewed_results, 1)

    def test_signal_auto_completes_workflow2(self):
        """Test auto-completion for ReviewerDecision workflow."""
        _invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.reviewer,
            invitee_email="reviewer1@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        completion = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer
        )

        # Initially not complete
        self.assertIsNone(completion.completed_at)

        # Review all 5 results
        for result in self.results:
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.reviewer,
                organisation=self.organisation,
                decision="INCLUDE",
                notes="Test decision",
                is_revote=False,
            )

        # Verify auto-completion
        completion.refresh_from_db()
        self.assertEqual(completion.reviewed_results, 5)
        self.assertIsNotNone(completion.completed_at)
        self.assertTrue(completion.is_complete)

    def test_signal_handles_multiple_reviewers_independently_workflow2(self):
        """Test signal tracks progress for multiple reviewers independently (Workflow #2)."""
        reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create invitations for both reviewers
        ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.reviewer,
            invitee_email="reviewer1@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )
        ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=reviewer2,
            invitee_email="reviewer2@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        # Reviewer 1 reviews result 1
        ReviewerDecision.objects.create(
            result=self.results[0],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="INCLUDE",
            notes="Test",
            is_revote=False,
        )

        # Reviewer 2 reviews results 1 and 2 (both can review same results in Workflow #2)
        ReviewerDecision.objects.create(
            result=self.results[0],
            reviewer=reviewer2,
            organisation=self.organisation,
            decision="EXCLUDE",
            notes="Test",
            is_revote=False,
        )
        ReviewerDecision.objects.create(
            result=self.results[1],
            reviewer=reviewer2,
            organisation=self.organisation,
            decision="INCLUDE",
            notes="Test",
            is_revote=False,
        )

        # Verify independent progress tracking
        completion1 = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer
        )
        completion2 = ReviewerCompletion.objects.get(
            session=self.session, reviewer=reviewer2
        )

        self.assertEqual(completion1.reviewed_results, 1)  # Reviewer 1: 1 result
        self.assertEqual(completion2.reviewed_results, 2)  # Reviewer 2: 2 results

    def test_signal_handles_mixed_initial_and_revote_decisions(self):
        """Test signal correctly handles mix of initial and re-vote decisions."""
        _invitation = ReviewInvitation.objects.create(
            session=self.session,
            inviter=self.owner,
            invitee=self.reviewer,
            invitee_email="reviewer1@example.com",
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        # Initial screening: review 3 results
        for i in range(3):
            ReviewerDecision.objects.create(
                result=self.results[i],
                reviewer=self.reviewer,
                organisation=self.organisation,
                decision="INCLUDE",
                notes="Initial decision",
                is_revote=False,
            )

        completion = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.reviewer
        )
        self.assertEqual(completion.reviewed_results, 3)

        # Re-vote on results 0 and 1 during consensus
        ReviewerDecision.objects.create(
            result=self.results[0],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="EXCLUDE",
            notes="Changed mind",
            is_revote=True,
        )
        ReviewerDecision.objects.create(
            result=self.results[1],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="EXCLUDE",
            notes="Changed mind",
            is_revote=True,
        )

        completion.refresh_from_db()
        # Still 3 results (re-votes don't change progress)
        self.assertEqual(completion.reviewed_results, 3)

        # Continue initial screening: review result 3
        ReviewerDecision.objects.create(
            result=self.results[3],
            reviewer=self.reviewer,
            organisation=self.organisation,
            decision="INCLUDE",
            notes="Initial decision",
            is_revote=False,
        )

        completion.refresh_from_db()
        # Now 4 results reviewed
        self.assertEqual(completion.reviewed_results, 4)
