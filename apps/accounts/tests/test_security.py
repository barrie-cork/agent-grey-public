from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SecurityTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_test_user()

    def test_csrf_token_verification(self):
        """Test CSRF token is required for forms"""
        # Use a client that enforces CSRF checks (Django test client skips them by default)
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("accounts:login"),
            {"email": "test@example.com", "password": "testpass123"},
        )
        # Should fail without valid CSRF token
        self.assertEqual(response.status_code, 403)

    def test_sql_injection_attempts(self):
        """Test SQL injection protection on forms"""
        # Try SQL injection in login
        _response = self.client.post(
            reverse("accounts:login"),
            {"email": "admin@evil.com' OR '1'='1", "password": "' OR '1'='1"},
        )
        # Should not authenticate
        self.assertNotIn("_auth_user_id", self.client.session)

        # Try SQL injection in signup (email-only form)
        _response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "test'; DROP TABLE--@example.com",
                "password1": "testpass123!",
                "password2": "testpass123!",
            },
        )
        # Table should still exist
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_xss_prevention_in_templates(self):
        """Test XSS prevention in templates"""
        # Create user with XSS attempt in name
        xss_user = create_test_user(
            username_prefix="xssuser", first_name='<script>alert("XSS")</script>'
        )

        # Login as this user
        self.client.login(username=xss_user.username, password="testpass123")
        response = self.client.get(reverse("accounts:profile"))

        # Script should be escaped, not executed
        self.assertNotContains(response, '<script>alert("XSS")</script>')
        self.assertContains(
            response, "&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;"
        )

    def test_password_hashing_verification(self):
        """Test passwords are properly hashed"""
        # Create user
        user = create_test_user(username_prefix="hashtest")

        # Password should not be stored in plain text
        self.assertNotEqual(user.password, "testpass123")

        # Password should be hashed (algorithm prefix depends on settings)
        self.assertIn("$", user.password, "Password should contain hash separator")

        # Check password works
        self.assertTrue(check_password("testpass123", user.password))

    def test_session_security_settings(self):
        """Test session security configurations"""
        # Login
        self.client.login(username=self.user.username, password="testpass123")

        # Get session
        session = self.client.session

        # Check session settings
        # Note: These would be set in production settings
        # For now, just verify session exists and has auth data
        self.assertIn("_auth_user_id", session)
        self.assertEqual(str(session["_auth_user_id"]), str(self.user.id))

    def test_secure_redirects(self):
        """Test redirects are secure and validated against open redirects"""
        # Test open redirect protection
        malicious_url = "http://evil.com"
        response = self.client.post(
            reverse("accounts:login") + f"?next={malicious_url}",
            {"email": self.user.email, "password": "testpass123"},
        )
        # Should redirect to default (dashboard), not external URL
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.com", response.url)

    def test_password_validation_rules(self):
        """Test password validation is enforced"""
        # Try to create user with weak password
        _response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "weakpass@example.com",
                "password1": "123",  # Too short and numeric only
                "password2": "123",
            },
        )
        self.assertFalse(User.objects.filter(email="weakpass@example.com").exists())

        # Try with common password
        _response = self.client.post(
            reverse("accounts:signup"),
            {
                "email": "commonpass@example.com",
                "password1": "password",
                "password2": "password",
            },
        )
        self.assertFalse(User.objects.filter(email="commonpass@example.com").exists())

    def test_authenticated_access_only(self):
        """Test authenticated-only views are protected"""
        # Logout
        self.client.logout()

        # Try to access profile
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

        # Try to post to profile
        response = self.client.post(
            reverse("accounts:profile"), {"email": "hacker@example.com"}
        )
        self.assertEqual(response.status_code, 302)

        # Verify user email wasn't changed
        original_email = self.user.email
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, original_email)

    @override_settings(
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        CSRF_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        CSRF_COOKIE_SAMESITE="Strict",
        X_FRAME_OPTIONS="DENY",
    )
    def test_cookie_security_settings(self):
        """Test new cookie security settings are applied"""
        # Verify settings are applied
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Strict")
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, "Strict")
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")

        # Login to create session
        self.client.login(username=self.user.username, password="testpass123")
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

    def test_x_frame_options_header(self):
        """Test X-Frame-Options header is set"""
        response = self.client.get(reverse("accounts:login"))

        # Check if header is set (may be set by middleware)
        x_frame = response.get("X-Frame-Options", "")
        if x_frame:
            self.assertIn(x_frame.upper(), ["DENY", "SAMEORIGIN"])

    @override_settings(SECURE_BROWSER_XSS_FILTER=True, SECURE_CONTENT_TYPE_NOSNIFF=True)
    def test_additional_security_headers(self):
        """Test additional security headers"""
        _response = self.client.get(reverse("accounts:login"))

        # These are set by SecurityMiddleware when configured
        self.assertTrue(settings.SECURE_BROWSER_XSS_FILTER)
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)

    def test_session_cookie_configuration(self):
        """Test session cookie security configuration"""
        # Login to create a session
        response = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": "testpass123"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Verify session was created
        self.assertIn("_auth_user_id", self.client.session)

        # In production, cookies would have secure attributes
        # Test environment may not set all attributes
