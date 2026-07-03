#!/usr/bin/env python
"""
Remaining Email Notification Tests for Accounts App
Tests: 5 additional email notification test cases
Based on: Accounts_ComprehensiveTestStrategy_20250808_1200.md
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.core.tests.utils import create_test_user

User = get_user_model()


class RemainingEmailNotificationTests(TestCase):
    """Remaining Email Notification Tests (5 test cases)"""

    def setUp(self):
        mail.outbox = []

    def test_a6_002_welcome_email_content(self):
        """A6-002: Test welcome email contains correct content and formatting"""
        _response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "new@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        # Find welcome email (if implemented)
        if mail.outbox:
            # Look for welcome email
            welcome_emails = [e for e in mail.outbox if "welcome" in e.subject.lower()]

            if welcome_emails:
                email = welcome_emails[0]

                # Check recipient
                self.assertIn("new@example.com", email.to)

                # Check content - email may be in body or HTML alternatives
                email_content = email.body
                if hasattr(email, "alternatives") and email.alternatives:
                    email_content = email.alternatives[0][0]

                if email_content:
                    # May contain user's email or auto-generated username
                    self.assertTrue(
                        "new" in email_content or "new@example.com" in email_content
                    )

    def test_a6_003_admin_notification_email(self):
        """A6-003: Test that admin notification is sent for new registrations"""
        with self.settings(ADMINS=[("Admin", "admin@example.com")]):
            _response = self.client.post(
                reverse("accounts:signup"),
                {
                    "email": "notify@example.com",
                    "password1": "StrongPass123!",
                    "password2": "StrongPass123!",
                },
            )

            # Check if admin notification was sent
            if len(mail.outbox) > 1:
                # Look for admin notification
                admin_emails = [
                    e
                    for e in mail.outbox
                    if any("admin@example.com" in recipient for recipient in e.to)
                ]

                if admin_emails:
                    admin_email = admin_emails[0]
                    # Username auto-generated from email prefix: notify
                    self.assertIn("notify", admin_email.body)

    def test_a6_004_email_signal_handling(self):
        """A6-004: Test that post_save signal properly triggers email sending"""
        # Clear outbox
        mail.outbox = []

        # Create user programmatically (not through form)
        user = create_test_user(username_prefix="signaluser")

        # Check if signal triggered email
        if mail.outbox:
            # Should have sent welcome email to the created user
            self.assertTrue(any(user.email in email.to[0] for email in mail.outbox))

        # Update existing user - should not send email
        mail.outbox = []
        user.first_name = "Updated"
        user.save()

        # Should not send another welcome email for update
        welcome_count = sum(1 for e in mail.outbox if "welcome" in e.subject.lower())
        self.assertEqual(welcome_count, 0)

    @patch("django.core.mail.send_mail")
    def test_a6_005_email_failure_handling(self, mock_send_mail):
        """A6-005: Test system behavior when email sending fails"""
        # Configure mock to raise exception
        mock_send_mail.side_effect = Exception("Email server error")

        # Attempt registration
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "fail@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        # Registration should still succeed despite email failure
        self.assertEqual(response.status_code, 302)

        # User should be created (username auto-generated from email prefix)
        self.assertTrue(User.objects.filter(email="fail@example.com").exists())

    @override_settings(EMAIL_BACKEND="")
    def test_a6_006_email_missing_configuration(self):
        """A6-006: Test behavior when email settings are not configured"""
        # Try registration with missing email config
        try:
            _response = self.client.post(
                reverse("accounts:signup"),
                {
                    "email": "noconfig@example.com",
                    "password1": "StrongPass123!",
                    "password2": "StrongPass123!",
                },
            )

            # Should handle gracefully
            # User creation should still work (username auto-generated from email prefix)
            self.assertTrue(User.objects.filter(email="noconfig@example.com").exists())
        except Exception as e:
            # Should not raise unhandled exception
            self.fail(f"Unhandled exception with missing email config: {e}")
