"""
Tests for the ExtensionTokenView (S8 – token issue/revoke UI).
"""

from django.test import Client, TestCase
from django.urls import reverse

from knox.models import AuthToken

from apps.core.tests.utils import create_test_user


class ExtensionTokenViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = create_test_user()
        self.url = reverse("accounts:extension_tokens")

    # --- GET ---

    def test_get_unauthenticated_redirects(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_get_authenticated_shows_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "accounts/extension_tokens.html")

    def test_get_lists_existing_tokens(self):
        AuthToken.objects.create(user=self.user)
        AuthToken.objects.create(user=self.user)
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context["tokens"]), 2)

    def test_get_does_not_list_other_users_tokens(self):
        other = create_test_user(username_prefix="other")
        AuthToken.objects.create(user=other)
        self.client.force_login(self.user)
        resp = self.client.get(self.url)
        self.assertEqual(len(resp.context["tokens"]), 0)

    # --- POST issue ---

    def test_issue_creates_token(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {"action": "issue", "name": "Laptop"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("token", data)
        self.assertTrue(data["token"])
        self.assertEqual(AuthToken.objects.filter(user=self.user).count(), 1)

    def test_issue_uses_default_name_when_blank(self):
        self.client.force_login(self.user)
        resp = self.client.post(self.url, {"action": "issue", "name": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.json())

    # --- POST revoke ---

    def test_revoke_deletes_token(self):
        self.client.force_login(self.user)
        instance, _ = AuthToken.objects.create(user=self.user)
        resp = self.client.post(
            self.url, {"action": "revoke", "token_pk": str(instance.pk)}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["revoked"])
        self.assertEqual(AuthToken.objects.filter(user=self.user).count(), 0)

    def test_cannot_revoke_other_users_token(self):
        other = create_test_user(username_prefix="other")
        instance, _ = AuthToken.objects.create(user=other)
        self.client.force_login(self.user)
        resp = self.client.post(
            self.url, {"action": "revoke", "token_pk": str(instance.pk)}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["revoked"])
        self.assertEqual(AuthToken.objects.filter(user=other).count(), 1)
