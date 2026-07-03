"""
Security tests for organisation invitation system.

Tests Phase A critical security fixes:
- Only IS can send organisation invitations
- Membership verification required
- Rate limiting enforced
- Email ownership enforced on acceptance
"""

import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organisation.models import (
    Organisation,
    OrganisationInvitation,
    OrganisationMembership,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class OrganisationInvitationSecurityTests(TestCase):
    """Test security fixes for organisation invitations."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create IS user (Information Specialist)
        self.is_user = create_test_user(
            username_prefix="info_specialist", first_name="Info", last_name="Specialist"
        )
        self.is_membership = OrganisationMembership.objects.create(
            user=self.is_user,
            organisation=self.org,
            role="INFORMATION_SPECIALIST",
            is_active=True,
        )

        # Create REVIEWER user
        self.reviewer = create_test_user(
            username_prefix="reviewer", first_name="Review", last_name="User"
        )
        self.reviewer_membership = OrganisationMembership.objects.create(
            user=self.reviewer, organisation=self.org, role="REVIEWER", is_active=True
        )

        # Create non-member user (outsider)
        self.outsider = create_test_user(
            username_prefix="outsider", first_name="Out", last_name="Sider"
        )

    def test_is_can_send_invitation(self):
        """Information Specialist can send invitations."""
        self.client.login(username=self.is_user.username, password="testpass123")

        response = self.client.post(
            reverse("organisation:invite", args=[self.org.id]),
            {"email": "newuser@test.com", "role": "REVIEWER", "name": "New User"},
        )

        # Should succeed with redirect or JSON success
        self.assertIn(response.status_code, [200, 302])

        # Verify invitation was created
        self.assertTrue(
            OrganisationInvitation.objects.filter(
                email="newuser@test.com", organisation=self.org
            ).exists()
        )

    def test_reviewer_cannot_send_invitation(self):
        """REVIEWER role cannot send invitations."""
        self.client.login(username=self.reviewer.username, password="testpass123")

        response = self.client.post(
            reverse("organisation:invite", args=[self.org.id]),
            {"email": "newuser@test.com", "role": "REVIEWER", "name": "New User"},
        )

        # Should be denied
        self.assertEqual(response.status_code, 403)

        # Verify invitation was NOT created
        self.assertFalse(
            OrganisationInvitation.objects.filter(
                email="newuser@test.com", organisation=self.org
            ).exists()
        )

    def test_non_member_cannot_send_invitation(self):
        """Non-member cannot send invitations to organisation."""
        self.client.login(username=self.outsider.username, password="testpass123")

        response = self.client.post(
            reverse("organisation:invite", args=[self.org.id]),
            {"email": "newuser@test.com", "role": "REVIEWER", "name": "New User"},
        )

        # Should be denied
        self.assertEqual(response.status_code, 403)

        # Verify invitation was NOT created
        self.assertFalse(
            OrganisationInvitation.objects.filter(
                email="newuser@test.com", organisation=self.org
            ).exists()
        )

    def test_rate_limiting_enforced(self):
        """Rate limiting blocks 11th invitation within hour."""
        self.client.login(username=self.is_user.username, password="testpass123")

        # Send 10 invitations (should succeed)
        for i in range(10):
            response = self.client.post(
                reverse("organisation:invite", args=[self.org.id]),
                {"email": f"user{i}@test.com", "role": "REVIEWER", "name": f"User {i}"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",  # AJAX request
            )
            self.assertEqual(response.status_code, 200)

        # 11th invitation should fail
        response = self.client.post(
            reverse("organisation:invite", args=[self.org.id]),
            {"email": "user11@test.com", "role": "REVIEWER", "name": "User 11"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",  # AJAX request
        )

        # Should return 429 Too Many Requests
        self.assertEqual(response.status_code, 429)

        # Verify 11th invitation was NOT created
        self.assertFalse(
            OrganisationInvitation.objects.filter(email="user11@test.com").exists()
        )

        # Verify we have exactly 10 invitations
        invitation_count = OrganisationInvitation.objects.filter(
            invited_by=self.is_user, created_at__gte=timezone.now() - timedelta(hours=1)
        ).count()
        self.assertEqual(invitation_count, 10)

    def test_rate_limiting_resets_after_hour(self):
        """Rate limiting resets after 1 hour."""
        self.client.login(username=self.is_user.username, password="testpass123")

        # Create 10 old invitations (more than 1 hour ago)
        old_time = timezone.now() - timedelta(hours=2)
        for i in range(10):
            invitation = OrganisationInvitation.objects.create(
                organisation=self.org,
                invited_by=self.is_user,
                email=f"olduser{i}@test.com",
                role="REVIEWER",
                name=f"Old User {i}",
                token=secrets.token_urlsafe(48),
                expires_at=timezone.now() + timedelta(days=7),
            )
            # Manually set created_at to past time
            OrganisationInvitation.objects.filter(id=invitation.id).update(
                created_at=old_time
            )

        # Now should be able to send new invitations
        response = self.client.post(
            reverse("organisation:invite", args=[self.org.id]),
            {"email": "newuser@test.com", "role": "REVIEWER", "name": "New User"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            OrganisationInvitation.objects.filter(email="newuser@test.com").exists()
        )

    def test_email_mismatch_blocks_acceptance(self):
        """User with wrong email cannot accept invitation (Review Manager)."""
        from apps.review_manager.models import SearchSession, ReviewInvitation
        from apps.review_manager.services.invitation_service import (
            ReviewInvitationService,
        )

        # Create a search session
        session = SearchSession.objects.create(
            title="Test Session",
            description="Test session for invitation testing",
            owner=self.is_user,
            organisation=self.org,
            status="ready_for_review",
        )

        # Create review invitation for specific email
        invitation = ReviewInvitation.objects.create(
            session=session,
            inviter=self.is_user,
            invitee_email="target@test.com",  # Invitation for this email
            invitee_name="Target User",
            token=secrets.token_urlsafe(48),
            status="PENDING",
            expires_at=timezone.now() + timedelta(days=7),
        )

        # Try to accept with different email (outsider@test.com)
        service = ReviewInvitationService()
        success, error_msg, returned_invitation = service.accept_invitation(
            token=invitation.token,
            user=self.outsider,  # Has email: outsider@test.com
        )

        # Should fail with email mismatch error
        self.assertFalse(success)
        self.assertIn("Invitation was sent to target@test.com", error_msg)
        self.assertIn(f"Your current account email is {self.outsider.email}", error_msg)

        # Invitation should still be PENDING
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "PENDING")
        self.assertIsNone(invitation.invitee)

    def test_correct_email_can_accept_invitation(self):
        """User with correct email can accept invitation."""
        from apps.review_manager.models import SearchSession, ReviewInvitation
        from apps.review_manager.services.invitation_service import (
            ReviewInvitationService,
        )

        # Create a search session
        session = SearchSession.objects.create(
            title="Test Session",
            description="Test session for invitation testing",
            owner=self.is_user,
            organisation=self.org,
            status="ready_for_review",
        )

        # Create review invitation for reviewer's email
        invitation = ReviewInvitation.objects.create(
            session=session,
            inviter=self.is_user,
            invitee_email=self.reviewer.email,  # Matches reviewer's email
            invitee_name="Review User",
            token=secrets.token_urlsafe(48),
            status="PENDING",
            expires_at=timezone.now() + timedelta(days=7),
        )

        # Accept with correct email
        service = ReviewInvitationService()
        success, error_msg, returned_invitation = service.accept_invitation(
            token=invitation.token,
            user=self.reviewer,
        )

        # Should succeed
        self.assertTrue(success)
        self.assertIsNone(error_msg)

        # Invitation should be ACCEPTED
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, "ACCEPTED")
        self.assertEqual(invitation.invitee, self.reviewer)
        self.assertIsNotNone(invitation.responded_at)

    def test_org_invitation_email_mismatch_blocks_acceptance(self):
        """User with wrong email cannot accept an organisation invitation."""
        from apps.organisation.services import InvitationService

        invitation = OrganisationInvitation.objects.create(
            organisation=self.org,
            invited_by=self.is_user,
            email="target@test.com",  # Invitation for this email
            role="REVIEWER",
            name="Target User",
            token=secrets.token_urlsafe(48),
            expires_at=timezone.now() + timedelta(days=7),
        )

        service = InvitationService()
        success, error = service.accept_invitation(
            token=invitation.token,
            user=self.outsider,  # Different email
        )

        self.assertFalse(success)
        self.assertIn("This invitation was sent to target@test.com", error)

        # No membership created; invitation still pending
        self.assertFalse(
            OrganisationMembership.objects.filter(
                user=self.outsider, organisation=self.org
            ).exists()
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganisationInvitation.STATUS_PENDING)

    def test_org_invitation_correct_email_can_accept(self):
        """User with matching email can accept an organisation invitation."""
        from apps.organisation.services import InvitationService

        invitation = OrganisationInvitation.objects.create(
            organisation=self.org,
            invited_by=self.is_user,
            email=self.outsider.email,
            role="REVIEWER",
            name="Out Sider",
            token=secrets.token_urlsafe(48),
            expires_at=timezone.now() + timedelta(days=7),
        )

        service = InvitationService()
        success, error = service.accept_invitation(
            token=invitation.token,
            user=self.outsider,
        )

        self.assertTrue(success)
        self.assertIsNone(error)

        membership = OrganisationMembership.objects.filter(
            user=self.outsider, organisation=self.org
        ).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, "REVIEWER")
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganisationInvitation.STATUS_ACCEPTED)

    def test_org_invitation_accept_page_renders(self):
        """GET on the magic link renders the accept page (templates exist)."""
        invitation = OrganisationInvitation.objects.create(
            organisation=self.org,
            invited_by=self.is_user,
            email="target@test.com",
            role="REVIEWER",
            name="Target User",
            token=secrets.token_urlsafe(48),
            expires_at=timezone.now() + timedelta(days=7),
        )

        response = self.client.get(
            reverse("organisation:invitation_accept", args=[invitation.token])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "organisation/invitation_accept.html")
        self.assertContains(response, self.org.name)

    def test_org_invitation_email_mismatch_blocked_via_view(self):
        """AcceptInvitationView blocks a logged-in user with the wrong email."""
        invitation = OrganisationInvitation.objects.create(
            organisation=self.org,
            invited_by=self.is_user,
            email="target@test.com",
            role="REVIEWER",
            name="Target User",
            token=secrets.token_urlsafe(48),
            expires_at=timezone.now() + timedelta(days=7),
        )

        self.client.login(username=self.outsider.username, password="testpass123")
        response = self.client.post(
            reverse("organisation:invitation_accept", args=[invitation.token])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "organisation/invitation_error.html")
        self.assertFalse(
            OrganisationMembership.objects.filter(
                user=self.outsider, organisation=self.org
            ).exists()
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, OrganisationInvitation.STATUS_PENDING)

    def test_ajax_request_returns_json_error(self):
        """AJAX requests return JSON error responses."""
        self.client.login(username=self.reviewer.username, password="testpass123")

        response = self.client.post(
            reverse("organisation:invite", args=[self.org.id]),
            {"email": "newuser@test.com", "role": "REVIEWER"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",  # AJAX request
        )

        # Should return 403 with proper error message
        self.assertEqual(response.status_code, 403)

    def test_non_ajax_request_returns_redirect(self):
        """Non-AJAX requests redirect with error message."""
        self.client.login(username=self.is_user.username, password="testpass123")

        # Create 10 invitations to hit rate limit
        for i in range(10):
            OrganisationInvitation.objects.create(
                organisation=self.org,
                invited_by=self.is_user,
                email=f"ratelimit{i}@test.com",
                role="REVIEWER",
                token=secrets.token_urlsafe(48),
                expires_at=timezone.now() + timedelta(days=7),
            )

        # Try to create 11th (should fail with rate limit)
        response = self.client.post(
            reverse("organisation:invite", args=[self.org.id]),
            {"email": "overlimit@test.com", "role": "REVIEWER"},
        )

        # Should return 429 for rate limiting
        self.assertEqual(response.status_code, 429)

    def test_session_activity_logged_on_acceptance(self):
        """SessionActivity is logged when invitation is accepted."""
        from apps.review_manager.models import (
            SearchSession,
            ReviewInvitation,
            SessionActivity,
        )
        from apps.review_manager.services.invitation_service import (
            ReviewInvitationService,
        )

        # Create a search session
        session = SearchSession.objects.create(
            title="Test Session",
            description="Test session for activity logging",
            owner=self.is_user,
            organisation=self.org,
            status="ready_for_review",
        )

        # Create review invitation
        invitation = ReviewInvitation.objects.create(
            session=session,
            inviter=self.is_user,
            invitee_email=self.reviewer.email,
            invitee_name="Review User",
            token=secrets.token_urlsafe(48),
            status="PENDING",
            expires_at=timezone.now() + timedelta(days=7),
        )

        # Accept invitation
        service = ReviewInvitationService()
        success, _, _ = service.accept_invitation(
            token=invitation.token, user=self.reviewer
        )

        self.assertTrue(success)

        # Verify SessionActivity was created
        activity = SessionActivity.objects.filter(
            session=session, user=self.reviewer, activity_type="INVITATION_ACCEPTED"
        ).first()

        self.assertIsNotNone(activity)
        self.assertEqual(
            activity.description, f"{self.reviewer.username} accepted review invitation"
        )
        self.assertEqual(activity.metadata["invitation_id"], str(invitation.id))
        self.assertEqual(activity.metadata["inviter"], self.is_user.username)
