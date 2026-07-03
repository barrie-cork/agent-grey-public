from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.forms import CustomAuthenticationForm
from apps.organisation.middleware import OrganisationMiddleware
from apps.organisation.models import Organisation, OrganisationMembership
from apps.core.tests.utils import create_test_user

User = get_user_model()


class AuthenticationIntegrationTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_complete_signup_login_flow(self):
        """Test complete signup → login flow"""
        # 1. Sign up (email-only form, username auto-generated from email prefix)
        signup_url = reverse("accounts:signup")
        response = self.client.post(
            signup_url,
            {
                "email": "newuser@example.com",
                "password1": "testpass123!",
                "password2": "testpass123!",
            },
        )
        self.assertEqual(response.status_code, 302)

        # 2. Verify user is created and logged in
        self.assertTrue(User.objects.filter(email="newuser@example.com").exists())
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)  # No redirect, user is logged in

        # 3. Logout
        self.client.logout()

        # 4. Login with email
        login_url = reverse("accounts:login")
        response = self.client.post(
            login_url, {"email": "newuser@example.com", "password": "testpass123!"}
        )
        self.assertEqual(response.status_code, 302)

        # 5. Verify logged in
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

    def test_profile_update_after_login(self):
        """Test profile update after login"""
        # Create user
        user = create_test_user()

        # Login
        self.client.login(username=user.username, password="testpass123")

        # Update profile
        profile_url = reverse("accounts:profile")
        response = self.client.post(
            profile_url,
            {
                "email": "updated@example.com",
                "first_name": "Updated",
                "last_name": "User",
            },
        )
        self.assertEqual(response.status_code, 302)

        # Verify update
        user.refresh_from_db()
        self.assertEqual(user.email, "updated@example.com")
        self.assertEqual(user.first_name, "Updated")
        self.assertEqual(user.last_name, "User")

    def test_password_reset_email_flow(self):
        """Test password reset email flow"""
        # Create user
        user = create_test_user()
        # Clear emails sent by user creation signals (welcome + admin notification)
        mail.outbox.clear()

        # Request password reset
        reset_url = reverse("accounts:password_reset")
        response = self.client.post(reset_url, {"email": user.email})
        self.assertEqual(response.status_code, 302)

        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(user.email, mail.outbox[0].to)
        self.assertIn("password reset", mail.outbox[0].subject.lower())

        # Extract reset link from email
        email_body = mail.outbox[0].body
        self.assertIn("accounts/reset/", email_body)

    def test_redirect_chains(self):
        """Test redirect chains for protected views"""
        # Try to access profile without login
        profile_url = reverse("accounts:profile")
        response = self.client.get(profile_url)
        self.assertEqual(response.status_code, 302)
        # Should redirect to login with next parameter
        self.assertIn(reverse("accounts:login"), response.url)
        self.assertIn("next=", response.url)

        # Login and verify redirect back to profile
        user = create_test_user()
        response = self.client.post(
            reverse("accounts:login") + f"?next={profile_url}",
            {"email": user.email, "password": "testpass123"},
            follow=True,
        )
        # Should end up at profile page
        self.assertContains(response, "Edit Profile")

    def test_session_expiry_behavior(self):
        """Test session expiry settings"""
        # Create and login user
        user = create_test_user()
        self.client.login(username=user.username, password="testpass123")

        # Check session exists
        self.assertIn("_auth_user_id", self.client.session)

        # Session should have correct expiry (24 hours = 86400 seconds)
        self.assertEqual(self.client.session.get_expiry_age(), 86400)


class AuthenticationMiddlewareIntegrationTest(TestCase):
    """
    Test authentication with OrganisationMiddleware in request pipeline.

    Regression test for Issue #32: Ensures middleware doesn't interfere
    with authentication by querying OrganisationMembership during auth transaction.
    """

    def setUp(self):
        """Create test user with organisation membership."""
        self.factory = RequestFactory()

        # Create test user
        self.user = create_test_user()

        # Create organisation
        self.org = Organisation.objects.create(
            name="Test Organisation", slug="test-org"
        )

        # Create membership
        OrganisationMembership.objects.create(
            user=self.user, organisation=self.org, role="REVIEWER", is_active=True
        )

    def test_authentication_with_organisation_middleware_on_login_path(self):
        """
        Test middleware skips execution for /accounts/login/.

        This is the core regression test for Issue #32. The middleware should
        skip execution for /accounts/login/ to avoid querying the database
        during the authentication transaction.
        """
        # Create POST request to login path (like Playwright E2E test)
        request = self.factory.post(
            "/accounts/login/",
            {"email": self.user.email, "password": "testpass123"},
        )

        # Simulate AuthenticationMiddleware (sets anonymous user)
        request.user = AnonymousUser()

        # Run OrganisationMiddleware (should skip for /accounts/login/)
        middleware = OrganisationMiddleware(lambda r: None)
        middleware._setup_organisation(request)

        # Verify middleware skipped (request.organisation should be None)
        self.assertIsNone(request.organisation)

        # Validate authentication form (should succeed without middleware interference)
        form = CustomAuthenticationForm(
            request=request,
            data={"email": self.user.email, "password": "testpass123"},
        )

        # CRITICAL: Form should be valid even with middleware in request pipeline
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        assert form.user_cache is not None
        self.assertEqual(form.user_cache.username, self.user.username)

    def test_organisation_context_loads_after_login(self):
        """
        Test middleware sets organisation context for non-auth paths.

        Verifies the middleware still works normally for dashboard and other
        views after successful login (no regression in core functionality).
        """
        # Create GET request to dashboard (NOT in SKIP_PATHS)
        request = self.factory.get("/")

        # Simulate authenticated user
        request.user = self.user

        # Run OrganisationMiddleware (should execute normally)
        middleware = OrganisationMiddleware(lambda r: None)
        middleware._setup_organisation(request)

        # Verify organisation context is set
        self.assertIsNotNone(request.organisation)
        self.assertEqual(request.organisation.slug, "test-org")
        self.assertEqual(request.organisation_membership.role, "REVIEWER")

    def test_middleware_skip_paths_coverage(self):
        """
        Test all authentication paths are correctly skipped.

        Ensures SKIP_PATHS constant includes all relevant auth views.
        """
        auth_paths = [
            "/accounts/login/",
            "/accounts/logout/",
            "/accounts/signup/",
            "/accounts/password-reset/",
        ]

        middleware = OrganisationMiddleware(lambda r: None)

        for path in auth_paths:
            request = self.factory.post(path)
            request.user = AnonymousUser()

            middleware._setup_organisation(request)

            # Verify middleware skipped (no database query)
            self.assertIsNone(
                request.organisation,
                f"Middleware should skip {path} but request.organisation is set",
            )
