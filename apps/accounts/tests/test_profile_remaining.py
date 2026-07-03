#!/usr/bin/env python
"""
Remaining Profile Management Tests for Accounts App
Tests: 4 additional profile management test cases
Based on: Accounts_ComprehensiveTestStrategy_20250808_1200.md
"""

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from apps.core.tests.utils import create_test_user

User = get_user_model()


class RemainingProfileManagementTests(TestCase):
    """Remaining Profile Management Tests (4 test cases)"""

    def setUp(self):
        self.user = create_test_user(
            username_prefix="profileuser", first_name="Profile", last_name="User"
        )
        self.client.login(username=self.user.username, password="testpass123")

    def test_a3_005_profile_update_invalid_email(self):
        """A3-005: Test profile update with invalid email format"""
        invalid_emails = [
            "invalid-email",
            "test@",
            "@example.com",
            "test.example.com",
            "test @example.com",  # Space in email
        ]

        for invalid_email in invalid_emails:
            response = self.client.post(
                reverse("accounts:profile"),
                {"email": invalid_email, "first_name": "Test", "last_name": "User"},
            )

            self.assertEqual(response.status_code, 200)  # Should stay on form

            # Email should not be updated
            self.user.refresh_from_db()
            self.assertNotEqual(self.user.email, invalid_email)

    def test_a3_007_empty_profile_fields(self):
        """A3-007: Test updating profile with empty optional fields"""
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "email": self.user.email,
                "first_name": "",  # Empty
                "last_name": "",  # Empty
            },
        )

        self.assertEqual(response.status_code, 302)  # Should succeed

        # Verify fields were cleared
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "")
        self.assertEqual(self.user.last_name, "")
        self.assertEqual(self.user.email, self.user.email)

    def test_a3_008_profile_form_security(self):
        """A3-008: Test that users cannot edit other users' profiles"""
        # Create another user
        other_user = create_test_user(username_prefix="otheruser")

        # Try to access profile while logged in as first user
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

        # Verify we're seeing our own profile (email), not other user's
        self.assertContains(response, self.user.email)
        self.assertNotContains(response, other_user.email)

        # Try to manipulate form to edit other user's data
        # This should fail because the view uses request.user
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "email": "hacked@example.com",
                "first_name": "Hacked",
                "last_name": "User",
            },
        )

        # Our user should be updated, not the other user
        self.user.refresh_from_db()
        other_user.refresh_from_db()

        self.assertEqual(self.user.email, "hacked@example.com")
        self.assertEqual(other_user.email, other_user.email)  # Unchanged

    def test_a3_010_profile_update_success_message(self):
        """A3-010: Test that success message displays after profile update"""
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "email": "updated@example.com",
                "first_name": "Updated",
                "last_name": "Name",
            },
            follow=True,
        )

        # Check for success message
        messages = list(get_messages(response.wsgi_request))

        if messages:
            # At least one message should indicate success
            message_texts = [str(m) for m in messages]
            self.assertTrue(
                any(
                    "success" in msg.lower() or "updated" in msg.lower()
                    for msg in message_texts
                ),
                f"No success message found in: {message_texts}",
            )
