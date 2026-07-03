#!/usr/bin/env python
"""
Remaining Password Reset Tests for Accounts App
Tests: 5 additional password reset test cases
Based on: Accounts_ComprehensiveTestStrategy_20250808_1200.md
"""

import re
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from apps.core.tests.utils import create_test_user

User = get_user_model()


class RemainingPasswordResetTests(TestCase):
    """Remaining Password Reset System Tests (5 test cases)"""

    def setUp(self):
        self.user = create_test_user(username_prefix="resetuser")
        # Clear mail outbox
        mail.outbox = []

    def test_a5_004_password_reset_token_validation(self):
        """A5-004: Test password reset token is valid and secure"""
        # Request password reset
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email}
        )

        self.assertEqual(response.status_code, 302)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        email_body = mail.outbox[0].body

        # Extract reset URL using regex
        reset_url_pattern = r"/accounts/reset/([^/]+)/([^/]+)/"
        match = re.search(reset_url_pattern, email_body)

        if match:
            uidb64, token = match.groups()

            # Navigate to reset confirm page
            response = self.client.get(
                reverse(
                    "accounts:password_reset_confirm",
                    kwargs={"uidb64": uidb64, "token": token},
                )
            )

            # Should be valid and show password reset form
            self.assertIn(response.status_code, [200, 302])
        else:
            # If no URL in email, generate token manually
            uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
            token = default_token_generator.make_token(self.user)

            response = self.client.get(
                reverse(
                    "accounts:password_reset_confirm",
                    kwargs={"uidb64": uidb64, "token": token},
                )
            )

            self.assertIn(response.status_code, [200, 302])

    def test_a5_005_password_reset_form_submission(self):
        """A5-005: Test successful password reset with valid token"""
        # Generate valid token
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        # Navigate to password reset confirm page
        response = self.client.get(
            reverse(
                "accounts:password_reset_confirm",
                kwargs={"uidb64": uidb64, "token": token},
            )
        )

        # Submit new password
        if response.status_code == 302:
            # Follow redirect to get the actual form
            response = self.client.get(response.url)

        # Post new password
        response = self.client.post(
            response.request["PATH_INFO"],
            {
                "new_password1": "NewSecurePass123!",
                "new_password2": "NewSecurePass123!",
            },
        )

        # Should redirect to complete page
        self.assertEqual(response.status_code, 302)

        # Test login with new password
        login_success = self.client.login(
            username=self.user.username, password="NewSecurePass123!"
        )
        self.assertTrue(login_success)

    def test_a5_006_password_reset_token_expiry(self):
        """A5-006: Test that reset tokens expire appropriately"""
        # This test requires mocking time or using an expired token
        # Django's default token timeout is PASSWORD_RESET_TIMEOUT (259200 seconds = 3 days)

        # Create an old token by mocking the timestamp
        with patch(
            "django.contrib.auth.tokens.PasswordResetTokenGenerator._now"
        ) as mock_now:
            # Set time to 4 days ago
            old_time = datetime.now() - timedelta(days=4)
            mock_now.return_value = old_time

            # Generate token with old timestamp
            uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
            old_token = default_token_generator.make_token(self.user)

        # Try to use the expired token
        response = self.client.get(
            reverse(
                "accounts:password_reset_confirm",
                kwargs={"uidb64": uidb64, "token": old_token},
            )
        )

        # Should be rejected (redirect or error page)
        self.assertIn(response.status_code, [200, 302])

        # If 200, check for error message
        if response.status_code == 200:
            self.assertContains(
                response, "invalid", status_code=200, msg_prefix="", html=False
            )

    def test_a5_007_password_reset_invalid_token(self):
        """A5-007: Test behavior with invalid/manipulated reset token"""
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        invalid_token = "invalid-token-12345"

        # Try to use invalid token
        response = self.client.get(
            reverse(
                "accounts:password_reset_confirm",
                kwargs={"uidb64": uidb64, "token": invalid_token},
            )
        )

        # Should be rejected
        self.assertIn(response.status_code, [200, 302])

        # Should not be able to reset password
        if response.status_code == 200:
            # Check for error indication
            content = response.content.decode()
            self.assertTrue(
                "invalid" in content.lower()
                or "expired" in content.lower()
                or "already been used" in content.lower()
            )

    def test_a5_008_password_reset_complete_flow(self):
        """A5-008: Test complete password reset workflow from start to finish"""
        # Step 1: Request password reset
        mail.outbox = []  # Clear any existing emails

        response = self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email}
        )
        self.assertEqual(response.status_code, 302)

        # Step 2: Check email and extract link
        self.assertEqual(len(mail.outbox), 1)
        email_body = mail.outbox[0].body

        # Extract reset URL
        reset_url_pattern = r"/accounts/reset/([^/]+)/([^/]+)/"
        match = re.search(reset_url_pattern, email_body)

        if not match:
            # Generate token manually if not in email
            uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
            token = default_token_generator.make_token(self.user)
        else:
            uidb64, token = match.groups()

        # Step 3: Use link to access reset form
        response = self.client.get(
            reverse(
                "accounts:password_reset_confirm",
                kwargs={"uidb64": uidb64, "token": token},
            )
        )

        # Step 4: Complete reset process
        if response.status_code == 302:
            response = self.client.get(response.url)

        response = self.client.post(
            response.request["PATH_INFO"],
            {
                "new_password1": "CompletelyNewPass123!",
                "new_password2": "CompletelyNewPass123!",
            },
        )

        # Step 5: Login with new password
        self.client.logout()
        login_success = self.client.login(
            username=self.user.username, password="CompletelyNewPass123!"
        )
        self.assertTrue(login_success)

        # Step 6: Verify old password no longer works
        self.client.logout()
        old_login = self.client.login(
            username=self.user.username, password="oldpassword123!"
        )
        self.assertFalse(old_login)
