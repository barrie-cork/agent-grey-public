"""Tests for search strategy views, including return to search strategy functionality."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.search_strategy.models import SearchStrategy
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SearchStrategyViewTest(TestCase):
    """Test the SearchStrategyView including return to search strategy feature."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        # Create a session in draft status
        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test description",
            owner=self.user,
            status="draft",
        )
        config = ReviewConfiguration.objects.create(
            session=self.session, created_by=self.user
        )
        self.session.current_configuration = config
        self.session.save()

    def test_can_access_strategy_form_from_draft(self):
        """Test accessing strategy form from draft status."""
        url = reverse(
            "search_strategy:strategy_form", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search Strategy")
        self.assertContains(response, "Population")
        self.assertContains(response, "Interest")
        self.assertContains(response, "Context")

    def test_can_access_strategy_from_ready_to_execute(self):
        """Test that strategy form is accessible from ready_to_execute status.

        ready_to_execute is not in the blocked_states or returnable_states lists,
        so the view renders the form without any status transition. This allows
        the user to review/edit their strategy before execution starts.
        """
        # Move session to ready_to_execute
        self.session.status = "ready_to_execute"
        self.session.save()

        # Create a strategy with some data
        SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly", "seniors"],
            interest_terms=["telehealth", "remote care"],
            context_terms=["rural", "remote areas"],
            search_config={
                "domains": ["nice.org.uk"],
                "include_general_search": True,
                "file_types": ["pdf"],
                "search_type": "google",
            },
        )

        # Access strategy form -- should render (200) without redirecting
        url = reverse(
            "search_strategy:strategy_form", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Session stays at ready_to_execute (no transition needed)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_to_execute")

    def test_can_return_to_strategy_from_under_review(self):
        """Test that the view allows returning to strategy editing from under_review.

        The view treats under_review as a returnable state -- the session
        transitions back to defining_search and the strategy form is rendered.
        """
        # Move session to under_review
        self.session.status = "under_review"
        self.session.save()

        # Access strategy form -- should render (200) after transitioning back
        url = reverse(
            "search_strategy:strategy_form", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Session should have transitioned back to defining_search
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "defining_search")

    def test_cannot_return_to_strategy_from_completed(self):
        """Test that completed sessions cannot return to strategy editing."""
        # Move session to completed
        self.session.status = "completed"
        self.session.save()

        # Try to access strategy form
        url = reverse(
            "search_strategy:strategy_form", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        # Should redirect with error
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse(
                "review_manager:session_detail", kwargs={"session_id": self.session.id}
            ),
        )

        # Check session status unchanged
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")

    def test_cannot_return_to_strategy_from_archived(self):
        """Test that archived sessions cannot return to strategy editing."""
        # Move session to archived
        self.session.status = "archived"
        self.session.save()

        # Try to access strategy form
        url = reverse(
            "search_strategy:strategy_form", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        # Should redirect with error
        self.assertEqual(response.status_code, 302)

        # Check session status unchanged
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "archived")

    def test_return_button_visibility_per_state(self):
        """Test that the return to search strategy button appears only in returnable states.

        The template shows the button for: executing, processing_results, ready_for_review.
        It is hidden for all other states.
        """
        states_with_button = {"executing", "processing_results", "ready_for_review"}
        all_states = [
            "draft",
            "defining_search",
            "ready_to_execute",
            "executing",
            "processing_results",
            "ready_for_review",
            "under_review",
            "completed",
            "archived",
        ]

        for status in all_states:
            self.session.status = status
            self.session.save()

            url = reverse(
                "review_manager:session_detail", kwargs={"session_id": self.session.id}
            )
            response = self.client.get(url)

            if status in states_with_button:
                self.assertContains(
                    response,
                    "Return to Search Strategy",
                    msg_prefix=f"Button SHOULD appear in {status} status",
                )
            else:
                self.assertNotContains(
                    response,
                    "Return to Search Strategy",
                    msg_prefix=f"Button should NOT appear in {status} status",
                )

    def test_return_button_hidden_in_blocked_states(self):
        """Test that the return button is hidden in completed/archived states."""
        # Test states where button should NOT appear
        states_without_button = ["completed", "archived"]

        for status in states_without_button:
            self.session.status = status
            self.session.save()

            url = reverse(
                "review_manager:session_detail", kwargs={"session_id": self.session.id}
            )
            response = self.client.get(url)

            self.assertNotContains(
                response,
                "Return to Search Strategy",
                msg_prefix=f"Button should NOT appear in {status} status",
            )
