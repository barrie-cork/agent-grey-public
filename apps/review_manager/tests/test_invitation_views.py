"""
Tests for invitation views (Phase 7, Task T048).

Tests the invitation view functionality including:
- Pending invitations view
- Accept invitation view with token validation
- Decline invitation view
- Login requirements
- Redirects and messaging
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import ReviewInvitation, SearchSession
from apps.core.tests.utils import create_test_user

User = get_user_model()


class InvitationViewsTestCase(TestCase):
    """Test suite for invitation views."""

    @classmethod
    def setUpTestData(cls):
        """Set up test fixtures once for all tests (class-level)."""
        # Create users
        cls.owner = create_test_user(username_prefix="owner")
        cls.reviewer = create_test_user(username_prefix="reviewer")

        # Create organisation
        cls.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-invitation-views"
        )
        OrganisationMembership.objects.create(
            organisation=cls.organisation,
            user=cls.owner,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

    def setUp(self):
        """Set up test fixtures for each test (instance-level)."""
        # Create client
        self.client = Client()

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test session for invitation views tests",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )

    # -------------------------------------------------------------------------
    # PendingInvitationsView Tests
    # -------------------------------------------------------------------------

    def test_pending_invitations_view_requires_login(self):
        """Anonymous user redirected to login."""
        url = reverse("review_manager:pending_invitations")
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_pending_invitations_view_shows_pending_only(self):
        """Only PENDING invitations shown in list."""
        # Create PENDING invitation
        pending_invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Create ACCEPTED invitation (should not appear)
        accepted_session = SearchSession.objects.create(
            title="Accepted Session",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )
        _accepted_invitation = ReviewInvitation.objects.create(
            session=accepted_session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            invitee=self.reviewer,
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        # Create DECLINED invitation (should not appear)
        declined_session = SearchSession.objects.create(
            title="Declined Session",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )
        _declined_invitation = ReviewInvitation.objects.create(
            session=declined_session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_DECLINED,
            responded_at=timezone.now(),
        )

        # Login and get pending invitations
        self.client.login(username=self.reviewer.username, password="testpass123")
        url = reverse("review_manager:pending_invitations")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check context
        self.assertIn("pending_invitations", response.context)
        pending_invitations = response.context["pending_invitations"]

        # Should contain only PENDING invitation
        self.assertEqual(len(pending_invitations), 1)
        self.assertEqual(pending_invitations[0].id, pending_invitation.id)
        self.assertEqual(pending_invitations[0].status, ReviewInvitation.STATUS_PENDING)

    def test_pending_invitations_view_empty_list(self):
        """Empty list when no pending invitations."""
        self.client.login(username=self.reviewer.username, password="testpass123")
        url = reverse("review_manager:pending_invitations")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Should have empty list
        self.assertIn("pending_invitations", response.context)
        self.assertEqual(len(response.context["pending_invitations"]), 0)

    # -------------------------------------------------------------------------
    # AcceptInvitationView Tests
    # -------------------------------------------------------------------------

    def test_accept_invitation_valid_token(self):
        """Valid token accepted successfully with redirect."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        self.client.login(username=self.reviewer.username, password="testpass123")
        url = reverse(
            "review_manager:accept_invitation", kwargs={"token": invitation.token}
        )
        response = self.client.get(url)

        # Should redirect to session detail
        self.assertEqual(response.status_code, 302)
        expected_url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        self.assertIn(expected_url, response.url)

        # Refresh invitation
        invitation.refresh_from_db()

        # Should be ACCEPTED
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_ACCEPTED)
        self.assertEqual(invitation.invitee, self.reviewer)

    def test_accept_invitation_expired_token(self):
        """Expired token rejected with error message."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Manually expire invitation
        invitation.expires_at = timezone.now() - timedelta(days=1)
        invitation.save()

        # Force expiry check
        invitation.is_valid()
        invitation.refresh_from_db()

        self.client.login(username=self.reviewer.username, password="testpass123")
        url = reverse(
            "review_manager:accept_invitation", kwargs={"token": invitation.token}
        )
        response = self.client.get(url)

        # Should redirect to pending invitations
        self.assertEqual(response.status_code, 302)
        expected_url = reverse("review_manager:pending_invitations")
        self.assertIn(expected_url, response.url)

        # Should have error message
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any("expired" in str(m).lower() for m in messages))

    def test_accept_invitation_invalid_token(self):
        """Invalid token rejected with error message."""
        self.client.login(username=self.reviewer.username, password="testpass123")
        url = reverse(
            "review_manager:accept_invitation", kwargs={"token": "invalid-token-12345"}
        )
        response = self.client.get(url)

        # Should redirect to pending invitations
        self.assertEqual(response.status_code, 302)
        expected_url = reverse("review_manager:pending_invitations")
        self.assertIn(expected_url, response.url)

        # Should have error message
        messages = list(response.wsgi_request._messages)
        self.assertTrue(len(messages) > 0)

    def test_accept_invitation_redirects_to_session(self):
        """Successful acceptance redirects to session detail."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        self.client.login(username=self.reviewer.username, password="testpass123")
        url = reverse(
            "review_manager:accept_invitation", kwargs={"token": invitation.token}
        )
        response = self.client.get(url)

        # Verify redirect URL contains session ID
        self.assertEqual(response.status_code, 302)
        self.assertIn(str(self.session.id), response.url)

        # Verify session detail URL
        session_detail_url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        self.assertEqual(response.url, session_detail_url)

    # -------------------------------------------------------------------------
    # DeclineInvitationView Tests
    # -------------------------------------------------------------------------

    def test_decline_invitation_success(self):
        """Invitation declined successfully with POST."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        self.client.login(username=self.reviewer.username, password="testpass123")
        url = reverse(
            "review_manager:decline_invitation", kwargs={"token": invitation.token}
        )
        response = self.client.post(url)

        # Should redirect to pending invitations
        self.assertEqual(response.status_code, 302)

        # Refresh invitation
        invitation.refresh_from_db()

        # Should be DECLINED
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_DECLINED)
        self.assertIsNotNone(invitation.responded_at)

        # Should have success message
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any("declined" in str(m).lower() for m in messages))

    def test_decline_invitation_requires_post(self):
        """GET method not allowed for decline view."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        self.client.login(username=self.reviewer.username, password="testpass123")
        url = reverse(
            "review_manager:decline_invitation", kwargs={"token": invitation.token}
        )
        response = self.client.get(url)

        # Should return 405 Method Not Allowed
        self.assertEqual(response.status_code, 405)

    def test_decline_invitation_invalid_token(self):
        """Invalid token handled gracefully."""
        self.client.login(username=self.reviewer.username, password="testpass123")
        url = reverse(
            "review_manager:decline_invitation", kwargs={"token": "invalid-token"}
        )
        response = self.client.post(url)

        # Should redirect to pending invitations
        self.assertEqual(response.status_code, 302)

        # Should have error message
        messages = list(response.wsgi_request._messages)
        self.assertTrue(len(messages) > 0)

    # -------------------------------------------------------------------------
    # Template Rendering Tests
    # -------------------------------------------------------------------------

    def test_pending_invitations_template_used(self):
        """Correct template used for pending invitations view."""
        self.client.login(username=self.reviewer.username, password="testpass123")
        url = reverse("review_manager:pending_invitations")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "review_manager/pending_invitations.html")

    def test_accept_invitation_requires_login(self):
        """Accept invitation requires login."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Try to accept without login
        url = reverse(
            "review_manager:accept_invitation", kwargs={"token": invitation.token}
        )
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_decline_invitation_requires_login(self):
        """Decline invitation requires login."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Try to decline without login
        url = reverse(
            "review_manager:decline_invitation", kwargs={"token": invitation.token}
        )
        response = self.client.post(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
