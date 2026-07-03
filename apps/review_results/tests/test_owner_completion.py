"""Tests for session owner ReviewerCompletion tracking in dual-screening workflow."""

from django.test import TestCase
from django.urls import reverse

from apps.organisation.models import Organisation
from apps.review_manager.models import SearchSession, ReviewConfiguration
from apps.review_results.models import ReviewerCompletion, ReviewerDecision
from apps.results_manager.models import ProcessedResult
from apps.core.tests.utils import create_test_user


class OwnerCompletionCreationTest(TestCase):
    """Test automatic creation of owner completion records."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Test Org", slug="test-org")
        self.owner = create_test_user(username_prefix="owner")
        self.owner.organisation = self.org
        self.owner.save()

    def test_owner_completion_created_when_workflow2_session_reaches_ready_for_review(
        self,
    ):
        """Test ReviewerCompletion created for owner in Workflow #2."""
        # Create session in earlier state
        session = SearchSession.objects.create(
            title="Test Session",
            owner=self.owner,
            organisation=self.org,
            status="processing_results",
            total_results=10,
        )

        # Create Workflow #2 configuration
        config = ReviewConfiguration.objects.create(
            session=session,
            min_reviewers_per_result=2,
            created_by=self.owner,
            organisation=self.org,
        )
        session.current_configuration = config
        session.save()

        # Verify no completion exists yet
        self.assertFalse(
            ReviewerCompletion.objects.filter(
                session=session, reviewer=self.owner
            ).exists()
        )

        # Transition to ready_for_review
        session.status = "ready_for_review"
        session.save(update_fields=["status"])

        # Verify completion created for owner
        self.assertTrue(
            ReviewerCompletion.objects.filter(
                session=session, reviewer=self.owner
            ).exists()
        )

        completion = ReviewerCompletion.objects.get(
            session=session, reviewer=self.owner
        )
        self.assertIsNone(completion.invitation)
        self.assertEqual(completion.total_results, 10)
        self.assertEqual(completion.reviewed_results, 0)
        self.assertTrue(completion.is_owner_record)

    def test_owner_completion_not_created_for_workflow1(self):
        """Test no ReviewerCompletion created for owner in Workflow #1."""
        session = SearchSession.objects.create(
            title="Test Session",
            owner=self.owner,
            organisation=self.org,
            status="processing_results",
            total_results=10,
        )

        # Create Workflow #1 configuration
        config = ReviewConfiguration.objects.create(
            session=session,
            min_reviewers_per_result=1,
            created_by=self.owner,
            organisation=self.org,
        )
        session.current_configuration = config
        session.save()

        # Transition to ready_for_review
        session.status = "ready_for_review"
        session.save(update_fields=["status"])

        # Verify no completion created
        self.assertFalse(
            ReviewerCompletion.objects.filter(
                session=session, reviewer=self.owner
            ).exists()
        )

    def test_owner_completion_not_duplicated(self):
        """Test owner completion not duplicated on subsequent saves."""
        session = SearchSession.objects.create(
            title="Test Session",
            owner=self.owner,
            organisation=self.org,
            status="processing_results",
            total_results=10,
        )

        config = ReviewConfiguration.objects.create(
            session=session,
            min_reviewers_per_result=2,
            created_by=self.owner,
            organisation=self.org,
        )
        session.current_configuration = config
        session.save()

        # Transition to ready_for_review
        session.status = "ready_for_review"
        session.save(update_fields=["status"])

        # Save again
        session.save()

        # Verify only one completion exists
        self.assertEqual(
            ReviewerCompletion.objects.filter(
                session=session, reviewer=self.owner
            ).count(),
            1,
        )


