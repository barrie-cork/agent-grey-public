"""Test utilities for creating unique test data."""

import uuid

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save

User = get_user_model()


class DisablePersonalOrgSignalMixin:
    """Disconnect the auto-create personal organisation signal during tests.

    Prevents the post_save signal from creating personal organisations
    when test users are created, avoiding interference with test org setup.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()  # type: ignore[misc]
        post_save.disconnect(
            sender=User,
            dispatch_uid="accounts.create_personal_organisation",
        )

    @classmethod
    def tearDownClass(cls):
        from apps.accounts.signals import create_personal_organisation

        post_save.connect(
            create_personal_organisation,
            sender=User,
            dispatch_uid="accounts.create_personal_organisation",
        )
        super().tearDownClass()  # type: ignore[misc]


def create_test_user(
    username_prefix="testuser", email_domain="example.com", **extra_fields
):
    """
    Create a test user with a unique username.

    Args:
        username_prefix (str): Prefix for the username
        email_domain (str): Domain for the email
        **extra_fields: Additional fields for user creation

    Returns:
        User: Created user instance
    """
    unique_suffix = str(uuid.uuid4())[:8]
    username = f"{username_prefix}_{unique_suffix}"
    email = f"{username}@{email_domain}"

    # Set defaults
    defaults = {
        "email": email,
        "password": "testpass123",
    }
    defaults.update(extra_fields)

    return User.objects.create_user(username=username, **defaults)


def create_test_superuser(
    username_prefix="admin", email_domain="example.com", **extra_fields
):
    """Create a test superuser with a unique username."""
    unique_suffix = str(uuid.uuid4())[:8]
    username = f"{username_prefix}_{unique_suffix}"
    email = f"{username}@{email_domain}"
    defaults = {"email": email, "password": "testpass123"}
    defaults.update(extra_fields)
    return User.objects.create_superuser(username=username, **defaults)


def create_multiple_test_users(count=2, username_prefix="testuser", **extra_fields):
    """
    Create multiple test users with unique usernames.

    Args:
        count (int): Number of users to create
        username_prefix (str): Prefix for usernames
        **extra_fields: Additional fields for user creation

    Returns:
        list: List of created user instances
    """
    users = []
    for i in range(count):
        user = create_test_user(
            username_prefix=f"{username_prefix}_{i}", **extra_fields
        )
        users.append(user)
    return users


def make_session_participant(session, user, inviter=None):
    """Give *user* accepted-invitation access to *session* (the real reviewer path).

    Mirrors how a reviewer actually gains session access: an ACCEPTED
    ``ReviewInvitation`` matched on email. Use in tests where a reviewer must be a
    genuine participant -- since GH #230 the org-membership shortcut no longer
    grants screening access, so a bare org member is no longer a participant.
    """
    import secrets
    from datetime import timedelta

    from django.utils import timezone

    from apps.review_manager.models import ReviewInvitation

    # Idempotent: ReviewInvitation has a unique (session, invitee_email) constraint,
    # so re-inviting the same user must update rather than crash.
    now = timezone.now()
    invitation, _ = ReviewInvitation.objects.update_or_create(
        session=session,
        invitee_email=user.email,
        defaults={
            "inviter": inviter or session.owner,
            "invitee": user,
            "invitee_name": getattr(user, "username", "") or user.email,
            "token": secrets.token_urlsafe(48),
            "status": ReviewInvitation.STATUS_ACCEPTED,
            "responded_at": now,
            "expires_at": now + timedelta(days=7),
        },
    )
    return invitation


class TestUserMixin:
    """Mixin for test cases that need unique test users."""

    def create_test_user(self, username_prefix="testuser", **extra_fields):
        """Create a unique test user for this test case."""
        return create_test_user(username_prefix, **extra_fields)

    def create_multiple_test_users(
        self, count=2, username_prefix="testuser", **extra_fields
    ):
        """Create multiple unique test users for this test case."""
        return create_multiple_test_users(count, username_prefix, **extra_fields)
