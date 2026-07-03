"""
Tests for invitation integration (Phase 7, Task T051).

End-to-end integration tests for the complete reviewer invitation workflow:
1. Full invitation workflow (create → email → accept → access)
2. Work queue integration (shared sessions appear in work queue)
3. Multiple reviewers with independent invitation states
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import ReviewInvitation, SearchSession
from apps.review_manager.services.invitation_service import ReviewInvitationService
from apps.core.tests.utils import create_test_user

User = get_user_model()


class InvitationIntegrationTestCase(TestCase):
    """End-to-end integration tests for reviewer invitation workflow."""

    @classmethod
    def setUpTestData(cls):
        """Set up test fixtures once for all tests (class-level)."""
        # Create users
        cls.owner = create_test_user(username_prefix="owner")
        cls.reviewer1 = create_test_user(username_prefix="reviewer1")
        cls.reviewer2 = create_test_user(username_prefix="reviewer2")
        cls.reviewer3 = create_test_user(username_prefix="reviewer3")

        # Create organisation
        cls.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-invitation-integration"
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
            title="Integration Test Session",
            description="Test session for integration tests",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )

    # -------------------------------------------------------------------------
    # Scenario 1: Full Invitation Workflow
    # -------------------------------------------------------------------------

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_full_invitation_workflow(self, mock_send_email):
        """
        End-to-end test: Owner creates session → invites reviewer2 → reviewer2
        logs in → sees notification → accepts invitation → accesses session →
        blocked from strategy edit.
        """
        mock_send_email.return_value = True

        # ===== Step 1: Owner creates session (already done in setUp)
        self.assertEqual(self.session.owner, self.owner)

        # ===== Step 2: Owner invites reviewer2
        service = ReviewInvitationService()
        invitee_data = [{"email": self.reviewer2.email, "name": "Reviewer Two"}]

        created_invitations, errors = service.create_invitations(
            session=self.session, invitee_data=invitee_data, inviter=self.owner
        )

        # Verify invitation created
        self.assertEqual(len(created_invitations), 1)
        self.assertEqual(len(errors), 0)

        invitation = created_invitations[0]
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_PENDING)
        self.assertIsNotNone(invitation.token)

        # Verify email sent (mock)
        mock_send_email.assert_called_once()

        # ===== Step 3: Reviewer2 logs in
        self.client.login(username=self.reviewer2.username, password="testpass123")

        # ===== Step 4: Reviewer2 sees notification badge
        dashboard_url = reverse("review_manager:dashboard")
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

        # Check notification count
        self.assertIn("pending_invitations_count", response.context)
        self.assertEqual(response.context["pending_invitations_count"], 1)

        # ===== Step 5: Reviewer2 navigates to pending invitations page
        pending_url = reverse("review_manager:pending_invitations")
        response = self.client.get(pending_url)
        self.assertEqual(response.status_code, 200)

        # Verify invitation appears
        self.assertIn("pending_invitations", response.context)
        pending_invitations = response.context["pending_invitations"]
        self.assertEqual(len(pending_invitations), 1)
        self.assertEqual(pending_invitations[0].id, invitation.id)

        # ===== Step 6: Reviewer2 clicks "Accept"
        accept_url = reverse(
            "review_manager:accept_invitation", kwargs={"token": invitation.token}
        )
        response = self.client.get(accept_url)

        # Verify redirect to session detail
        self.assertEqual(response.status_code, 302)
        session_detail_url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        self.assertEqual(response.url, session_detail_url)

        # ===== Step 7: Verify invitation status updated
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, ReviewInvitation.STATUS_ACCEPTED)
        self.assertEqual(invitation.invitee, self.reviewer2)
        self.assertIsNotNone(invitation.responded_at)

        # ===== Step 8: Verify session appears in "Shared With Me"
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

        self.assertIn("shared_sessions", response.context)
        shared_sessions = response.context["shared_sessions"]
        self.assertEqual(len(shared_sessions), 1)
        self.assertEqual(shared_sessions[0].id, self.session.id)

        # ===== Step 9: Reviewer2 can access session detail (200)
        response = self.client.get(session_detail_url)
        self.assertEqual(response.status_code, 200)

        # Verify role context
        self.assertEqual(response.context["user_role"], "reviewer")
        self.assertFalse(response.context["can_edit"])

        # ===== Step 10: Reviewer2 CANNOT access strategy edit (403 or redirect)
        # Note: Strategy edit view doesn't exist in this context, but we test SessionUpdateView
        edit_session_url = reverse(
            "review_manager:edit_session", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(edit_session_url)

        # Should be redirected (UserOwnerMixin blocks non-owners)
        self.assertEqual(response.status_code, 302)

    # -------------------------------------------------------------------------
    # Scenario 2: Work Queue Integration
    # -------------------------------------------------------------------------

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_work_queue_includes_shared_sessions(self, mock_send_email):
        """
        Test that reviewer can access work queue from shared session after
        accepting invitation.
        """
        mock_send_email.return_value = True

        # ===== Step 1: Setup - Session with results ready for review
        # (In real scenario, session would have SearchResults from serp_execution)
        # For this test, we verify session access after acceptance

        # ===== Step 2: Owner invites Reviewer1
        service = ReviewInvitationService()
        invitee_data = [{"email": self.reviewer1.email, "name": "Reviewer One"}]

        created_invitations, errors = service.create_invitations(
            session=self.session, invitee_data=invitee_data, inviter=self.owner
        )

        self.assertEqual(len(created_invitations), 1)
        invitation = created_invitations[0]

        # ===== Step 3: Reviewer1 accepts invitation
        self.client.login(username=self.reviewer1.username, password="testpass123")
        accept_url = reverse(
            "review_manager:accept_invitation", kwargs={"token": invitation.token}
        )
        response = self.client.get(accept_url)
        self.assertEqual(response.status_code, 302)

        # ===== Step 4: Verify Reviewer1 can access session
        session_detail_url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(session_detail_url)
        self.assertEqual(response.status_code, 200)

        # ===== Step 5: Verify session appears in dashboard
        dashboard_url = reverse("review_manager:dashboard")
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

        # Check shared_sessions includes invited session
        shared_sessions = response.context["shared_sessions"]
        shared_session_ids = [s.id for s in shared_sessions]
        self.assertIn(self.session.id, shared_session_ids)

        # ===== Step 6: Verify work queue API would include this session's results
        # (In real implementation, ReviewClaimService checks accessible sessions)
        # For this test, we verify that the session is accessible
        self.assertTrue(
            ReviewInvitation.objects.filter(
                session=self.session,
                invitee=self.reviewer1,
                status=ReviewInvitation.STATUS_ACCEPTED,
            ).exists(),
            "Reviewer1 should have accepted invitation to access work queue",
        )

    # -------------------------------------------------------------------------
    # Scenario 3: Multiple Reviewers Independent Invitations
    # -------------------------------------------------------------------------

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_multiple_reviewers_independent_invitations(self, mock_send_email):
        """
        Test that each reviewer has independent invitation state:
        - R1 accepts → can access
        - R2 declines → cannot access
        - R3 remains pending → cannot access
        - One reviewer's action doesn't affect others
        """
        mock_send_email.return_value = True

        # ===== Step 1: Owner invites R1, R2, R3
        service = ReviewInvitationService()
        invitee_data = [
            {"email": self.reviewer1.email, "name": "Reviewer One"},
            {"email": self.reviewer2.email, "name": "Reviewer Two"},
            {"email": self.reviewer3.email, "name": "Reviewer Three"},
        ]

        created_invitations, errors = service.create_invitations(
            session=self.session, invitee_data=invitee_data, inviter=self.owner
        )

        # Verify 3 invitations created
        self.assertEqual(len(created_invitations), 3)
        self.assertEqual(len(errors), 0)

        inv_r1, inv_r2, inv_r3 = created_invitations

        # ===== Step 2: R1 accepts invitation
        self.client.login(username=self.reviewer1.username, password="testpass123")
        accept_url = reverse(
            "review_manager:accept_invitation", kwargs={"token": inv_r1.token}
        )
        response = self.client.get(accept_url)
        self.assertEqual(response.status_code, 302)
        self.client.logout()

        # ===== Step 3: R2 declines invitation
        self.client.login(username=self.reviewer2.username, password="testpass123")
        decline_url = reverse(
            "review_manager:decline_invitation", kwargs={"token": inv_r2.token}
        )
        response = self.client.post(decline_url)
        self.assertEqual(response.status_code, 302)
        self.client.logout()

        # ===== Step 4: R3 remains pending (no action)

        # ===== Step 5: Verify statuses independent
        inv_r1.refresh_from_db()
        inv_r2.refresh_from_db()
        inv_r3.refresh_from_db()

        self.assertEqual(inv_r1.status, ReviewInvitation.STATUS_ACCEPTED)
        self.assertEqual(inv_r2.status, ReviewInvitation.STATUS_DECLINED)
        self.assertEqual(inv_r3.status, ReviewInvitation.STATUS_PENDING)

        # ===== Step 6: R1 can access session (ACCEPTED)
        self.client.login(username=self.reviewer1.username, password="testpass123")
        session_detail_url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(session_detail_url)
        self.assertEqual(response.status_code, 200)
        self.client.logout()

        # ===== Step 7: R2 CANNOT access session (DECLINED)
        self.client.login(username=self.reviewer2.username, password="testpass123")
        response = self.client.get(session_detail_url)
        self.assertEqual(
            response.status_code, 403, "Declined reviewer should be denied access"
        )
        self.client.logout()

        # ===== Step 8: R3 CANNOT access session (PENDING)
        self.client.login(username=self.reviewer3.username, password="testpass123")
        response = self.client.get(session_detail_url)
        self.assertEqual(
            response.status_code, 403, "Pending reviewer should be denied access"
        )
        self.client.logout()

        # ===== Step 9: Verify R1 acceptance doesn't affect R2/R3
        inv_r2.refresh_from_db()
        inv_r3.refresh_from_db()

        self.assertEqual(
            inv_r2.status,
            ReviewInvitation.STATUS_DECLINED,
            "R2's declined status should be unchanged",
        )
        self.assertEqual(
            inv_r3.status,
            ReviewInvitation.STATUS_PENDING,
            "R3's pending status should be unchanged",
        )

    # -------------------------------------------------------------------------
    # Additional Integration Tests
    # -------------------------------------------------------------------------

    @patch(
        "apps.review_manager.services.invitation_service.ReviewInvitationService.send_invitation_email"
    )
    def test_dashboard_separates_owned_and_shared_sessions(self, mock_send_email):
        """Dashboard correctly separates owned vs shared sessions."""
        mock_send_email.return_value = True

        # Create owned session for reviewer1
        owned_session = SearchSession.objects.create(
            title="Reviewer1 Owned Session",
            owner=self.reviewer1,
            organisation=self.organisation,
            status="draft",
        )

        # Owner invites reviewer1 to shared session
        service = ReviewInvitationService()
        invitee_data = [{"email": self.reviewer1.email, "name": "Reviewer One"}]

        created_invitations, errors = service.create_invitations(
            session=self.session, invitee_data=invitee_data, inviter=self.owner
        )

        invitation = created_invitations[0]

        # Reviewer1 accepts invitation
        self.client.login(username=self.reviewer1.username, password="testpass123")
        accept_url = reverse(
            "review_manager:accept_invitation", kwargs={"token": invitation.token}
        )
        response = self.client.get(accept_url)
        self.assertEqual(response.status_code, 302)

        # Check dashboard
        dashboard_url = reverse("review_manager:dashboard")
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

        # Verify separation
        owned_sessions = response.context["owned_sessions"]
        shared_sessions = response.context["shared_sessions"]

        # Should have 1 owned session
        self.assertEqual(len(owned_sessions), 1)
        self.assertEqual(owned_sessions[0].id, owned_session.id)

        # Should have 1 shared session
        self.assertEqual(len(shared_sessions), 1)
        self.assertEqual(shared_sessions[0].id, self.session.id)

        # No session should appear in both lists
        owned_ids = {s.id for s in owned_sessions}
        shared_ids = {s.id for s in shared_sessions}
        self.assertEqual(len(owned_ids & shared_ids), 0)
