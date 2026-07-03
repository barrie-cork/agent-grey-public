#!/usr/bin/env python
"""
Remaining Registration Tests for Accounts App
Tests: 4 additional registration test cases
Based on: Accounts_ComprehensiveTestStrategy_20250808_1200.md

Note: SignUpForm uses email + password only. Username is auto-generated
from the email prefix (e.g. 'user@example.com' -> username 'user').
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class RemainingRegistrationTests(TestCase):
    """Remaining User Registration Tests (4 test cases)"""

    def test_a2_009_optional_fields_registration(self):
        """A2-009: Test registration with only required fields (email, passwords)"""
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "minimal@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        # Should succeed with just email and passwords
        self.assertEqual(response.status_code, 302)

        # Verify user was created with auto-generated username
        user = User.objects.get(email="minimal@example.com")
        self.assertEqual(user.username, "minimal")  # Auto-generated from email prefix
        self.assertEqual(user.first_name, "")
        self.assertEqual(user.last_name, "")

    def test_a2_010_maximum_length_validation(self):
        """A2-010: Test registration with fields exceeding maximum length"""
        long_email = "a" * 250 + "@example.com"  # Exceeds 254 char limit

        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": long_email,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)  # Should stay on form

        # Should not create user
        self.assertFalse(User.objects.filter(email=long_email).exists())

    def test_a2_011_special_characters_in_registration(self):
        """A2-011: Test registration with special characters in email"""
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "test+filter@example.com",
                "password1": "StrongP@ss123!",
                "password2": "StrongP@ss123!",
            },
        )

        # Should handle special characters properly
        self.assertEqual(response.status_code, 302)

        # Verify user was created with correct data
        user = User.objects.get(email="test+filter@example.com")
        # Username auto-generated from email prefix
        self.assertEqual(user.username, "test+filter")

    def test_a2_012_registration_form_ui_ux(self):
        """A2-012: Test registration form user interface elements"""
        response = self.client.get(reverse("accounts:signup"))
        content = response.content.decode()

        # Verify form fields have proper labels
        self.assertIn("<label", content)
        self.assertIn("Email", content)
        self.assertIn("Password", content)

        # Check for form structure
        self.assertIn("<form", content)
        self.assertIn('method="post"', content.lower())

        # Check for CSRF token
        self.assertIn("csrfmiddlewaretoken", content)

        # Check for submit button
        self.assertIn('type="submit"', content.lower())