class OwnerProgressTrackingTest(TestCase):
    """Test progress tracking for session owners."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Test Org", slug="test-org")
        self.owner = create_test_user(username_prefix="owner")
        self.owner.organisation = self.org
        self.owner.save()

        # Create session and config
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.owner,
            organisation=self.org,
            status="processing_results",
            total_results=5,
        )
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            created_by=self.owner,
            organisation=self.org,
        )
        self.session.current_configuration = config
        self.session.save()

        # Create results
        self.results = []
        for i in range(5):
            result = ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i + 1}",
                url=f"https://example.com/{i + 1}",
                snippet=f"Snippet {i + 1}",
                processing_status="success",
            )
            self.results.append(result)

        # Transition to create owner completion
        self.session.status = "ready_for_review"
        self.session.save(update_fields=["status"])

    def test_owner_progress_updated_on_decision(self):
        """Test owner's ReviewerCompletion progress is updated on decision."""
        completion = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.owner
        )
        self.assertEqual(completion.reviewed_results, 0)

        # Owner makes a decision
        ReviewerDecision.objects.create(
            result=self.results[0],
            reviewer=self.owner,
            organisation=self.org,
            decision="INCLUDE",
            is_revote=False,
        )

        completion.refresh_from_db()
        self.assertEqual(completion.reviewed_results, 1)

    def test_owner_auto_completed_when_all_reviewed(self):
        """Test owner auto-completed when all results reviewed."""
        # Owner reviews all results
        for result in self.results:
            ReviewerDecision.objects.create(
                result=result,
                reviewer=self.owner,
                organisation=self.org,
                decision="INCLUDE",
                is_revote=False,
            )

        completion = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.owner
        )
        self.assertEqual(completion.reviewed_results, 5)
        self.assertTrue(completion.is_complete)
        self.assertIsNotNone(completion.completed_at)


class OwnerMarkCompleteEndpointTest(TestCase):
    """Test mark_reviewer_complete endpoint for session owners."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Test Org", slug="test-org")
        self.owner = create_test_user(username_prefix="owner")
        self.owner.organisation = self.org
        self.owner.save()

        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.owner,
            organisation=self.org,
            status="under_review",
            total_results=5,
        )
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=2,
            created_by=self.owner,
            organisation=self.org,
        )
        self.session.current_configuration = config
        self.session.save()

        # Create owner completion manually (simulating what signal does)
        ReviewerCompletion.objects.create(
            invitation=None,
            session=self.session,
            reviewer=self.owner,
            total_results=5,
            reviewed_results=5,
        )

        self.client.login(username=self.owner.username, password="testpass123")

    def test_owner_can_mark_complete(self):
        """Test session owner can successfully mark review complete."""
        url = reverse("review_results:mark_reviewer_complete", args=[self.session.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data["status"], ["waiting", "complete"])

        # Verify completion marked
        completion = ReviewerCompletion.objects.get(
            session=self.session, reviewer=self.owner
        )
        self.assertIsNotNone(completion.completed_at)


class OwnerRecordPropertyTest(TestCase):
    """Test the is_owner_record property."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Test Org", slug="test-org")
        self.owner = create_test_user(username_prefix="owner")
        self.owner.organisation = self.org
        self.owner.save()

        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.owner,
            organisation=self.org,
            status="under_review",
            total_results=5,
        )

    def test_is_owner_record_true_when_no_invitation(self):
        """Test is_owner_record returns True when invitation is None."""
        completion = ReviewerCompletion.objects.create(
            invitation=None,
            session=self.session,
            reviewer=self.owner,
            total_results=5,
            reviewed_results=0,
        )
        self.assertTrue(completion.is_owner_record)

    def test_is_owner_record_false_when_invitation_exists(self):
        """Test is_owner_record returns False when invitation exists."""
        from apps.review_manager.models import ReviewInvitation

        # Create invitation with PENDING status first to avoid signal creating completion
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="reviewer@example.com",
            invitee_name="Test Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Manually create completion linked to invitation
        completion = ReviewerCompletion.objects.create(
            invitation=invitation,
            session=self.session,
            reviewer=self.owner,
            total_results=5,
            reviewed_results=0,
        )
        self.assertFalse(completion.is_owner_record)
