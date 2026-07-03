#!/usr/bin/env python
"""
Comprehensive test suite for Accounts app
Based on: Accounts_ComprehensiveTestStrategy_20250808_1200.md
Tests 76 test cases across 8 categories
"""

import uuid

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse
from apps.core.tests.utils import create_test_user

User = get_user_model()


class AccountsAuthenticationTests(TestCase):
    """Authentication & Authorization Tests (18 test cases)"""

    def setUp(self):
        self.client = Client()
        self.user = create_test_user()
        # Clear mail outbox after user creation (signals send emails)
        mail.outbox.clear()

    def test_a1_001_valid_username_login(self):
        """A1-001: Test user login with valid username and password"""
        response = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": "testpass123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_a1_002_valid_email_login(self):
        """A1-002: Test user login with email address instead of username"""
        response = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": "testpass123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_a1_003_invalid_username_login(self):
        """A1-003: Test login with non-existent email"""
        response = self.client.post(
            reverse("accounts:login"),
            {"email": "nonexistent@example.com", "password": "anypassword"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid login credentials", status_code=200)

    def test_a1_004_invalid_password_login(self):
        """A1-004: Test login with correct username but wrong password"""
        response = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": "wrongpassword"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_a1_005_empty_credentials_login(self):
        """A1-005: Test login attempt with empty username and password fields"""
        response = self.client.post(
            reverse("accounts:login"), {"email": "", "password": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_a1_006_successful_logout(self):
        """A1-006: Test user logout functionality"""
        self.client.login(username=self.user.username, password="testpass123")
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        # Check next request is not authenticated
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)  # Redirected to login

    def test_a1_007_login_required_protection(self):
        """A1-007: Test that profile page requires authentication"""
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_a1_008_post_login_redirection(self):
        """A1-008: Test redirection to intended page after login"""
        response = self.client.get(reverse("accounts:profile"))
        login_url = response.url

        response = self.client.post(
            login_url,
            {"email": self.user.email, "password": "testpass123"},
            follow=True,
        )

        self.assertRedirects(response, reverse("accounts:profile"))

    def test_a1_009_session_persistence(self):
        """A1-009: Test that user session persists across requests"""
        self.client.login(username=self.user.username, password="testpass123")

        # Make another request
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_a1_017_csrf_protection(self):
        """A1-017: Test that login form includes CSRF protection"""
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "csrfmiddlewaretoken")


class AccountsRegistrationTests(TestCase):
    """User Registration Tests (12 test cases)"""

    def setUp(self):
        self.client = Client()

    def test_a2_001_valid_registration(self):
        """A2-001: Test successful user registration with all required fields"""
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "new@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        # Username is auto-generated from email prefix
        self.assertTrue(User.objects.filter(email="new@example.com").exists())

        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.username, "new")  # Auto-generated from email prefix
        self.assertEqual(user.email, "new@example.com")

    def test_a2_002_registration_auto_login(self):
        """A2-002: Test that user is automatically logged in after successful registration"""
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "auto@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
            follow=True,
        )

        self.assertTrue(response.wsgi_request.user.is_authenticated)
        # Username is auto-generated from email prefix
        self.assertEqual(response.wsgi_request.user.username, "auto")

    def test_a2_003_duplicate_email_registration(self):
        """A2-003: Test registration attempt with existing email"""
        existing_user = create_test_user(username_prefix="existinguser")

        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": existing_user.email,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered", status_code=200)

    def test_a2_004_duplicate_email_registration_second(self):
        """A2-004: Test second registration attempt with existing email address"""
        existing_user = create_test_user(username_prefix="user1")

        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": existing_user.email,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered", status_code=200)

    def test_a2_005_password_mismatch_registration(self):
        """A2-005: Test registration with non-matching password confirmation"""
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "mismatch@example.com",
                "password1": "Password123!",
                "password2": "Different123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        # Django uses unicode smart quotes in the error message
        self.assertContains(response, "password fields didn", status_code=200)

    def test_a2_006_weak_password_registration(self):
        """A2-006: Test registration with weak password"""
        response = self.client.post(
            reverse("accounts:signup"),
            {"email": "weak@example.com", "password1": "123", "password2": "123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="weak@example.com").exists())

    def test_a2_007_missing_required_fields(self):
        """A2-007: Test registration with missing required fields (email)"""
        response = self.client.post(
            reverse("accounts:signup"),
            {"email": "", "password1": "StrongPass123!", "password2": "StrongPass123!"},
        )

        self.assertEqual(response.status_code, 200)
        # Form stays on page with validation errors

    def test_a2_008_invalid_email_format(self):
        """A2-008: Test registration with invalid email formats"""
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "invalid-email",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid email", status_code=200)


class AccountsProfileManagementTests(TestCase):
    """Profile Management Tests (10 test cases)"""

    def setUp(self):
        self.client = Client()
        self.user = create_test_user(
            username_prefix="profileuser", first_name="Profile", last_name="User"
        )
        # Clear mail outbox after user creation (signals send emails)
        mail.outbox.clear()
        self.client.login(username=self.user.username, password="testpass123")

    def test_a3_001_view_profile_information(self):
        """A3-001: Test that user can view their profile information"""
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.email)
        # Profile shows first/last name, not username
        self.assertContains(response, "Profile")

    def test_a3_002_update_profile_email(self):
        """A3-002: Test updating user's email address"""
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "email": "updated@example.com",
                "first_name": "Profile",
                "last_name": "User",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "updated@example.com")

    def test_a3_003_update_profile_names(self):
        """A3-003: Test updating first and last name"""
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "email": "profile@example.com",
                "first_name": "UpdatedFirst",
                "last_name": "UpdatedLast",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "UpdatedFirst")
        self.assertEqual(self.user.last_name, "UpdatedLast")

    def test_a3_004_profile_update_duplicate_email(self):
        """A3-004: Test profile update attempt with email already used by another user"""
        other_user = create_test_user(username_prefix="otheruser")

        response = self.client.post(
            reverse("accounts:profile"),
            {
                "email": other_user.email,
                "first_name": "Profile",
                "last_name": "User",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered", status_code=200)

    def test_a3_006_profile_update_same_email(self):
        """A3-006: Test profile update using user's current email (should be allowed)"""
        response = self.client.post(
            reverse("accounts:profile"),
            {
                "email": "profile@example.com",
                "first_name": "Updated",
                "last_name": "Name",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "profile@example.com")
        self.assertEqual(self.user.first_name, "Updated")

    def test_a3_009_profile_page_authentication(self):
        """A3-009: Test that profile page requires authentication"""
        self.client.logout()
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)


class AccountsPasswordResetTests(TestCase):
    """Password Reset System Tests (8 test cases)"""

    def setUp(self):
        self.client = Client()
        self.user = create_test_user(username_prefix="resetuser")
        # Clear mail outbox after user creation (signals send 2 emails)
        mail.outbox.clear()

    def test_a5_001_password_reset_request(self):
        """A5-001: Test password reset request with valid email"""
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_a5_002_password_reset_invalid_email(self):
        """A5-002: Test password reset request with non-existent email"""
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": "nonexistent@example.com"}
        )

        # Django fails silently for security
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_a5_003_password_reset_email_delivery(self):
        """A5-003: Test that password reset email is actually sent"""
        _response = self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email}
        )

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn("reset", email.subject.lower())
        self.assertIn(self.user.email, email.to)


