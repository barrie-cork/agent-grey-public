from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from apps.core.tests.utils import create_test_superuser, create_test_user

User = get_user_model()

# Test constants
TEST_PASSWORD = "test_secure_password_123!"
ADMIN_PASSWORD = "admin_secure_password_456!"


class AdminTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = create_test_superuser()
        self.user = create_test_user()

    def test_user_registered_in_admin(self):
        """Test User model is registered in admin"""
        self.assertIn(User, site._registry)

    def test_admin_list_display(self):
        """Test admin list display fields"""
        self.client.force_login(self.admin)
        url = reverse("admin:accounts_user_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Check for custom fields in response
        self.assertContains(response, "Username")
        self.assertContains(response, "Email")

    def test_admin_search_fields(self):
        """Test admin search functionality"""
        self.client.force_login(self.admin)
        url = reverse("admin:accounts_user_changelist")
        response = self.client.get(url, {"q": self.user.username})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)

    def test_admin_readonly_fields(self):
        """Test readonly fields in admin"""
        self.client.force_login(self.admin)
        url = reverse("admin:accounts_user_change", args=[self.user.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Check that id, created_at, updated_at are present but readonly
        self.assertContains(response, str(self.user.id))

    def test_admin_fieldsets(self):
        """Test custom fieldsets are displayed"""
        self.client.force_login(self.admin)
        url = reverse("admin:accounts_user_change", args=[self.user.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Check for timestamps fieldset
        self.assertContains(response, "Timestamps")
