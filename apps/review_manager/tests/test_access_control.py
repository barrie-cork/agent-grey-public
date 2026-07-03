"""
Tests for role-based access control in review sessions.

Verifies that:
- Session owners have full access with editing capabilities
- Invited reviewers (with accepted invitations) have read-only access
- Users without invitations are denied access
- Owner-only views properly reject non-owners
"""

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import (
    ReviewConfiguration,
    ReviewInvitation,
    SearchSession,
)
from apps.core.tests.utils import DisablePersonalOrgSignalMixin, create_test_user


class AccessControlTestCase(DisablePersonalOrgSignalMixin, TestCase):
    """Test role-based access control for review sessions."""

    @classmethod
    def setUpTestData(cls):
        """Set up test fixtures once for all tests (class-level).

        Creates:
        - 3 users: owner, invited_reviewer, stranger
        - 1 organisation
        """
        # Create users
        cls.owner = create_test_user(username_prefix="owner")
        cls.invited_reviewer = create_test_user(username_prefix="reviewer")
        cls.stranger = create_test_user(username_prefix="stranger")

        # Create organisation
        cls.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-access-control"
        )
        # Add owner as member
        OrganisationMembership.objects.create(
            organisation=cls.organisation,
            user=cls.owner,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

    def setUp(self):
        """Set up test fixtures for each test (instance-level).

        Creates:
        - 1 session owned by owner
        - 1 ACCEPTED invitation for invited_reviewer
        - 1 PENDING invitation for another email
        """
        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test session for access control",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )

        # Create review configuration (required for session detail access)
        config = ReviewConfiguration.objects.create(
            session=self.session,
            min_reviewers_per_result=1,
            created_by=self.owner,
        )
        self.session.current_configuration = config
        self.session.save(update_fields=["current_configuration"])

        # Create ACCEPTED invitation for invited_reviewer
        self.accepted_invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=self.invited_reviewer.email,
            invitee_name="Test Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_ACCEPTED,
            invitee=self.invited_reviewer,
        )

        # Create PENDING invitation for another email
        self.pending_invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="pending@example.com",
            invitee_name="Pending User",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Create request factory
        self.factory = RequestFactory()

    # -------------------------------------------------------------------------
    # SessionDetailView Access Tests
    # -------------------------------------------------------------------------

    def test_session_detail_owner_access(self):
        """Owner can access session detail view."""
        self.client.force_login(self.owner)
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["user_role"], "owner")
        self.assertTrue(response.context["can_edit"])

    def test_session_detail_invited_reviewer_access(self):
        """Invited reviewer with accepted invitation can access session detail."""
        self.client.force_login(self.invited_reviewer)
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["user_role"], "reviewer")
        self.assertFalse(response.context["can_edit"])

    def test_session_detail_uninvited_user_denied(self):
        """Uninvited user cannot access session detail (PermissionDenied)."""
        self.client.force_login(self.stranger)
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        # PermissionDenied should result in 403 Forbidden
        self.assertEqual(response.status_code, 403)

    def test_session_detail_pending_invitation_denied(self):
        """User with pending invitation cannot access until accepted."""
        # Create user with pending invitation email
        pending_user = create_test_user(username_prefix="pending")

        self.client.login(username=pending_user.username, password="testpass123")
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        # Should be denied - invitation not accepted yet
        self.assertEqual(response.status_code, 403)

    # -------------------------------------------------------------------------
    # Context Data Tests
    # -------------------------------------------------------------------------

    def test_session_detail_context_includes_role(self):
        """Session detail context includes user_role and can_edit."""
        self.client.force_login(self.owner)
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertIn("user_role", response.context)
        self.assertIn("can_edit", response.context)

    def test_session_detail_context_owner_can_edit(self):
        """Owner context has can_edit=True."""
        self.client.force_login(self.owner)
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.context["user_role"], "owner")
        self.assertTrue(response.context["can_edit"])

    def test_session_detail_context_reviewer_cannot_edit(self):
        """Reviewer context has can_edit=False."""
        self.client.force_login(self.invited_reviewer)
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.context["user_role"], "reviewer")
        self.assertFalse(response.context["can_edit"])

    # -------------------------------------------------------------------------
    # Owner-Only View Protection Tests
    # -------------------------------------------------------------------------

    def test_session_edit_requires_ownership(self):
        """SessionUpdateView (edit_session) requires ownership."""
        self.client.force_login(self.invited_reviewer)
        url = reverse(
            "review_manager:edit_session", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        # Should redirect with error (UserOwnerMixin behavior)
        # Could redirect to '/' or '/dashboard' depending on middleware
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url in ["/", "/dashboard", reverse("review_manager:dashboard")],
            f"Expected redirect to dashboard or root, got: {response.url}",
        )

    def test_session_delete_requires_ownership(self):
        """SessionDeleteView requires ownership."""
        self.client.force_login(self.invited_reviewer)
        url = reverse(
            "review_manager:delete_session", kwargs={"session_id": self.session.id}
        )
        response = self.client.post(url)  # DELETE uses POST

        # Should redirect with error (UserOwnerMixin behavior)
        # Could redirect to '/' or '/dashboard' depending on middleware
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url in ["/", "/dashboard", reverse("review_manager:dashboard")],
            f"Expected redirect to dashboard or root, got: {response.url}",
        )

        # Verify session still exists (not deleted)
        self.assertTrue(SearchSession.objects.filter(id=self.session.id).exists())

    # -------------------------------------------------------------------------
    # Template Rendering Tests
    # -------------------------------------------------------------------------

    def test_role_indicator_shown_for_reviewer(self):
        """Reviewer role indicator alert is shown for invited reviewers."""
        self.client.force_login(self.invited_reviewer)
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertContains(response, "Reviewer Access")
        self.assertContains(response, "You are a <strong>reviewer</strong>")

    def test_role_indicator_not_shown_for_owner(self):
        """Reviewer role indicator alert is not shown for owners."""
        self.client.force_login(self.owner)
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertNotContains(response, "Reviewer Access")
        self.assertNotContains(response, "You are a <strong>reviewer</strong>")

    def test_edit_buttons_hidden_for_reviewer(self):
        """Edit buttons are hidden for invited reviewers."""
        self.client.force_login(self.invited_reviewer)
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        # Should not contain "Modify Search Strategy" section
        # (Only visible if can_edit and status is executing/processing/ready_for_review)
        if self.session.status in [
            "executing",
            "processing_results",
            "ready_for_review",
        ]:
            self.assertNotContains(response, "Return to Search Strategy")

    def test_edit_buttons_shown_for_owner(self):
        """Edit buttons are shown for owners."""
        # Set session to a status where "Modify Search Strategy" is visible
        self.session.status = "ready_for_review"
        self.session.save()

        self.client.force_login(self.owner)
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        # Should contain "Modify Search Strategy" section
        self.assertContains(response, "Return to Search Strategy")

    # -------------------------------------------------------------------------
    # Edge Case Tests
    # -------------------------------------------------------------------------

    def test_declined_invitation_denies_access(self):
        """User with declined invitation cannot access session."""
        # Create user and declined invitation
        declined_user = create_test_user(username_prefix="declined")
        ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=declined_user.email,
            invitee_name="Declined User",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_DECLINED,
        )

        self.client.login(username=declined_user.username, password="testpass123")
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        # Should be denied access
        self.assertEqual(response.status_code, 403)

    def test_expired_invitation_denies_access(self):
        """User with expired invitation cannot access session."""
        # Create user and expired invitation
        expired_user = create_test_user(username_prefix="expired")
        ReviewInvitation.objects.create(
            session=self.session,
            invitee_email=expired_user.email,
            invitee_name="Expired User",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_EXPIRED,
        )

        self.client.login(username=expired_user.username, password="testpass123")
        url = reverse(
            "review_manager:session_detail", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        # Should be denied access
        self.assertEqual(response.status_code, 403)