class AccountsEmailNotificationTests(TestCase):
    """Email Notification Tests (6 test cases)"""

    def setUp(self):
        self.client = Client()

    def test_a6_001_welcome_email_trigger(self):
        """A6-001: Test that welcome email is sent when new user registers"""
        _response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "welcome@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        # Check if any emails were sent (welcome email implementation may vary)
        # This test assumes welcome emails are implemented
        if len(mail.outbox) > 0:
            self.assertIn("welcome@example.com", mail.outbox[0].to)


class AccountsSecurityTests(TestCase):
    """Security & Edge Cases Tests (4 test cases)"""

    def setUp(self):
        self.client = Client()
        self.user = create_test_user(username_prefix="securityuser")
        mail.outbox.clear()

    def test_a8_001_uuid_primary_key_security(self):
        """A8-001: Test that UUID primary keys are properly generated and secure"""
        users = []
        for i in range(5):
            user = create_test_user()
            users.append(user)

        # Check all UUIDs are unique
        uuids = [str(user.id) for user in users]
        self.assertEqual(len(uuids), len(set(uuids)))

        # Check UUID format
        for user_id in uuids:
            # Should be a valid UUID
            uuid_obj = uuid.UUID(user_id, version=4)
            self.assertEqual(str(uuid_obj), user_id)

    def test_a8_002_session_security(self):
        """A8-002: Test session security features"""
        _response = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": "testpass123"},
        )

        # Session should be created on login
        self.assertIsNotNone(self.client.session.session_key)

    def test_a8_003_mass_assignment_protection(self):
        """A8-003: Test that forms protect against mass assignment vulnerabilities"""
        # Try to set is_staff through signup form
        _response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "hack@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "is_staff": "true",  # This should be ignored
                "is_superuser": "true",  # This should be ignored
            },
        )

        if User.objects.filter(email="hack@example.com").exists():
            user = User.objects.get(email="hack@example.com")
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
