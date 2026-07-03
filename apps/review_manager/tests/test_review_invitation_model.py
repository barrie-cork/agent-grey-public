"""
Tests for ReviewInvitation model (Phase 7, Task T046).

Tests the ReviewInvitation model functionality including:
- Token generation
- Expiry logic
- Validation methods
- Magic link generation
- Unique constraints
- String representation
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.organisation.models import Organisation, OrganisationMembership
from apps.review_manager.models import ReviewInvitation, SearchSession
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ReviewInvitationModelTestCase(TestCase):
    """Test suite for ReviewInvitation model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test fixtures once for all tests (class-level)."""
        # Create users
        cls.owner = create_test_user(username_prefix="owner")
        cls.invitee_user = create_test_user(username_prefix="invitee")

        # Create organisation
        cls.organisation = Organisation.objects.create(
            name="Test Organisation", slug="test-org-invitation-model"
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
            description="Test session for invitation model tests",
            owner=self.owner,
            organisation=self.organisation,
            status="ready_for_review",
        )

        # Create request factory for URL generation tests
        self.factory = RequestFactory()

    # -------------------------------------------------------------------------
    # Token Generation Tests
    # -------------------------------------------------------------------------

    def test_create_invitation_generates_token(self):
        """Verify token is auto-generated on save with correct length and format."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="Test User",
            inviter=self.owner,
        )

        # Token should be auto-generated
        self.assertIsNotNone(invitation.token)

        # Token should be 64 characters (48 bytes -> 64 chars base64 URL-safe)
        self.assertEqual(len(invitation.token), 64)

        # Token should be URL-safe (no special chars except - and _)
        self.assertTrue(
            all(c.isalnum() or c in "-_" for c in invitation.token),
            "Token should only contain alphanumeric characters, hyphens, and underscores",
        )

    def test_token_uniqueness(self):
        """Verify that tokens are unique across multiple invitations."""
        tokens = set()

        # Create 100 invitations
        for i in range(100):
            invitation = ReviewInvitation.objects.create(
                session=self.session,
                invitee_email=f"user{i}@example.com",
                invitee_name=f"User {i}",
                inviter=self.owner,
            )
            tokens.add(invitation.token)

        # All tokens should be unique
        self.assertEqual(
            len(tokens), 100, "All 100 tokens should be unique (no collisions)"
        )

    # -------------------------------------------------------------------------
    # Expiry Logic Tests
    # -------------------------------------------------------------------------

    def test_create_invitation_sets_expiry_7_days(self):
        """Verify expiry is set to invited_at + 7 days."""
        _before_creation = timezone.now()

        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="Test User",
            inviter=self.owner,
        )

        after_creation = timezone.now()

        # expires_at should be auto-set
        self.assertIsNotNone(invitation.expires_at)

        # expires_at should be approximately 7 days after invited_at
        expiry_delta = invitation.expires_at - invitation.invited_at
        expected_delta = timedelta(days=7)

        # Allow 1 second tolerance for test execution time
        self.assertAlmostEqual(
            expiry_delta.total_seconds(),
            expected_delta.total_seconds(),
            delta=1,
            msg="Expiry should be 7 days after invited_at",
        )

        # expires_at should be in the future
        self.assertGreater(
            invitation.expires_at, after_creation, "Expiry should be in the future"
        )

    # -------------------------------------------------------------------------
    # Validation Tests
    # -------------------------------------------------------------------------

    def test_is_valid_pending_not_expired(self):
        """Valid invitation (PENDING, not expired) returns True."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="Test User",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Should be valid (pending and not expired)
        self.assertTrue(
            invitation.is_valid(), "Pending non-expired invitation should be valid"
        )

    def test_is_valid_expired_auto_updates_status(self):
        """Expired invitation auto-updates status to EXPIRED and returns False."""
        # Create invitation with expired time
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="Test User",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_PENDING,
        )

        # Manually set expires_at to past
        invitation.expires_at = timezone.now() - timedelta(days=1)
        invitation.save()

        # Refresh from database
        invitation.refresh_from_db()

        # is_valid() should return False
        self.assertFalse(
            invitation.is_valid(), "Expired invitation should not be valid"
        )

        # Refresh from database to check status update
        invitation.refresh_from_db()

        # Status should be auto-updated to EXPIRED
        self.assertEqual(
            invitation.status,
            ReviewInvitation.STATUS_EXPIRED,
            "Expired invitation status should be auto-updated to EXPIRED",
        )

    def test_is_valid_accepted_invitation(self):
        """Accepted invitation returns False from is_valid()."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="Test User",
            inviter=self.owner,
            status=ReviewInvitation.STATUS_ACCEPTED,
        )

        # Should not be valid (already accepted)
        self.assertFalse(
            invitation.is_valid(),
            "Accepted invitation should not be valid for re-acceptance",
        )

    # -------------------------------------------------------------------------
    # Unique Constraint Tests
    # -------------------------------------------------------------------------

    def test_unique_together_session_email(self):
        """Duplicate (session, email) raises IntegrityError."""
        # Create first invitation
        ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="duplicate@example.com",
            invitee_name="First Invitation",
            inviter=self.owner,
        )

        # Attempt to create second invitation with same session + email
        with self.assertRaises(
            IntegrityError, msg="Duplicate (session, email) should raise IntegrityError"
        ):
            ReviewInvitation.objects.create(
                session=self.session,
                invitee_email="duplicate@example.com",
                invitee_name="Second Invitation (Should Fail)",
                inviter=self.owner,
            )

    # -------------------------------------------------------------------------
    # Magic Link Tests
    # -------------------------------------------------------------------------

    def test_get_magic_link_absolute_url(self):
        """Magic link returns full URL with token."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="Test User",
            inviter=self.owner,
        )

        # Create mock request
        request = self.factory.get("/")
        request.META["HTTP_HOST"] = "testserver"

        # Get magic link
        magic_link = invitation.get_magic_link(request)

        # Should be absolute URL
        self.assertTrue(
            magic_link.startswith("http://") or magic_link.startswith("https://"),
            f"Magic link should be absolute URL, got: {magic_link}",
        )

        # Should contain token
        self.assertIn(
            invitation.token, magic_link, "Magic link should contain invitation token"
        )

        # Should contain accept invitation path
        self.assertIn(
            "/invitations/accept/",
            magic_link,
            "Magic link should contain /invitations/accept/ path",
        )

    # -------------------------------------------------------------------------
    # String Representation Tests
    # -------------------------------------------------------------------------

    def test_str_representation(self):
        """__str__() returns expected format with email and session title."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="user@example.com",
            invitee_name="Test User",
            inviter=self.owner,
        )

        str_repr = str(invitation)

        # Should contain email
        self.assertIn(
            "user@example.com", str_repr, "__str__() should contain invitee email"
        )

        # Should contain session title
        self.assertIn(
            "Test Session", str_repr, "__str__() should contain session title"
        )

        # Should match expected format
        self.assertEqual(
            str_repr,
            "Invitation: user@example.com to Test Session",
            "__str__() should match expected format",
        )

    # -------------------------------------------------------------------------
    # Edge Case Tests
    # -------------------------------------------------------------------------

    def test_invitation_with_null_inviter(self):
        """Invitation can be created with null inviter (inviter deleted)."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="Test User",
            inviter=None,  # No inviter
        )

        # Should save successfully
        self.assertIsNotNone(invitation.id)
        self.assertIsNone(invitation.inviter)

    def test_invitation_without_invitee_name(self):
        """Invitation can be created without invitee_name (blank)."""
        invitation = ReviewInvitation.objects.create(
            session=self.session,
            invitee_email="test@example.com",
            invitee_name="",  # Blank name
            inviter=self.owner,
        )

        # Should save successfully
        self.assertIsNotNone(invitation.id)
        self.assertEqual(invitation.invitee_name, "")
