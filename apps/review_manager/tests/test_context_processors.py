"""
Tests for context processors (Phase 7, Task T052).

Tests the pending_invitations context processor that provides
notification badge count across all templates.
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.context_processors import pending_invitations
from apps.review_manager.models import ReviewInvitation, SearchSession
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ContextProcessorsTestCase(TestCase):
    """Test suite for review_manager context processors."""

    @classmethod
    def setUpTestData(cls):
        """Set up test fixtures once for all tests (class-level)."""
        # Create users
        cls.owner = create_test_user(username_prefix="owner")
        cls.reviewer = create_test_user(username_prefix="reviewer")

        # Create organisation
        cls.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-context-processors"
        )
        OrganisationMembership.objects.create(
            organisation=cls.organisation,
            user=cls.owner,
            role=OrganisationMembership.ROLE_LEAD_REVIEWER,
        )

    def setUp(self):
        """Set up test fixtures for each test (instance-level)."""
        # Create request factory
        self.factory = RequestFactory()

        # Create session
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test session for context processor tests",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )

    # -------------------------------------------------------------------------
    # pending_invitations Context Processor Tests
    # -------------------------------------------------------------------------

    def test_pending_invitations_anonymous_user(self):
        """Anonymous user returns count=0."""
        # Create mock request with anonymous user
        request = self.factory.get("/")
        request.user = type("MockAnonymousUser", (), {"is_authenticated": False})()

        context = pending_invitations(request)

        # Should return 0 for anonymous users
        self.assertEqual(
            context["pending_invitations_count"],
            0,
            "Anonymous user should have 0 pending invitations",
        )

    def test_pending_invitations_authenticated_no_invitations(self):
        """Authenticated user with 0 invitations returns count=0."""
        # Create mock request with authenticated user (no invitations)
        request = self.factory.get("/")
        request.user = self.reviewer

        context = pending_invitations(request)

        # Should return 0 when no invitations exist
        self.assertEqual(
            context["pending_invitations_count"],
            0,
            "User with no invitations should have count=0",
        )

    def test_pending_invitations_authenticated_with_invitations(self):
        """Authenticated user with 3 invitations returns count=3."""
        # Create 3 PENDING invitations for reviewer
        for i in range(3):
            session = SearchSession.objects.create(
                title=f"Session {i}",
                owner=self.owner,
                organisation=self.organisation,
                status="ready_for_review",
            )
            ReviewInvitation.objects.create(
                session=session,
                invitee_email=self.reviewer.email,
                invitee_name="Reviewer",
                inviter=self.owner,
                status=ReviewInvitation.STATUS_PENDING,
            )

        # Create 1 ACCEPTED invitation (should NOT be counted)
        accepted_session = SearchSession.objects.create(
            title="Accepted Session",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )
        ReviewInvitation.objects.create(
            session=accepted_session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            invitee=self.reviewer,
            status=ReviewInvitation.STATUS_ACCEPTED,
            responded_at=timezone.now(),
        )

        # Create 1 DECLINED invitation (should NOT be counted)
        declined_session = SearchSession.objects.create(
            title="Declined Session",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )
        ReviewInvitation.objects.create(
            session=declined_session,
            invitee_email=self.reviewer.email,
            invitee_name="Reviewer",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_DECLINED,
            responded_at=timezone.now(),
        )

        # Create mock request with authenticated user
        request = self.factory.get("/")
        request.user = self.reviewer

        context = pending_invitations(request)

        # Should return exactly 3 (only PENDING invitations)
        self.assertEqual(
            context["pending_invitations_count"],
            3,
            "User should have 3 pending invitations (ACCEPTED/DECLINED not counted)",
        )

    def test_pending_invitations_filters_by_email(self):
        """Context processor filters invitations by user email."""
        # Create 2 invitations for reviewer
        for i in range(2):
            session = SearchSession.objects.create(
                title=f"Reviewer Session {i}",
                owner=self.owner,
                organisation=self.organisation,
                status="ready_for_review",
            )
            ReviewInvitation.objects.create(
                session=session,
                invitee_email=self.reviewer.email,
                invitee_name="Reviewer",
                inviter=self.owner,
                status=ReviewInvitation.STATUS_PENDING,
            )

        # Create 1 invitation for different user
        other_user = create_test_user(username_prefix="other")
        other_session = SearchSession.objects.create(
            title="Other User Session",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )
        ReviewInvitation.objects.create(
            session=other_session,
            invitee_email=other_user.email,
            invitee_name="Other User",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Create mock request with reviewer user
        request = self.factory.get("/")
        request.user = self.reviewer

        context = pending_invitations(request)

        # Should return only 2 (reviewer's invitations)
        self.assertEqual(
            context["pending_invitations_count"],
            2,
            "Should only count invitations for authenticated user's email",
        )

    def test_pending_invitations_exception_handling(self):
        """Context processor handles database exceptions gracefully."""
        # Create mock request
        request = self.factory.get("/")
        request.user = self.reviewer

        # Mock ReviewInvitation.objects.filter to raise exception
        original_filter = ReviewInvitation.objects.filter

        def mock_filter(*args, **kwargs):
            raise Exception("Database connection error")

        ReviewInvitation.objects.filter = mock_filter

        try:
            context = pending_invitations(request)

            # Should return 0 on exception (fail gracefully)
            self.assertEqual(
                context["pending_invitations_count"],
                0,
                "Should return 0 when database error occurs",
            )
        finally:
            # Restore original filter method
            ReviewInvitation.objects.filter = original_filter

    def test_pending_invitations_context_key_exists(self):
        """Context dict contains pending_invitations_count key."""
        request = self.factory.get("/")
        request.user = self.reviewer

        context = pending_invitations(request)

        # Should always have the key
        self.assertIn(
            "pending_invitations_count",
            context,
            "Context should always contain pending_invitations_count key",
        )

    def test_pending_invitations_returns_integer(self):
        """Context processor always returns integer count."""
        # Create 5 invitations
        for i in range(5):
            session = SearchSession.objects.create(
                title=f"Session {i}",
                owner=self.owner,
                organisation=self.organisation,
                status="ready_for_review",
            )
            ReviewInvitation.objects.create(
                session=session,
                invitee_email=self.reviewer.email,
                invitee_name="Reviewer",
                inviter=self.owner,
                status=ReviewInvitation.STATUS_PENDING,
            )

        request = self.factory.get("/")
        request.user = self.reviewer

        context = pending_invitations(request)

        # Should be an integer
        self.assertIsInstance(
            context["pending_invitations_count"], int, "Count should be an integer"
        )
        self.assertEqual(context["pending_invitations_count"], 5)
