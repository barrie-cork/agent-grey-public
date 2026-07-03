"""
Tests for ReviewInvitationService (Phase 7, Task T047).

Tests the ReviewInvitationService functionality including:
- Service initialisation and health checks
- Creating and sending invitations
- Accepting invitations with validation
- Declining invitations
- Getting pending invitations
- Revoking invitations
- Email integration (mocked)
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import ReviewInvitation, SearchSession
from apps.review_manager.services.invitation_service import ReviewInvitationService
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ReviewInvitationServiceTestCase(TestCase):
    """Test suite for ReviewInvitationService."""

    @classmethod
    def setUpTestData(cls):
        """Set up test fixtures once for all tests (class-level)."""
        # Create users
        cls.owner = create_test_user(username_prefix="owner")
        cls.reviewer1 = create_test_user(username_prefix="reviewer1")
        cls.reviewer2 = create_test_user(username_prefix="reviewer2")

        # Create organisation
        cls.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-invitation-service"
        )
        OrganisationMembership.objects.create(
            organisation=cls.organisation,
            user=cls.owner,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

    def setUp(self):
        """Set up test fixtures for each test (instance-level)."""
        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test session for invitation service tests",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )

        # Create request factory
        self.factory = RequestFactory()

        # Instantiate service
        self.service = ReviewInvitationService()

    # -------------------------------------------------------------------------
    # Service Initialisation and Health Check Tests
    # -------------------------------------------------------------------------

    def test_service_initialization(self):
        """Service initialises correctly."""
        service = ReviewInvitationService()

        # Verify service name and version
        self.assertEqual(service.SERVICE_NAME, "ReviewInvitationService")
        self.assertEqual(service.SERVICE_VERSION, "1.0.0")

    def test_health_check_success(self):
        """Health check succeeds when database is accessible."""
        service = ReviewInvitationService()

        health_status = service.health_check()

        # Health check should pass
        self.assertTrue(
            health_status, "Health check should return True when database is accessible"
        )

    def test_default_config_loaded(self):
        """Default configuration contains expected keys."""
        service = ReviewInvitationService()
        config = service.get_default_config()

        # Verify config keys
        self.assertIn("cache_timeout", config)
        self.assertIn("max_invitations_per_session", config)
        self.assertIn("invitation_expiry_days", config)

        # Verify values
        self.assertEqual(config["cache_timeout"], 300)
        self.assertEqual(config["max_invitations_per_session"], 10)
        self.assertEqual(config["invitation_expiry_days"], 7)

    # -------------------------------------------------------------------------
    # Create Invitations Tests
    # -------------------------------------------------------------------------

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_create_invitations_success_single(self, mock_send_email):
        """Single invitation created and email sent successfully."""
        mock_send_email.return_value = True

        invitee_data = [{"email": "invitee@example.com", "name": "Test Invitee"}]

        created, errors = self.service.create_invitations(
            session=self.session, invitee_data=invitee_data, inviter=self.owner
        )

        # Should create 1 invitation
        self.assertEqual(len(created), 1)
        self.assertEqual(len(errors), 0)

        # Verify invitation details
        invitation = created[0]
        self.assertEqual(invitation.invitee_email, "invitee@example.com")
        self.assertEqual(invitation.invitee_name, "Test Invitee")
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_PENDING)
        self.assertEqual(invitation.session, self.session)
        self.assertEqual(invitation.inviter, self.owner)

        # Verify email was sent
        mock_send_email.assert_called_once()

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_create_invitations_success_multiple(self, mock_send_email):
        """Multiple invitations created and emails sent."""
        mock_send_email.return_value = True

        invitee_data = [
            {"email": "reviewer1@example.com", "name": "Reviewer One"},
            {"email": "reviewer2@example.com", "name": "Reviewer Two"},
            {"email": "reviewer3@example.com", "name": "Reviewer Three"},
        ]

        created, errors = self.service.create_invitations(
            session=self.session, invitee_data=invitee_data, inviter=self.owner
        )

        # Should create 3 invitations
        self.assertEqual(len(created), 3)
        self.assertEqual(len(errors), 0)

        # Verify email sent for each
        self.assertEqual(mock_send_email.call_count, 3)

        # Verify all invitations created
        emails = [inv.invitee_email for inv in created]
        self.assertIn("reviewer1@example.com", emails)
        self.assertIn("reviewer2@example.com", emails)
        self.assertIn("reviewer3@example.com", emails)

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_create_invitations_skips_duplicates(self, mock_send_email):
        """Existing PENDING invitation is skipped."""
        mock_send_email.return_value = True

        # Create existing PENDING invitation
        ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="existing@example.com",
            invitee_name="Existing User",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        invitee_data = [{"email": "existing@example.com", "name": "Duplicate Attempt"}]

        created, errors = self.service.create_invitations(
            session=self.session, invitee_data=invitee_data, inviter=self.owner
        )

        # Should not create invitation
        self.assertEqual(len(created), 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("already exists", errors[0])

        # Email should not be sent
        mock_send_email.assert_not_called()

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_create_invitations_skips_accepted(self, mock_send_email):
        """Existing ACCEPTED invitation is skipped."""
        mock_send_email.return_value = True

        # Create existing ACCEPTED invitation
        ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="accepted@example.com",
            invitee_name="Accepted User",
            inviter=self.owner,
            invitee=self.reviewer1,
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        invitee_data = [{"email": "accepted@example.com", "name": "Re-invite Attempt"}]

        created, errors = self.service.create_invitations(
            session=self.session, invitee_data=invitee_data, inviter=self.owner
        )

        # Should not create invitation
        self.assertEqual(len(created), 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("already accepted", errors[0])

        # Email should not be sent
        mock_send_email.assert_not_called()

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_create_invitations_skips_missing_email(self, mock_send_email):
        """Invitee without email is skipped."""
        mock_send_email.return_value = True

        invitee_data = [
            {"name": "No Email User"},  # Missing email
            {"email": "valid@example.com", "name": "Valid User"},
        ]

        created, errors = self.service.create_invitations(
            session=self.session, invitee_data=invitee_data, inviter=self.owner
        )

        # Should create only 1 invitation (skip the one without email)
        self.assertEqual(len(created), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("without email", errors[0])

        # Only 1 email sent
        self.assertEqual(mock_send_email.call_count, 1)

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_create_invitations_max_limit_enforcement(self, mock_send_email):
        """Cannot exceed max invitations per session limit."""
        mock_send_email.return_value = True

        # Create 10 pending invitations (at limit)
        for i in range(10):
            ReviewInvitation.objects.create(
                session=self.session,
                invitee_email=f"user{i}@example.com",
                invitee_name=f"User {i}",
                inviter=self.owner,
                status=ReviewInvitation.STATUS_PENDING,
            )

        # Attempt to create one more (should fail)
        invitee_data = [{"email": "overflow@example.com", "name": "Overflow User"}]

        created, errors = self.service.create_invitations(
            session=self.session, invitee_data=invitee_data, inviter=self.owner
        )

        # Should not create invitation
        self.assertEqual(len(created), 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("exceed maximum", errors[0])

        # Email should not be sent
        mock_send_email.assert_not_called()

    # -------------------------------------------------------------------------
    # Accept Invitation Tests
    # -------------------------------------------------------------------------

    def test_accept_invitation_valid_token(self):
        """Valid token accepted successfully."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        success, error, result_invitation = self.service.accept_invitation(
            token=invitation.token, user=self.reviewer1
        )

        # Should succeed
        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertIsNotNone(result_invitation)

        # Refresh invitation
        invitation.refresh_from_db()

        # Verify status updated
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_ACCEPTED)
        self.assertEqual(invitation.invitee, self.reviewer1)
        self.assertIsNotNone(invitation.responded_at)

    def test_accept_invitation_expired(self):
        """Expired token rejected."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Manually expire invitation
        invitation.expires_at = timezone.now() - timedelta(days=1)
        invitation.save()

        # Force expiry check
        invitation.is_valid()
        invitation.refresh_from_db()

        success, error, result_invitation = self.service.accept_invitation(
            token=invitation.token, user=self.reviewer1
        )

        # Should fail
        self.assertFalse(success)
        self.assertIsNotNone(error)
        assert error is not None
        self.assertIn("expired", error.lower())

    def test_accept_invitation_invalid_token(self):
        """Invalid token rejected."""
        success, error, result_invitation = self.service.accept_invitation(
            token="invalid-token-that-does-not-exist", user=self.reviewer1
        )

        # Should fail
        self.assertFalse(success)
        self.assertIsNotNone(error)
        self.assertIn("Invalid", error)
        self.assertIsNone(result_invitation)

    def test_accept_invitation_already_accepted(self):
        """Already accepted invitation rejected."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            invitee=self.reviewer1,
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        success, error, result_invitation = self.service.accept_invitation(
            token=invitation.token, user=self.reviewer1
        )

        # Should fail
        self.assertFalse(success)
        self.assertIsNotNone(error)
        assert error is not None
        self.assertIn("already been accepted", error.lower())

    def test_accept_invitation_declined_status(self):
        """Declined invitation cannot be accepted."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_DECLINED,
            responded_at=timezone.now(),
        )

        success, error, result_invitation = self.service.accept_invitation(
            token=invitation.token, user=self.reviewer1
        )

        # Should fail
        self.assertFalse(success)
        self.assertIsNotNone(error)

    # -------------------------------------------------------------------------
    # Decline Invitation Tests
    # -------------------------------------------------------------------------

    def test_decline_invitation_success(self):
        """Invitation declined successfully."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        success, error, result_invitation = self.service.decline_invitation(
            token=invitation.token, user=self.reviewer1
        )

        # Should succeed
        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertIsNotNone(result_invitation)

        # Refresh invitation
        invitation.refresh_from_db()

        # Verify status updated
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_DECLINED)
        self.assertIsNotNone(invitation.responded_at)

    def test_decline_invitation_invalid_token(self):
        """Invalid token rejected."""
        success, error, result_invitation = self.service.decline_invitation(
            token="invalid-token", user=self.reviewer1
        )

        # Should fail
        self.assertFalse(success)
        self.assertIsNotNone(error)
        self.assertIsNone(result_invitation)

    def test_decline_invitation_already_accepted(self):
        """Accepted invitation cannot be declined."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            invitee=self.reviewer1,
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        success, error, result_invitation = self.service.decline_invitation(
            token=invitation.token, user=self.reviewer1
        )

        # Should fail
        self.assertFalse(success)
        self.assertIsNotNone(error)

    # -------------------------------------------------------------------------
    # Get Pending Invitations Tests
    # -------------------------------------------------------------------------

    def test_get_pending_invitations_multiple(self):
        """Get multiple pending invitations for user."""
        # Create 3 pending invitations for reviewer1
        for i in range(3):
            session = SearchSession.objects.create(
                title=f"Session {i}",
                owner=self.owner,
                organisation=self.organisation,
                status="ready_for_review",
            )
            ReviewInvitation.objects.create(
                session=session,
                invitee_email=self.reviewer1.email,
                invitee_name="Reviewer One",
                inviter=self.owner,
                status=ReviewInvitation.STATUS_PENDING,
            )

        # Create 1 accepted invitation (should not appear)
        accepted_session = SearchSession.objects.create(
            title="Accepted Session",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )
        ReviewInvitation.objects.create(
            session=accepted_session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            invitee=self.reviewer1,
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        pending = self.service.get_pending_invitations(self.reviewer1)

        # Should return exactly 3 pending invitations
        self.assertEqual(len(pending), 3)

        # All should be PENDING
        for invitation in pending:
            self.assertEqual(invitation.status, ReviewInvitation.STATUS_PENDING)

    def test_get_pending_invitations_empty(self):
        """Get empty list when no pending invitations."""
        pending = self.service.get_pending_invitations(self.reviewer1)

        # Should return empty list
        self.assertEqual(len(pending), 0)

    def test_get_pending_invitations_filters_by_email(self):
        """Pending invitations filtered by user email."""
        # Create invitation for reviewer1
        ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Create invitation for reviewer2
        session2 = SearchSession.objects.create(
            title="Session 2",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )
        ReviewInvitation.objects.create(
            session=session2,
            invitee_email=self.reviewer2.email,
            invitee_name="Reviewer Two",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Get pending for reviewer1
        pending = self.service.get_pending_invitations(self.reviewer1)

        # Should return only 1 invitation
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].invitee_email, self.reviewer1.email)

    # -------------------------------------------------------------------------
    # Revoke Invitation Tests
    # -------------------------------------------------------------------------

    def test_revoke_invitation_success(self):
        """Pending invitation revoked successfully."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        success = self.service.revoke_invitation(invitation)

        # Should succeed
        self.assertTrue(success)

        # Refresh invitation
        invitation.refresh_from_db()

        # Verify status updated
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_REVOKED)

    def test_revoke_invitation_already_accepted(self):
        """Accepted invitation cannot be revoked."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            invitee=self.reviewer1,
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        success = self.service.revoke_invitation(invitation)

        # Should fail
        self.assertFalse(success)

        # Refresh invitation
        invitation.refresh_from_db()

        # Status should remain ACCEPTED
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_ACCEPTED)

    # -------------------------------------------------------------------------
    # Email Sending Tests (Mocked)
    # -------------------------------------------------------------------------

    @patch(
        "apps.review_results.services.email_notification_service.EmailNotificationService"
    )
    def test_send_invitation_email_success(self, mock_email_service_class):
        """Email sent successfully via EmailNotificationService."""
        # Setup mock
        mock_instance = MagicMock()
        mock_email_service_class.return_value = mock_instance
        mock_instance.send_reviewer_invitation.return_value = True

        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="Test User",
            inviter=self.owner,
        )

        result = self.service.send_invitation_email(invitation)

        # Should return True
        self.assertTrue(result)

        # Verify send_reviewer_invitation was called
        mock_instance.send_reviewer_invitation.assert_called_once_with(invitation, None)

    @patch(
        "apps.review_results.services.email_notification_service.EmailNotificationService"
    )
    def test_send_invitation_email_failure_returns_false(
        self, mock_email_service_class
    ):
        """Email failure returns False."""
        # Setup mock to return False (simulating email send failure)
        mock_instance = MagicMock()
        mock_email_service_class.return_value = mock_instance
        mock_instance.send_reviewer_invitation.return_value = False

        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="Test User",
            inviter=self.owner,
        )

        result = self.service.send_invitation_email(invitation)

        # Should return False (email sending failed)
        self.assertFalse(result)

    @patch(
        "apps.review_results.services.email_notification_service.EmailNotificationService"
    )
    def test_send_invitation_email_exception_returns_false(
        self, mock_email_service_class
    ):
        """Email service exception returns False and logs error."""
        # Setup mock to raise exception
        mock_instance = MagicMock()
        mock_email_service_class.return_value = mock_instance
        mock_instance.send_reviewer_invitation.side_effect = Exception(
            "SMTP connection failed"
        )

        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="Test User",
            inviter=self.owner,
        )

        result = self.service.send_invitation_email(invitation)

        # Should return False (exception handled gracefully)
        self.assertFalse(result)

    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------

    def test_create_invitations_email_send_failure_still_creates_invitation(self):
        """Invitation created even if email fails (graceful degradation)."""
        with patch.object(self.service, "send_invitation_email", return_value=False):
            invitees = [{"email": "test@example.com", "name": "Test User"}]
            created, errors = self.service.create_invitations(
                session=self.session, invitee_data=invitees, inviter=self.owner
            )

            # Invitation should still be created
            self.assertEqual(len(created), 1)
            self.assertEqual(len(errors), 0)

            # Verify invitation exists in database
            invitation = ReviewInvitation.objects.get(invitee_email="test@example.com")
            self.assertEqual(invitation.session, self.session)
            self.assertEqual(invitation.status, ReviewInvitation.STATUS_PENDING)

    def test_create_invitations_database_error_handling(self):
        """Database error during creation adds error message."""
        # patch.object on the manager instance so the mock intercepts correctly
        # (string-based patch can't traverse Django's ManagerDescriptor)
        with patch.object(
            ReviewInvitation.objects,
            "get_or_create",
            side_effect=Exception("Database connection lost"),
        ):
            invitees = [{"email": "test@example.com", "name": "Test User"}]
            created, errors = self.service.create_invitations(
                session=self.session, invitee_data=invitees, inviter=self.owner
            )

            # Should return empty created list and error message
            self.assertEqual(len(created), 0)
            self.assertEqual(len(errors), 1)
            self.assertIn("Failed to create invitation", errors[0])
            self.assertIn("test@example.com", errors[0])

    def test_health_check_database_unavailable_returns_false(self):
        """Health check returns False when database is unavailable."""
        # patch.object on the manager instance so the mock intercepts correctly
        with patch.object(
            ReviewInvitation.objects,
            "count",
            side_effect=Exception("Database connection failed"),
        ):
            result = self.service.health_check()

            # Should return False (service unhealthy)
            self.assertFalse(result)

    def test_accept_invitation_database_error_returns_error_tuple(self):
        """Database error during acceptance returns error tuple."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
        )

        # Mock save to raise exception
        with patch.object(
            ReviewInvitation, "save", side_effect=Exception("Database write failed")
        ):
            success, error_message, returned_inv = self.service.accept_invitation(
                token=invitation.token, user=self.reviewer1
            )

            # Should return error tuple
            self.assertFalse(success)
            self.assertIsNotNone(error_message)
            self.assertEqual(error_message, "Failed to accept invitation")
            self.assertIsNone(returned_inv)

    def test_revoke_invitation_non_pending_status_returns_false(self):
        """Revoking non-pending invitation returns False."""
        # Create accepted invitation
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_ACCEPTED,
        )

        result = self.service.revoke_invitation(invitation)

        # Should return False (cannot revoke accepted invitation)
        self.assertFalse(result)

        # Status should not change
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_ACCEPTED)

    def test_revoke_invitation_database_error_returns_false(self):
        """Database error during revocation returns False."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer1.email,
            invitee_name="Reviewer One",
            inviter=self.owner,
        )

        # Mock save to raise exception
        with patch.object(
            ReviewInvitation, "save", side_effect=Exception("Database error")
        ):
            result = self.service.revoke_invitation(invitation)

            # Should return False (error handled)
            self.assertFalse(result)
