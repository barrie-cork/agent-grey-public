"""
Integration tests for external reviewer approval workflow.

Tests Phases A-F integration:
- Classifier correctly identifies external reviewers
- Approval workflow stores/sends invitations appropriately
- IS can approve/reject with proper notifications
- Activity logging captures all actions
- Email notifications sent correctly
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from constance.test import override_config

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import (
    SearchSession,
    ReviewConfiguration,
    ReviewInvitation,
    SessionActivity,
)
from apps.core.tests.utils import create_test_user
from apps.review_manager.utils import classify_invited_reviewers

User = get_user_model()


class ApprovalWorkflowIntegrationTests(TestCase):
    """Integration tests for end-to-end approval workflow."""

    def _check_email_sent(self, mock_send, subject_text):
        """Helper to check if an email with given subject was sent."""
        call_args = mock_send.call_args_list
        for call in call_args:
            # Check positional args
            if call[0] and len(call[0]) > 0 and subject_text in str(call[0][0]):
                return True
            # Check keyword args
            if "subject" in call[1] and subject_text in call[1]["subject"]:
                return True
        return False

    def setUp(self):
        """Set up test data for all tests."""
        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create IS user (email must match hardcoded values in test assertions)
        self.is_user = create_test_user(
            username_prefix="info_spec",
            email="is@test.com",
        )
        OrganisationMembership.objects.create(
            user=self.is_user,
            organisation=self.org,
            role="INFORMATION_SPECIALIST",
            is_active=True,
        )

        # Create session owner (internal member)
        self.owner = create_test_user(
            username_prefix="owner",
            email="owner@test.com",
        )
        OrganisationMembership.objects.create(
            user=self.owner, organisation=self.org, role="REVIEWER", is_active=True
        )

        # Create another internal reviewer
        self.internal_reviewer = create_test_user(
            username_prefix="internal_reviewer",
            email="internal@test.com",
        )
        OrganisationMembership.objects.create(
            user=self.internal_reviewer,
            organisation=self.org,
            role="REVIEWER",
            is_active=True,
        )

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.owner,
            organisation=self.org,
            status="defining_search",
        )

        # Create review configuration
        self.config = ReviewConfiguration.objects.create(
            session=self.session, organisation=self.org, created_by=self.owner
        )

        # Set as current configuration
        self.session.current_configuration = self.config
        self.session.save(update_fields=["current_configuration"])

        self.client = Client()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_config(REQUIRE_IS_APPROVAL_FOR_EXTERNAL_INVITES=True)
    @patch(
        "apps.review_manager.services.notification_service.NotificationService._send_email"
    )
    def test_external_reviewers_stored_when_approval_enabled(self, mock_send):
        """Test that external reviewers are stored for approval when flag enabled."""
        # Set up reviewers
        invited_reviewers = [
            {
                "email": "internal@test.com",
                "first_name": "Internal",
                "last_name": "Reviewer",
            },
            {
                "email": "external1@example.com",
                "first_name": "External",
                "last_name": "One",
            },
            {
                "email": "external2@example.com",
                "first_name": "External",
                "last_name": "Two",
            },
        ]

        self.config.invited_reviewers = invited_reviewers
        self.config.save()

        # Transition to ready_for_review (use update_fields to trigger signal properly)
        self.session.status = "ready_for_review"
        self.session.save(update_fields=["status"])

        # Reload config
        self.config.refresh_from_db()

        # Assert external reviewers stored
        self.assertIsNotNone(self.config.external_reviewers_pending_approval)
        self.assertEqual(len(self.config.external_reviewers_pending_approval), 2)

        # Check only internal reviewer got invitation
        invitations = ReviewInvitation.objects.filter(session=self.session)
        self.assertEqual(invitations.count(), 1)
        self.assertEqual(invitations.first().invitee_email, "internal@test.com")

        # Check activity logged
        activity = SessionActivity.objects.filter(
            session=self.session, activity_type="external_reviewers_pending_approval"
        ).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.metadata["count"], 2)

        # Check IS notification sent
        mock_send.assert_called()
        self.assertTrue(
            self._check_email_sent(mock_send, "Approval Needed: External Reviewers"),
            f"IS notification not sent. Calls: {mock_send.call_args_list}",
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_config(REQUIRE_IS_APPROVAL_FOR_EXTERNAL_INVITES=False)
    def test_external_reviewers_sent_when_approval_disabled(self):
        """Test that external reviewers are invited immediately when flag disabled."""
        # Set up reviewers
        invited_reviewers = [
            {
                "email": "internal@test.com",
                "first_name": "Internal",
                "last_name": "Reviewer",
            },
            {
                "email": "external1@example.com",
                "first_name": "External",
                "last_name": "One",
            },
            {
                "email": "external2@example.com",
                "first_name": "External",
                "last_name": "Two",
            },
        ]

        self.config.invited_reviewers = invited_reviewers
        self.config.save()

        # Transition to ready_for_review (use update_fields to trigger signal properly)
        self.session.status = "ready_for_review"
        self.session.save(update_fields=["status"])

        # Reload config
        self.config.refresh_from_db()

        # Assert no external reviewers pending
        self.assertEqual(self.config.external_reviewers_pending_approval, [])

        # Check all reviewers got invitations
        invitations = ReviewInvitation.objects.filter(session=self.session)
        self.assertEqual(invitations.count(), 3)

        invited_emails = set(inv.invitee_email for inv in invitations)
        expected_emails = {
            "internal@test.com",
            "external1@example.com",
            "external2@example.com",
        }
        self.assertEqual(invited_emails, expected_emails)

    @patch(
        "apps.review_manager.services.notification_service.NotificationService._send_email"
    )
    def test_is_can_approve_external_reviewers(self, mock_send):
        """Test that IS user can approve external reviewers."""
        # Store external reviewers for approval
        external_reviewers = [
            {
                "email": "external1@example.com",
                "first_name": "External",
                "last_name": "One",
            },
            {
                "email": "external2@example.com",
                "first_name": "External",
                "last_name": "Two",
            },
        ]
        self.config.external_reviewers_pending_approval = external_reviewers
        self.config.save()

        # Login as IS user
        self.client.login(username=self.is_user.username, password="testpass123")

        # Approve the reviewers
        response = self.client.post(
            reverse("review_manager:approve_external_reviewers", args=[self.session.id])
        )

        self.assertEqual(response.status_code, 302)  # Redirect on success

        # Reload config
        self.config.refresh_from_db()

        # Assert approval fields set
        self.assertTrue(self.config.external_reviewers_approved)
        self.assertEqual(self.config.external_reviewers_approved_by, self.is_user)
        self.assertIsNotNone(self.config.external_reviewers_approved_at)
        self.assertEqual(self.config.external_reviewers_pending_approval, [])

        # Check invitations created
        invitations = ReviewInvitation.objects.filter(session=self.session)
        self.assertEqual(invitations.count(), 2)

        invited_emails = set(inv.invitee_email for inv in invitations)
        expected_emails = {"external1@example.com", "external2@example.com"}
        self.assertEqual(invited_emails, expected_emails)

        # Check activity logged
        activity = SessionActivity.objects.filter(
            session=self.session, activity_type="external_reviewers_approved"
        ).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.user, self.is_user)

        # Check owner notification sent
        mock_send.assert_called()
        self.assertTrue(
            self._check_email_sent(mock_send, "External Reviewers Approved"),
            f"Approval notification not sent. Calls: {mock_send.call_args_list}",
        )

    @patch(
        "apps.review_manager.services.notification_service.NotificationService._send_email"
    )
    def test_is_can_reject_external_reviewers(self, mock_send):
        """Test that IS user can reject external reviewers with reason."""
        # Store external reviewers for approval
        external_reviewers = [
            {
                "email": "external1@example.com",
                "first_name": "External",
                "last_name": "One",
            },
            {
                "email": "external2@example.com",
                "first_name": "External",
                "last_name": "Two",
            },
        ]
        self.config.external_reviewers_pending_approval = external_reviewers
        self.config.save()

        # Login as IS user
        self.client.login(username=self.is_user.username, password="testpass123")

        # Reject the reviewers
        rejection_reason = "Potential conflict of interest identified"
        response = self.client.post(
            reverse("review_manager:reject_external_reviewers", args=[self.session.id]),
            {"rejection_reason": rejection_reason},
        )

        self.assertEqual(response.status_code, 302)  # Redirect on success

        # Reload config
        self.config.refresh_from_db()

        # Assert rejection fields set
        self.assertFalse(self.config.external_reviewers_approved)
        self.assertEqual(self.config.external_reviewers_rejected_by, self.is_user)
        self.assertIsNotNone(self.config.external_reviewers_rejected_at)
        self.assertEqual(
            self.config.external_reviewers_rejection_reason, rejection_reason
        )
        self.assertEqual(self.config.external_reviewers_pending_approval, [])

        # Check no invitations created
        invitations = ReviewInvitation.objects.filter(session=self.session)
        self.assertEqual(invitations.count(), 0)

        # Check activity logged
        activity = SessionActivity.objects.filter(
            session=self.session, activity_type="external_reviewers_rejected"
        ).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.user, self.is_user)
        self.assertEqual(activity.metadata["rejection_reason"], rejection_reason)

        # Check owner notification sent
        mock_send.assert_called()
        self.assertTrue(
            self._check_email_sent(mock_send, "External Reviewers Rejected"),
            f"Rejection notification not sent. Calls: {mock_send.call_args_list}",
        )

    def test_non_is_cannot_access_approvals(self):
        """Test that IS users from different orgs cannot act on sessions from other orgs."""
        # Store external reviewers for approval
        external_reviewers = [
            {
                "email": "external1@example.com",
                "first_name": "External",
                "last_name": "One",
            }
        ]
        self.config.external_reviewers_pending_approval = external_reviewers
        self.config.save()

        # Login as owner (IS in their personal org, but REVIEWER in test org)
        self.client.login(username=self.owner.username, password="testpass123")

        # User CAN access pending approvals page (they're IS in their personal org)
        # But the queryset should be empty (no sessions from their IS orgs)
        response = self.client.get(reverse("review_manager:pending_approvals"))
        self.assertEqual(response.status_code, 200)  # Can access page
        self.assertEqual(
            len(response.context["pending_sessions"]), 0
        )  # But no sessions

        # Try to approve session from test org (where they're only REVIEWER)
        response = self.client.post(
            reverse("review_manager:approve_external_reviewers", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 403)  # Forbidden

        # Try to reject session from test org (where they're only REVIEWER)
        response = self.client.post(
            reverse("review_manager:reject_external_reviewers", args=[self.session.id]),
            {"rejection_reason": "test"},
        )
        self.assertEqual(response.status_code, 403)  # Forbidden

    def test_reviewer_classification_accuracy(self):
        """Test that classify_invited_reviewers correctly identifies internal/external."""
        invited_reviewers = [
            {"email": "owner@test.com", "first_name": "Owner", "last_name": "User"},
            {
                "email": "internal@test.com",
                "first_name": "Internal",
                "last_name": "Reviewer",
            },
            {
                "email": "external1@example.com",
                "first_name": "External",
                "last_name": "One",
            },
            {
                "email": "external2@example.com",
                "first_name": "External",
                "last_name": "Two",
            },
            {"email": "is@test.com", "first_name": "Info", "last_name": "Spec"},
        ]

        classification = classify_invited_reviewers(invited_reviewers, self.org)

        # Check internal classification
        self.assertEqual(len(classification["internal"]), 3)
        internal_emails = {r["email"] for r in classification["internal"]}
        self.assertEqual(
            internal_emails, {"owner@test.com", "internal@test.com", "is@test.com"}
        )

        # Check external classification
        self.assertEqual(len(classification["external"]), 2)
        external_emails = {r["email"] for r in classification["external"]}
        self.assertEqual(
            external_emails, {"external1@example.com", "external2@example.com"}
        )

        # Check counts
        self.assertEqual(classification["counts"]["internal"], 3)
        self.assertEqual(classification["counts"]["external"], 2)
        self.assertEqual(classification["counts"]["total"], 5)

    @override_config(INVITATION_RATE_LIMIT_PER_HOUR=2)
    def test_rate_limiting_enforced(self):
        """Test that invitation rate limiting is enforced."""
        # This test would require more complex setup to test rate limiting
        # properly. Placeholder for now.
        self.skipTest("Rate limiting test requires Redis/cache setup")

    def test_email_ownership_enforcement(self):
        """Test that users can only accept invitations for their email."""
        # Create invitation for external email
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="external@example.com",
            invitee_name="External User",
            inviter=self.owner,
            token="test-token-123",
            expires_at=timezone.now() + timedelta(days=7),
        )

        # Try to accept with different user
        self.client.login(
            username=self.internal_reviewer.username, password="testpass123"
        )

        _response = self.client.post(
            reverse("review_manager:accept_invitation", args=[invitation.token])
        )

        # Should fail validation
        # Note: Actual implementation may vary - adjust assertion as needed
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "PENDING")  # Not accepted

    def test_session_activity_types_recorded(self):
        """Test that all new activity types are properly recorded."""
        # Test pending approval activity
        activity1 = SessionActivity.objects.create(
            session=self.session,
            user=self.owner,
            activity_type="external_reviewers_pending_approval",
            description="External reviewers pending approval",
            metadata={"count": 2},
        )
        self.assertEqual(
            activity1.get_activity_type_display(), "External Reviewers Pending Approval"
        )

        # Test approved activity
        activity2 = SessionActivity.objects.create(
            session=self.session,
            user=self.is_user,
            activity_type="external_reviewers_approved",
            description="External reviewers approved",
            metadata={"count": 2},
        )
        self.assertEqual(
            activity2.get_activity_type_display(), "External Reviewers Approved"
        )

        # Test rejected activity
        activity3 = SessionActivity.objects.create(
            session=self.session,
            user=self.is_user,
            activity_type="external_reviewers_rejected",
            description="External reviewers rejected",
            metadata={"count": 2, "rejection_reason": "Test reason"},
        )
        self.assertEqual(
            activity3.get_activity_type_display(), "External Reviewers Rejected"
        )

        # Verify all activities were created
        activities = SessionActivity.objects.filter(session=self.session)
        self.assertEqual(activities.count(), 3)
