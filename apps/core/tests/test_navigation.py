from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.template import Context, Template
from django.test import RequestFactory, TestCase, override_settings

from apps.core.templatetags.navigation_tags import (
    should_show_header,
    user_can_access_dashboard,
)
from apps.core.tests.utils import create_test_superuser, create_test_user

# Auth page detection helper (logic extracted from should_show_header)
AUTH_PAGE_NAMES = {
    "login",
    "signup",
    "password_reset",
    "password_reset_done",
    "password_reset_confirm",
    "password_reset_complete",
}


def is_auth_page(context) -> bool:
    """Check if the current page is an authentication page."""
    request = context.get("request")
    if request and hasattr(request, "resolver_match") and request.resolver_match:
        return request.resolver_match.url_name in AUTH_PAGE_NAMES
    return False


User = get_user_model()


class NavigationVisibilityTests(TestCase):
    """Tests for navigation visibility logic."""

    def setUp(self):
        self.factory = RequestFactory()
        self.regular_user = create_test_user(username_prefix="regular")
        self.staff_user = create_test_user(username_prefix="staff", is_staff=True)
        self.admin_user = create_test_superuser()

        # Create admin group
        self.admin_group = Group.objects.create(name="Administrators")

    def test_header_hidden_on_login_page(self):
        """Header should be hidden on login page for all users."""
        request = self.factory.get("/accounts/login/")
        request.resolver_match = type("obj", (object,), {"url_name": "login"})()

        # Test with anonymous user
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()
        context = Context({"request": request, "user": request.user})

        self.assertFalse(should_show_header(context))
        self.assertTrue(is_auth_page(context))

    def test_header_hidden_on_signup_page(self):
        """Header should be hidden on signup page."""
        request = self.factory.get("/accounts/signup/")
        request.resolver_match = type("obj", (object,), {"url_name": "signup"})()
        request.user = self.regular_user
        context = Context({"request": request, "user": request.user})

        self.assertFalse(should_show_header(context))
        self.assertTrue(is_auth_page(context))

    def test_header_hidden_on_password_reset_pages(self):
        """Header should be hidden on all password reset pages."""
        password_reset_pages = [
            "password_reset",
            "password_reset_done",
            "password_reset_confirm",
            "password_reset_complete",
        ]

        for page_name in password_reset_pages:
            with self.subTest(page=page_name):
                request = self.factory.get(f"/accounts/{page_name}/")
                request.resolver_match = type(
                    "obj", (object,), {"url_name": page_name}
                )()
                request.user = self.regular_user
                context = Context({"request": request, "user": request.user})

                self.assertFalse(should_show_header(context))
                self.assertTrue(is_auth_page(context))

    def test_header_visible_for_regular_user_on_non_auth_page(self):
        """Header should be visible for regular users on non-auth pages."""
        request = self.factory.get("/dashboard/")
        request.resolver_match = type("obj", (object,), {"url_name": "dashboard"})()
        request.user = self.regular_user
        context = Context({"request": request, "user": request.user})

        self.assertTrue(should_show_header(context))
        self.assertFalse(is_auth_page(context))

    def test_header_hidden_for_staff_user(self):
        """Header should be hidden for staff users by default."""
        request = self.factory.get("/dashboard/")
        request.resolver_match = type("obj", (object,), {"url_name": "dashboard"})()
        request.user = self.staff_user
        context = Context({"request": request, "user": request.user})

        self.assertFalse(should_show_header(context))

    @override_settings(NAVIGATION_CONFIG={"SHOW_HEADER_FOR_STAFF": True})
    def test_header_visible_for_staff_when_configured(self):
        """Header should be visible for staff users when configured."""
        request = self.factory.get("/dashboard/")
        request.resolver_match = type("obj", (object,), {"url_name": "dashboard"})()
        request.user = self.staff_user
        context = Context({"request": request, "user": request.user})

        self.assertTrue(should_show_header(context))

    def test_header_visible_for_superuser_staff(self):
        """Header should always be visible for superusers, even if they're staff."""
        request = self.factory.get("/dashboard/")
        request.resolver_match = type("obj", (object,), {"url_name": "dashboard"})()
        request.user = self.admin_user
        context = Context({"request": request, "user": request.user})

        self.assertTrue(should_show_header(context))

    def test_dashboard_link_superuser_only(self):
        """Dashboard link should only be visible to superusers."""
        # Regular user should not have dashboard access
        self.assertFalse(user_can_access_dashboard(self.regular_user))

        # Staff user should not have dashboard access
        self.assertFalse(user_can_access_dashboard(self.staff_user))

        # Superuser should have dashboard access
        self.assertTrue(user_can_access_dashboard(self.admin_user))

    def test_dashboard_link_admin_group_user(self):
        """Users in admin groups should have dashboard access."""
        # Add regular user to admin group
        self.regular_user.groups.add(self.admin_group)

        self.assertTrue(user_can_access_dashboard(self.regular_user))

    def test_dashboard_link_anonymous_user(self):
        """Anonymous users should not have dashboard access."""
        self.assertFalse(user_can_access_dashboard(None))

    def test_template_rendering_with_navigation_tags(self):
        """Test that navigation template tags work in actual templates."""
        template_code = """
        {% load navigation_tags %}
        {% should_show_header as show_header %}
        {% user_can_access_dashboard user as can_access_dashboard %}
        show_header:{{ show_header }}
        can_access_dashboard:{{ can_access_dashboard }}
        """

        # Test with regular user on non-auth page
        request = self.factory.get("/dashboard/")
        request.resolver_match = type("obj", (object,), {"url_name": "dashboard"})()
        request.user = self.regular_user

        template = Template(template_code)
        context = Context({"request": request, "user": request.user})
        rendered = template.render(context)

        self.assertIn("show_header:True", rendered.replace(" ", "").replace("\n", ""))
        self.assertIn(
            "can_access_dashboard:False", rendered.replace(" ", "").replace("\n", "")
        )

    def test_no_resolver_match(self):
        """Test behavior when request has no resolver_match."""
        request = self.factory.get("/unknown/")
        request.user = self.regular_user
        context = Context({"request": request, "user": request.user})

        # Should show header by default when no resolver match
        self.assertTrue(should_show_header(context))
        self.assertFalse(is_auth_page(context))


