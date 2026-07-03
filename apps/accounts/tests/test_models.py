from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from apps.core.tests.utils import create_test_superuser, create_test_user

User = get_user_model()


class UserModelTest(TestCase):
    def test_create_user_with_uuid(self):
        """Test creating a user generates a UUID primary key"""
        user = create_test_user()
        self.assertIsNotNone(user.id)
        self.assertEqual(len(str(user.id)), 36)  # UUID length with hyphens

    def test_create_user_with_email(self):
        """Test creating a user with email"""
        user = create_test_user()
        self.assertIn("@", user.email)

    def test_email_unique_constraint(self):
        """Test email uniqueness is enforced"""
        user1 = create_test_user()
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                username="unique_user_2", email=user1.email, password="pass123"
            )

    def test_email_is_required(self):
        """Test email field has blank=False (required)"""
        field = User._meta.get_field("email")
        self.assertFalse(field.blank)

    def test_timestamps_auto_populated(self):
        """Test created_at and updated_at are auto-populated"""
        user = create_test_user()
        self.assertIsNotNone(user.created_at)
        self.assertIsNotNone(user.updated_at)

    def test_db_table_name(self):
        """Test the database table name follows Django default convention"""
        user = create_test_user()
        self.assertEqual(user._meta.db_table, "accounts_user")

    def test_date_joined_auto_set(self):
        """Test date_joined is automatically set by AbstractUser"""
        user = create_test_user()
        self.assertIsNotNone(user.date_joined)

    def test_user_string_representation(self):
        """Test the string representation of User"""
        user = create_test_user()
        self.assertEqual(str(user), user.username)

    def test_create_superuser(self):
        """Test creating a superuser"""
        admin = create_test_superuser()
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_active)
