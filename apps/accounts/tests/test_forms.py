from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.forms import CustomAuthenticationForm, ProfileForm, SignUpForm
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SignUpFormTest(TestCase):
    """Tests for simplified email-only SignUpForm."""

    def test_signup_form_only_has_email_and_password_fields(self):
        """Test that SignUpForm only requires email and password fields."""
        form = SignUpForm()
        required_fields = {"email", "password1", "password2"}
        # These fields should NOT be in the form
        forbidden_fields = {"username", "first_name", "last_name"}

        self.assertEqual(set(form.fields.keys()), required_fields)
        for field in forbidden_fields:
            self.assertNotIn(field, form.fields)

    def test_signup_form_valid_with_email_only(self):
        """Test signup form with email and password only."""
        form = SignUpForm(
            data={
                "email": "newuser@example.com",
                "password1": "testpass123!",
                "password2": "testpass123!",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_signup_form_auto_generates_username(self):
        """Test that username is auto-generated from email prefix."""
        form = SignUpForm(
            data={
                "email": "johndoe@example.com",
                "password1": "testpass123!",
                "password2": "testpass123!",
            }
        )
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.username, "johndoe")
        self.assertEqual(user.email, "johndoe@example.com")

    def test_signup_form_handles_duplicate_username_collision(self):
        """Test username collision handling with counter suffix."""
        # Create existing user with exact username 'collisiontest'
        User.objects.create_user(
            username="collisiontest",
            email="collisiontest_orig@example.com",
            password="testpass123",
        )

        # New user with email 'collisiontest@newdomain.com' should get 'collisiontest1'
        form = SignUpForm(
            data={
                "email": "collisiontest@newdomain.com",
                "password1": "testpass123!",
                "password2": "testpass123!",
            }
        )
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.username, "collisiontest1")

    def test_signup_form_truncates_long_email_prefix(self):
        """Test that very long email prefixes are truncated."""
        long_email = "a" * 50 + "@example.com"
        form = SignUpForm(
            data={
                "email": long_email,
                "password1": "testpass123!",
                "password2": "testpass123!",
            }
        )
        self.assertTrue(form.is_valid())
        user = form.save()
        # Username should be max 30 chars
        self.assertLessEqual(len(user.username), 30)

    def test_signup_form_duplicate_email(self):
        """Test signup form with duplicate email."""
        existing_user = create_test_user(username_prefix="existinguser")
        form = SignUpForm(
            data={
                "email": existing_user.email,
                "password1": "testpass123!",
                "password2": "testpass123!",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_signup_form_password_mismatch(self):
        """Test signup form with mismatched passwords."""
        form = SignUpForm(
            data={
                "email": "newuser@example.com",
                "password1": "testpass123!",
                "password2": "different123!",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_signup_form_widgets(self):
        """Test form widgets have correct CSS classes."""
        form = SignUpForm()
        self.assertIn("form-control", form.fields["email"].widget.attrs["class"])


class ProfileFormTest(TestCase):
    def setUp(self):
        self.user = create_test_user()

    def test_profile_form_valid_data(self):
        """Test profile form with valid data"""
        form = ProfileForm(
            instance=self.user,
            data={
                "email": "newemail@example.com",
                "first_name": "Updated",
                "last_name": "Name",
            },
        )
        self.assertTrue(form.is_valid())

    def test_profile_form_no_password_field(self):
        """Test profile form doesn't have password field"""
        form = ProfileForm(instance=self.user)
        self.assertNotIn("password", form.fields)

    def test_profile_form_duplicate_email(self):
        """Test profile form with duplicate email from another user"""
        other_user = create_test_user(username_prefix="otheruser")
        form = ProfileForm(
            instance=self.user,
            data={
                "email": other_user.email,
                "first_name": "Test",
                "last_name": "User",
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_profile_form_same_email(self):
        """Test profile form with user's own email (should be valid)"""
        form = ProfileForm(
            instance=self.user,
            data={
                "email": self.user.email,
                "first_name": "Test",
                "last_name": "User",
            },
        )
        self.assertTrue(form.is_valid())


class CustomAuthenticationFormTest(TestCase):
    """Tests for email-only CustomAuthenticationForm."""

    def setUp(self):
        self.user = create_test_user()

    def test_login_form_has_email_field(self):
        """Test that login form uses 'email' field, not 'username'."""
        form = CustomAuthenticationForm()
        self.assertIn("email", form.fields)
        self.assertNotIn("username", form.fields)
        self.assertEqual(form.fields["email"].label, "Email")

    def test_login_with_email(self):
        """Test login with email."""
        form = CustomAuthenticationForm(
            data={"email": self.user.email, "password": "testpass123"}
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        form = CustomAuthenticationForm(
            data={"email": self.user.email, "password": "wrongpassword"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)