class HeaderVisibilityIntegrationTests(TestCase):
    """Integration tests for header visibility in actual templates."""

    def setUp(self):
        from apps.organisation.models import Organisation, OrganisationMembership

        self.regular_user = create_test_user(username_prefix="regular")
        self.admin_user = create_test_superuser()

        # Create organisation context (required by middleware/views)
        org = Organisation.objects.create(name="Test Org", slug="test-org")
        OrganisationMembership.objects.create(
            organisation=org, user=self.regular_user, role="INFORMATION_SPECIALIST"
        )
        OrganisationMembership.objects.create(
            organisation=org, user=self.admin_user, role="INFORMATION_SPECIALIST"
        )

    def test_login_page_has_no_header(self):
        """Integration test: login page should have no navigation header."""
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)

        # Check that nav element is not in the response
        self.assertNotIn("nav-logo", response.content.decode())

    def test_signup_page_has_no_header(self):
        """Integration test: signup page should have no navigation header."""
        response = self.client.get("/accounts/signup/")
        self.assertEqual(response.status_code, 200)

        # Check that nav element is not in the response
        self.assertNotIn("nav-logo", response.content.decode())

    def test_regular_user_dashboard_has_header_without_admin_link(self):
        """Integration test: regular user should see header without admin dashboard link."""
        self.client.login(username=self.regular_user.username, password="testpass123")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        # Check that nav element is present
        self.assertIn("<nav", content)

        # Check that admin dashboard link is not present
        self.assertNotIn("Admin Dashboard", content)

        # Check that My Reviews link is present
        self.assertIn("My Reviews", content)

    def test_superuser_dashboard_has_admin_link(self):
        """Integration test: superuser should see admin dashboard link."""
        self.client.login(username=self.admin_user.username, password="testpass123")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        # Check that nav element is present
        self.assertIn("<nav", content)

        # Check that admin link is present (sidebar uses "Admin" label)
        self.assertIn("nav-admin", content)

        # Check that My Reviews link is also present
        self.assertIn("My Reviews", content)
