from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SignUpViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse("accounts:signup")

    def test_signup_view_get(self):
        """Test GET request to signup view"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/signup.html")

    def test_signup_view_post_valid(self):
        """Test POST request with valid data"""
        response = self.client.post(
            self.url,
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "password1": "testpass123!",
                "password2": "testpass123!",
                "first_name": "John",
                "last_name": "Doe",
            },
        )
        self.assertEqual(response.status_code, 302)  # Redirect after success
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_signup_auto_login(self):
        """Test user is automatically logged in after signup"""
        response = self.client.post(
            self.url,
            {
                "username": "newuser",
                "email": "newuser@example.com",  # Add email field
                "password1": "testpass123!",
                "password2": "testpass123!",
            },
            follow=True,
        )
        # Check that the user is logged in by verifying they can access a protected page
        self.assertEqual(response.status_code, 200)
        # User should be logged in and redirected to create session page
        self.assertContains(response, "Create New Review Session")

    def test_signup_redirect_to_create_session(self):
        """Test redirect to create session after signup"""
        response = self.client.post(
            self.url,
            {
                "username": "newuser",
                "email": "newuser@example.com",  # Add email field
                "password1": "testpass123!",
                "password2": "testpass123!",
            },
        )
        self.assertRedirects(response, reverse("review_manager:create_session"))

    def test_signup_auto_login_uses_correct_backend(self):
        """Signup should auto-login without explicit backend specification.

        Validates that Django automatically selects ModelBackend for authentication
        when RoleBasedPermissionBackend returns None from authenticate().
        This test ensures Phase 5 refactoring is working correctly.
        """
        response = self.client.post(
            self.url,
            {
                "email": "new@example.com",
                "password1": "TestPass123!",
                "password2": "TestPass123!",
            },
        )

        # Should redirect to create session (successful login)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("review_manager:create_session"))

        # User should be authenticated (username auto-generated from email prefix)
        user = get_user_model().objects.get(email="new@example.com")
        from django.contrib.auth import get_user as get_authenticated_user

        # Get the authenticated user from the client session
        authenticated_user = get_authenticated_user(self.client)
        self.assertTrue(authenticated_user.is_authenticated)
        self.assertEqual(authenticated_user.email, "new@example.com")
        self.assertEqual(authenticated_user.id, user.id)


class ProfileViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_test_user()
        self.url = reverse("accounts:profile")

    def test_profile_view_requires_login(self):
        """Test profile view requires authentication"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_view_get(self):
        """Test GET request to profile view"""
        self.client.login(username=self.user.username, password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/profile.html")

    def test_profile_view_post_valid(self):
        """Test POST request with valid data"""
        self.client.login(username=self.user.username, password="testpass123")
        response = self.client.post(
            self.url,
            {
                "email": "newemail@example.com",
                "first_name": "Updated",
                "last_name": "Name",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "newemail@example.com")

    def test_profile_view_success_message(self):
        """Test success message after profile update"""
        self.client.login(username=self.user.username, password="testpass123")
        response = self.client.post(
            self.url,
            {
                "email": "newemail@example.com",
                "first_name": "Updated",
                "last_name": "Name",
            },
            follow=True,
        )
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Profile updated successfully!")


class AuthenticationViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_test_user()

    def test_login_view_get(self):
        """Test GET request to login view"""
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_login_with_email(self):
        """Test login with email"""
        response = self.client.post(
            reverse("accounts:login"),
            {"email": self.user.email, "password": "testpass123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("review_manager:dashboard"))

    def test_login_with_next_parameter(self):
        """Test login redirects to 'next' parameter when provided"""
        next_url = reverse("accounts:profile")
        response = self.client.post(
            f"{reverse('accounts:login')}?next={next_url}",
            {"email": self.user.email, "password": "testpass123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, next_url)

    def test_logout(self):
        """Test logout functionality"""
        self.client.login(username=self.user.username, password="testpass123")
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("accounts:login"))
