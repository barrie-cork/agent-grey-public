"""Tests for organisation creation from profile page."""

from django.test import Client, TestCase
from django.urls import reverse

from apps.core.tests.utils import create_test_user
from apps.organisation.models import Organisation, OrganisationMembership


class CreateOrganisationFormTest(TestCase):
    """Test CreateOrganisationForm validation."""

    def setUp(self):
        self.user = create_test_user(username_prefix="orgcreator")
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("organisation:create")

    def test_create_organisation_success(self):
        """Valid name creates org with IS membership."""
        response = self.client.post(self.url, {"name": "Edinburgh Library"})
        self.assertRedirects(response, reverse("accounts:profile"))

        org = Organisation.objects.get(name="Edinburgh Library")
        self.assertEqual(org.slug, "edinburgh-library")

        membership = OrganisationMembership.objects.get(
            user=self.user, organisation=org
        )
        self.assertEqual(membership.role, "INFORMATION_SPECIALIST")
        self.assertTrue(membership.is_active)

    def test_name_too_short_rejected(self):
        """Name under 2 characters is rejected."""
        response = self.client.post(self.url, {"name": "X"})
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "name",
            "Organisation name must be at least 2 characters.",
        )

    def test_empty_name_rejected(self):
        """Empty name is rejected."""
        response = self.client.post(self.url, {"name": ""})
        self.assertEqual(response.status_code, 200)

    def test_slug_uniqueness(self):
        """Duplicate names get unique slugs."""
        Organisation.objects.create(name="Test Org", slug="test-org")

        response = self.client.post(self.url, {"name": "Test Org"})
        self.assertRedirects(response, reverse("accounts:profile"))

        orgs = Organisation.objects.filter(name="Test Org")
        self.assertEqual(orgs.count(), 2)
        slugs = set(orgs.values_list("slug", flat=True))
        self.assertEqual(len(slugs), 2)
        self.assertIn("test-org", slugs)
        self.assertIn("test-org-1", slugs)

    def test_multiple_orgs_per_user(self):
        """User can create multiple organisations beyond their personal org."""
        initial_count = OrganisationMembership.objects.filter(user=self.user).count()
        self.client.post(self.url, {"name": "First Org"})
        self.client.post(self.url, {"name": "Second Org"})

        memberships = OrganisationMembership.objects.filter(user=self.user)
        self.assertEqual(memberships.count(), initial_count + 2)

    def test_login_required(self):
        """Anonymous users are redirected to login."""
        self.client.logout()
        response = self.client.post(self.url, {"name": "Sneaky Org"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_get_renders_form(self):
        """GET request renders the creation form."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Organisation")


class ProfileOrganisationsTest(TestCase):
    """Test organisations section on profile page."""

    def setUp(self):
        self.user = create_test_user(username_prefix="profuser")
        self.client = Client()
        self.client.force_login(self.user)

    def test_profile_shows_memberships(self):
        """Profile page lists user's organisation memberships."""
        org = Organisation.objects.create(name="Visible Org", slug="visible-org")
        OrganisationMembership.objects.create(
            user=self.user,
            organisation=org,
            role="INFORMATION_SPECIALIST",
            is_active=True,
        )

        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, "Visible Org")
        self.assertContains(response, "Create Organisation")

    def test_profile_hides_inactive_memberships(self):
        """Inactive memberships are not shown on profile."""
        org = Organisation.objects.create(name="Hidden Org", slug="hidden-org")
        OrganisationMembership.objects.create(
            user=self.user,
            organisation=org,
            role="REVIEWER",
            is_active=False,
        )

        response = self.client.get(reverse("accounts:profile"))
        self.assertNotContains(response, "Hidden Org")

    def test_profile_shows_create_button(self):
        """Profile page always shows 'Create Organisation' button."""
        response = self.client.get(reverse("accounts:profile"))
        self.assertContains(response, 'data-testid="btn-create-org"')
