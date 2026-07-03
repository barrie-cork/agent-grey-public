"""
Tests for accounts signals (email notifications).
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from apps.core.tests.utils import create_test_user

User = get_user_model()


class UserRegistrationEmailTest(TestCase):
    """Test email notifications when users register."""

    def setUp(self):
        """Clear email outbox before each test."""
        mail.outbox = []

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ADMINS=[("Test Admin", "admin@test.com")],
        DEFAULT_FROM_EMAIL="noreply@test.com",
        SITE_DOMAIN="testserver",
    )
    def test_welcome_email_sent_on_user_creation(self):
        """Test that welcome email is sent when user is created."""
        user = create_test_user(first_name="Test", last_name="User")

        # Check that emails were sent
        self.assertEqual(len(mail.outbox), 2)  # Welcome email + admin notification

        # Check welcome email
        welcome_email = mail.outbox[0]
        self.assertIn(user.email, welcome_email.to)
        self.assertIn("Welcome to Agent Grey!", welcome_email.subject)
        self.assertIn("Hello Test User", welcome_email.body)
        self.assertIn(user.username, welcome_email.body)
        self.assertIn("dashboard", welcome_email.body)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ADMINS=[("Test Admin", "admin@test.com")],
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_admin_notification_sent_on_user_creation(self):
        """Test that admin notification is sent when user is created."""
        user = create_test_user()

        # Check that emails were sent
        self.assertEqual(len(mail.outbox), 2)

        # Check admin notification email
        admin_email = mail.outbox[1]
        self.assertIn("admin@test.com", admin_email.to)
        self.assertIn(f"New user registered: {user.username}", admin_email.subject)
        self.assertIn(user.username, admin_email.body)
        self.assertIn(user.email, admin_email.body)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ADMINS=[("Test Admin", "admin@test.com")],
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_no_email_sent_when_user_has_no_email(self):
        """Test that no welcome email is sent when user has no email address."""
        # Create a user without email by using User.objects directly
        User.objects.create_user(
            username="noemail_user", email="", password="testpass123"
        )

        # Should not send any emails since user has no email
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ADMINS=[],  # No admins configured
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_no_admin_email_when_no_admins_configured(self):
        """Test that no admin email is sent when no admins are configured."""
        _user = create_test_user()

        # Should only send welcome email, not admin email
        self.assertEqual(len(mail.outbox), 1)

        # Check it's the welcome email
        welcome_email = mail.outbox[0]
        self.assertIn("Welcome to Agent Grey!", welcome_email.subject)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ADMINS=[("Test Admin", "admin@test.com")],
        DEFAULT_FROM_EMAIL="noreply@test.com",
    )
    def test_no_email_sent_on_user_update(self):
        """Test that no email is sent when user is updated (not created)."""
        user = create_test_user()

        # Clear email outbox
        mail.outbox = []

        # Update the user
        user.first_name = "Updated"
        user.save()

        # Should not send any emails on update
        self.assertEqual(len(mail.outbox), 0)
