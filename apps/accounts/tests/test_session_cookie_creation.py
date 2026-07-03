"""
Test session/CSRF cookie creation for login view (Issue #33).

This test verifies that the LoginView creates a CSRF token cookie on GET request,
which is required for CSRF validation on subsequent POST requests.
The @ensure_csrf_cookie decorator ensures this behaviour.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SessionCookieCreationTest(TestCase):
    """
    Test CSRF cookie creation for login page (Issue #33).

    Regression test to ensure E2E authentication works correctly by
    verifying that CSRF cookies are created before form submission.
    """

    def setUp(self):
        """Create test user for authentication tests."""
        self.client = Client()
        self.user = create_test_user()
        self.login_url = reverse("accounts:login")

    def test_get_login_page_creates_csrf_cookie(self):
        """
        Test that GET /accounts/login/ creates a csrftoken cookie.

        The @ensure_csrf_cookie decorator on LoginView forces CSRF cookie
        creation on GET, which is needed for subsequent POST CSRF validation.

        See: GitHub Issue #33 - E2E authentication failures
        """
        # GET login page (simulates browser loading login form)
        response = self.client.get(self.login_url)

        # Verify HTTP 200 response
        self.assertEqual(response.status_code, 200)

        # CRITICAL: CSRF cookie must be present (set by @ensure_csrf_cookie)
        self.assertIn(
            "csrftoken",
            response.cookies,
            "CSRF token cookie missing on GET /accounts/login/",
        )

        # Verify CSRF cookie has a value
        csrf_cookie = response.cookies["csrftoken"]
        self.assertIsNotNone(csrf_cookie.value, "CSRF cookie value is None")
        self.assertGreater(len(csrf_cookie.value), 0, "CSRF cookie value is empty")

    def test_login_post_succeeds_after_get(self):
        """
        Test that POST /accounts/login/ succeeds after GET.

        This simulates the E2E test flow where:
        1. GET /accounts/login/ creates CSRF cookie
        2. POST /accounts/login/ uses CSRF token for validation
        3. Authentication succeeds and redirects to dashboard
        """
        # Step 1: GET login page (creates CSRF cookie)
        response = self.client.get(self.login_url)
        self.assertIn("csrftoken", response.cookies)

        # Step 2: POST credentials (using same session)
        response = self.client.post(
            self.login_url, {"email": self.user.email, "password": "testpass123"}
        )

        # Verify successful login (HTTP 302 redirect)
        self.assertEqual(
            response.status_code,
            302,
            f"Login failed - got {response.status_code} instead of 302 redirect",
        )

    def test_ensure_csrf_cookie_decorator_active(self):
        """
        Test that @ensure_csrf_cookie decorator is active on LoginView.

        Verifies the fix is working by checking that the decorator
        forces CSRF cookie creation on first GET request.
        """
        # Clear all cookies and session
        self.client = Client()  # Fresh client with no session

        # First GET request should create CSRF cookie immediately
        response = self.client.get(self.login_url)

        # Verify CSRF cookie in response (set by @ensure_csrf_cookie)
        self.assertIn(
            "csrftoken",
            response.cookies,
            "CSRF cookie not set in response - @ensure_csrf_cookie may not be active",
        )
