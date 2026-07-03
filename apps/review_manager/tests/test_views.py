"""
Tests for review_manager views.

Tests for view functionality, permissions, and response handling
for search session management views.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from ..models import SearchSession, SessionActivity
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SessionArchiveViewTests(TestCase):
    """Test cases for SessionArchiveView."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.other_user = create_test_user(username_prefix="otheruser")

    def test_archive_completed_session(self):
        """Test archiving a session from completed status."""
        # Create a completed session
        session = SearchSession.objects.create(
            title="Completed Session", owner=self.user, status="completed"
        )

        # Login
        self.client.login(username=self.user.username, password="testpass123")

        # Archive the session
        url = reverse(
            "review_manager:archive_session", kwargs={"session_id": session.id}
        )
        response = self.client.post(url)

        # Verify redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("review_manager:dashboard"))

        # Verify status changed to archived
        session.refresh_from_db()
        self.assertEqual(session.status, "archived")

        # Verify activity was logged
        activity = SessionActivity.objects.filter(
            session=session, activity_type="status_changed"
        ).latest("created_at")
        self.assertIn("archived", activity.description.lower())
        self.assertEqual(activity.metadata["new_status"], "archived")
        self.assertEqual(activity.metadata["old_status"], "completed")

    def test_archive_from_draft_allowed(self):
        """Test that archiving from draft is allowed (for administrative purposes)."""
        session = SearchSession.objects.create(
            title="Draft Session", owner=self.user, status="draft"
        )

        self.client.login(username=self.user.username, password="testpass123")
        url = reverse(
            "review_manager:archive_session", kwargs={"session_id": session.id}
        )
        response = self.client.post(url)

        # Should succeed
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, "archived")

    def test_archive_requires_authentication(self):
        """Test that archive view requires authentication."""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="completed"
        )

        url = reverse(
            "review_manager:archive_session", kwargs={"session_id": session.id}
        )
        response = self.client.post(url)

        # Should redirect (authentication required)
        self.assertEqual(response.status_code, 302)
        # The redirect URL should be to login page with next parameter or root
        # Different settings may configure different LOGIN_URLs
        self.assertTrue(
            response.url in ["/", "/accounts/login/"]
            or "/accounts/login/" in response.url
            or response.url.startswith("/accounts/login"),
            f"Expected redirect to login page or root, got {response.url}",
        )

    def test_archive_requires_ownership(self):
        """Test that only the owner can archive their session."""
        session = SearchSession.objects.create(
            title="Other User's Session", owner=self.other_user, status="completed"
        )

        # Login as different user
        self.client.login(username=self.user.username, password="testpass123")
        url = reverse(
            "review_manager:archive_session", kwargs={"session_id": session.id}
        )
        response = self.client.post(url)

        # UserOwnerMixin redirects to dashboard with error message (not 404)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("review_manager:dashboard"))

        # Verify status unchanged
        session.refresh_from_db()
        self.assertEqual(session.status, "completed")

    def test_archive_invalid_transition_error(self):
        """Test that invalid state transition shows error message."""
        # Archived sessions can only go to draft
        session = SearchSession.objects.create(
            title="Already Archived", owner=self.user, status="archived"
        )

        self.client.login(username=self.user.username, password="testpass123")
        url = reverse(
            "review_manager:archive_session", kwargs={"session_id": session.id}
        )
        response = self.client.post(url)

        # Should redirect back to session detail with error
        self.assertEqual(response.status_code, 302)

        # Verify status unchanged
        session.refresh_from_db()
        self.assertEqual(session.status, "archived")

    def test_archive_success_message(self):
        """Test that successful archive shows success message."""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="completed"
        )

        self.client.login(username=self.user.username, password="testpass123")
        url = reverse(
            "review_manager:archive_session", kwargs={"session_id": session.id}
        )
        response = self.client.post(url, follow=True)

        # Check for success message
        messages = list(response.context["messages"])
        self.assertTrue(any("archived successfully" in str(m) for m in messages))

    def test_archive_from_all_allowed_states(self):
        """Test that archiving is allowed from all non-archived states."""
        allowed_states = [
            "draft",
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
            "completed",
        ]

        for status in allowed_states:
            with self.subTest(status=status):
                session = SearchSession.objects.create(
                    title=f"Session in {status}", owner=self.user, status=status
                )

                self.client.login(username=self.user.username, password="testpass123")
                url = reverse(
                    "review_manager:archive_session", kwargs={"session_id": session.id}
                )
                response = self.client.post(url)

                # Should succeed
                self.assertEqual(response.status_code, 302)
                session.refresh_from_db()
                self.assertEqual(
                    session.status, "archived", f"Failed to archive from {status}"
                )

                # Clean up
                session.delete()
