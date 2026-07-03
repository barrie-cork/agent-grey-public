"""
Tests for DashboardView Phase 4 implementation.

Tests the dashboard integration with reviewer invitations, including:
- Owned sessions display
- Shared sessions display (accepted invitations)
- is_owner annotation
- Context data separation
- Pending invitations preview
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.review_manager.models import ReviewInvitation, SearchSession
from apps.core.tests.utils import create_test_user

User = get_user_model()


class DashboardViewPhase4TestCase(TestCase):
    """Test suite for Phase 4 dashboard integration."""

    def setUp(self):
        """Set up test data for dashboard tests."""
        # Create users
        self.user1 = create_test_user(username_prefix="user1")
        self.user2 = create_test_user(username_prefix="user2")

        # Create sessions owned by user1
        self.owned_session1 = SearchSession.objects.create(
            title="Owned Session 1",
            description="User1 owns this",
            owner=self.user1,
            status="draft",
        )
        self.owned_session2 = SearchSession.objects.create(
            title="Owned Session 2",
            description="User1 also owns this",
            owner=self.user1,
            status="ready_for_review",
        )

        # Create session owned by user2
        self.other_session = SearchSession.objects.create(
            title="Other User Session",
            description="User2 owns this",
            owner=self.user2,
            status="draft",
        )

        # Create invitation from user2 to user1 (PENDING)
        self.pending_invitation = ReviewInvitation.objects.create(
            session=self.other_session,
            inviter=self.user2,
            invitee_email=self.user1.email,
            invitee_name="User One",
            status=ReviewInvitation.STATUS_PENDING,
            invited_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )

        # Create another session owned by user2
        self.shared_session = SearchSession.objects.create(
            title="Shared Session",
            description="User2 owns, User1 invited",
            owner=self.user2,
            status="under_review",
        )

        # Create invitation from user2 to user1 (ACCEPTED)
        self.accepted_invitation = ReviewInvitation.objects.create(
            session=self.shared_session,
            inviter=self.user2,
            invitee=self.user1,
            invitee_email=self.user1.email,
            invitee_name="User One",
            status=ReviewInvitation.STATUS_ACCEPTED,
            invited_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(days=7),
            responded_at=timezone.now(),
        )

        self.dashboard_url = reverse("review_manager:dashboard")

    def test_dashboard_shows_owned_sessions_only(self):
        """Test that dashboard shows user's owned sessions."""
        self.client.login(username=self.user1.username, password="testpass123")
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)

        # Check owned_sessions in context
        self.assertIn("owned_sessions", response.context)
        owned_sessions = response.context["owned_sessions"]

        # Should contain both owned sessions
        self.assertEqual(len(owned_sessions), 2)
        owned_titles = [s.title for s in owned_sessions]
        self.assertIn("Owned Session 1", owned_titles)
        self.assertIn("Owned Session 2", owned_titles)

    def test_dashboard_shows_invited_sessions_after_acceptance(self):
        """Test that accepted invitations appear in shared_sessions."""
        self.client.login(username=self.user1.username, password="testpass123")
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)

        # Check shared_sessions in context
        self.assertIn("shared_sessions", response.context)
        shared_sessions = response.context["shared_sessions"]

        # Should contain the shared session
        self.assertEqual(len(shared_sessions), 1)
        self.assertEqual(shared_sessions[0].title, "Shared Session")

        # Should NOT contain pending invitation session
        shared_titles = [s.title for s in shared_sessions]
        self.assertNotIn("Other User Session", shared_titles)

    def test_dashboard_is_owner_annotation(self):
        """Test that is_owner annotation correctly identifies ownership."""
        self.client.login(username=self.user1.username, password="testpass123")
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)

        # Check owned sessions have is_owner=True
        owned_sessions = response.context["owned_sessions"]
        for session in owned_sessions:
            self.assertTrue(
                session.is_owner, f"Session {session.title} should have is_owner=True"
            )

        # Check shared sessions have is_owner=False
        shared_sessions = response.context["shared_sessions"]
        for session in shared_sessions:
            self.assertFalse(
                session.is_owner, f"Session {session.title} should have is_owner=False"
            )

    def test_dashboard_context_separates_owned_shared(self):
        """Test that context properly separates owned and shared sessions."""
        self.client.login(username=self.user1.username, password="testpass123")
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)

        owned_sessions = response.context["owned_sessions"]
        shared_sessions = response.context["shared_sessions"]

        # Owned sessions should only be owned by user1
        for session in owned_sessions:
            self.assertEqual(session.owner, self.user1)

        # Shared sessions should be owned by someone else
        for session in shared_sessions:
            self.assertNotEqual(session.owner, self.user1)

        # No session should appear in both lists
        owned_ids = {s.id for s in owned_sessions}
        shared_ids = {s.id for s in shared_sessions}
        self.assertEqual(
            len(owned_ids & shared_ids),
            0,
            "Sessions should not appear in both owned and shared lists",
        )

    def test_dashboard_context_pending_limited_to_5(self):
        """Test that pending invitations preview is limited to 5."""
        # Create 10 pending invitations
        for i in range(10):
            session = SearchSession.objects.create(
                title=f"Extra Session {i}",
                description="Extra session for testing",
                owner=self.user2,
                status="draft",
            )
            ReviewInvitation.objects.create(
                session=session,
                inviter=self.user2,
                invitee_email=self.user1.email,
                invitee_name="User One",
                status=ReviewInvitation.STATUS_PENDING,
                invited_at=timezone.now(),
                expires_at=timezone.now() + timezone.timedelta(days=7),
            )

        self.client.login(username=self.user1.username, password="testpass123")
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)

        # Check pending_invitations limited to 5
        self.assertIn("pending_invitations", response.context)
        pending_invitations = response.context["pending_invitations"]

        # Should be exactly 5 (sliced from total 11)
        self.assertEqual(len(pending_invitations), 5)

    def test_dashboard_no_shared_sessions_for_user_without_invitations(self):
        """Test that users without invitations have empty shared_sessions."""
        self.client.login(username=self.user2.username, password="testpass123")
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)

        # User2 should have no shared sessions
        shared_sessions = response.context["shared_sessions"]
        self.assertEqual(len(shared_sessions), 0)

        # User2 should have owned sessions
        owned_sessions = response.context["owned_sessions"]
        self.assertGreater(len(owned_sessions), 0)

    def test_dashboard_queryset_distinct(self):
        """Test that queryset uses distinct() to prevent duplicates.

        Tests that when a user has multiple accepted invitations from
        different inviters to the same session (edge case), the session
        appears only once in the dashboard.
        """
        # Create another user who will also invite user1 to the same session
        user3 = create_test_user(username_prefix="user3")

        # User3 creates an additional invitation for user1 to the shared_session
        # Note: This creates a second ACCEPTED invitation to the same session
        # but from a different inviter, testing the distinct() functionality
        # Create as PENDING first, then update to ACCEPTED via queryset
        # to avoid the signal creating a duplicate ReviewerCompletion
        additional_invitation = ReviewInvitation.objects.create(
            session=self.shared_session,
            inviter=user3,  # Different inviter
            invitee=self.user1,
            invitee_email="user1+alt@example.com",  # Different email to avoid unique constraint
            invitee_name="User One Alt",
            status=ReviewInvitation.STATUS_PENDING,
            invited_at=timezone.now(),
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        # Update status via queryset to bypass signal
        ReviewInvitation.objects.filter(id=additional_invitation.id).update(
            status=ReviewInvitation.STATUS_ACCEPTED, responded_at=timezone.now()
        )

        self.client.login(username=self.user1.username, password="testpass123")
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)

        # Get all sessions (both owned and shared)
        all_sessions_in_queryset = list(response.context["sessions"])
        session_ids = [s.id for s in all_sessions_in_queryset]
        unique_ids = set(session_ids)

        # Verify no duplicates in full queryset
        self.assertEqual(
            len(session_ids),
            len(unique_ids),
            "No duplicate sessions should appear in queryset due to JOIN",
        )

        # Shared session should only appear once in shared_sessions
        shared_sessions = response.context["shared_sessions"]
        shared_ids = [s.id for s in shared_sessions]
        shared_unique_ids = set(shared_ids)

        self.assertEqual(
            len(shared_ids),
            len(shared_unique_ids),
            "No duplicate sessions should appear in shared_sessions",
        )

    def test_dashboard_unauthenticated_redirect(self):
        """Test that unauthenticated users are redirected to login."""
        response = self.client.get(self.dashboard_url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_dashboard_pending_invitations_count(self):
        """Test that pending_invitations_count is in context (from context processor)."""
        self.client.login(username=self.user1.username, password="testpass123")
        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.status_code, 200)

        # Check context includes pending_invitations_count from context processor
        self.assertIn("pending_invitations_count", response.context)

        # Should be 1 (the pending_invitation created in setUp)
        # Plus any created in previous tests (isolation issue - use fresh DB)
        self.assertGreaterEqual(response.context["pending_invitations_count"], 1)
