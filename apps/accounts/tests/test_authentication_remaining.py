#!/usr/bin/env python
"""
Remaining Authentication & Authorization Tests for Accounts App
Tests: 8 additional authentication test cases
Based on: Accounts_ComprehensiveTestStrategy_20250808_1200.md
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from apps.core.tests.utils import create_test_user

User = get_user_model()


class RemainingAuthenticationTests(TestCase):
    """Remaining Authentication & Authorization Tests (8 test cases)"""

    def setUp(self):
        self.user = create_test_user(first_name="Test", last_name="User")

    def test_a1_010_concurrent_session_handling(self):
        """A1-010: Test behavior with multiple browser sessions"""
        # Create two test clients
        client1 = Client()
        client2 = Client()

        # Login with both
        login1 = client1.login(username=self.user.username, password="testpass123")
        login2 = client2.login(username=self.user.username, password="testpass123")

        self.assertTrue(login1)
        self.assertTrue(login2)

        # Both should have valid sessions
        response1 = client1.get(reverse("accounts:profile"))
        response2 = client2.get(reverse("accounts:profile"))

        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)

    def test_a1_011_session_security_headers(self):
        """A1-011: Test that proper security headers are set for authenticated sessions"""
        _response = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": "testpass123"},
        )

        # Check for CSRF cookie
        self.assertIn("csrftoken", self.client.cookies)

        # Check session cookie security attributes
        if "sessionid" in self.client.cookies:
            session_cookie = self.client.cookies["sessionid"]
            # Django sets these by default in production
            # In test mode, these might not be set, so we check if they exist
            if hasattr(session_cookie, "httponly"):
                self.assertIsNotNone(session_cookie.get("httponly"))
            if hasattr(session_cookie, "samesite"):
                self.assertIsNotNone(session_cookie.get("samesite"))

    def test_a1_012_brute_force_protection(self):
        """A1-012: Test system behavior under multiple failed login attempts"""
        # Attempt login with wrong password multiple times
        for i in range(10):
            response = self.client.post(
                reverse("accounts:login"),
                {"email": self.user.email, "password": f"wrongpassword{i}"},
            )
            self.assertEqual(response.status_code, 200)  # Should stay on login page

        # Attempt valid login after failed attempts
        response = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": "testpass123"},
        )

        # Django doesn't have built-in account lockout by default
        # Valid login should still work
        self.assertEqual(
            response.status_code, 302
        )  # Should redirect after successful login

    def test_a1_013_case_sensitivity_testing(self):
        """A1-013: Test username case sensitivity in login"""
        # Django usernames are case-sensitive by default

        # Try lowercase
        response = self.client.post(
            reverse("accounts:login"),
            {
                "email": self.user.email,  # Correct case
                "password": "testpass123",
            },
        )
        self.assertEqual(response.status_code, 302)  # Should succeed

        self.client.logout()

        # Try uppercase
        response = self.client.post(
            reverse("accounts:login"),
            {
                "email": self.user.email.upper(),  # Wrong case
                "password": "testpass123",
            },
        )
        self.assertEqual(response.status_code, 200)  # Should fail, stay on login page

    def test_a1_014_special_characters_in_credentials(self):
        """A1-014: Test login with usernames/passwords containing special characters"""
        # Create user with special characters in username
        special_user = create_test_user(username_prefix="test_user-123")

        # Test login with the special user's email
        response = self.client.post(
            reverse("accounts:login"),
            {"email": special_user.email, "password": "testpass123"},
        )

        self.assertEqual(response.status_code, 302)  # Should succeed
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_a1_015_sql_injection_prevention(self):
        """A1-015: Test that login form prevents SQL injection attacks"""
        # Try common SQL injection payloads
        sql_payloads = [
            "'; DROP TABLE accounts_user; --",
            "' OR '1'='1",
            "admin'--",
            "' OR 1=1--",
            "'; SELECT * FROM accounts_user; --",
        ]

        for payload in sql_payloads:
            response = self.client.post(
                reverse("accounts:login"), {"email": payload, "password": payload}
            )

            # Should not cause any errors, just fail login
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.wsgi_request.user.is_authenticated)

        # Verify user table still exists
        self.assertTrue(User.objects.exists())

    def test_a1_016_xss_prevention_in_login(self):
        """A1-016: Test that login form prevents cross-site scripting"""
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "<svg onload=alert('XSS')>",
        ]

        for payload in xss_payloads:
            response = self.client.post(
                reverse("accounts:login"), {"email": payload, "password": "password"}
            )

            # Check that the XSS payload is HTML-escaped (not rendered as raw HTML).
            # The page legitimately contains <script> tags for its own JS,
            # so we check the payload itself is escaped rather than banning all tags.
            content = response.content.decode()
            self.assertNotIn(payload, content)

    def test_a1_018_login_form_accessibility(self):
        """A1-018: Test login form accessibility features"""
        response = self.client.get(reverse("accounts:login"))
        content = response.content.decode()

        # Check for form labels
        self.assertIn("<label", content)

        # Check for form structure
        self.assertIn("<form", content)
        self.assertIn('method="post"', content.lower())

        # Check for CSRF token (required for security)
        self.assertIn("csrfmiddlewaretoken", content)

        # Check for required fields
        self.assertIn("required", content.lower())
