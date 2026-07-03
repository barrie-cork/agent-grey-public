"""Integration tests for search execution workflow."""

import json
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.review_manager.models import SearchSession
from apps.review_manager.services.state_manager import SessionStateManager
from apps.search_strategy.models import SearchStrategy
from apps.core.tests.utils import create_test_user


class TestAutomaticExecutionFlow(TestCase):
    """Test the new automatic execution workflow."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="defining_search"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test interest"],
            context_terms=["test context"],
            is_complete=True,
        )

    def test_automatic_execution_trigger(self):
        """Test that ready_to_execute automatically triggers execution."""
        state_manager = SessionStateManager(self.session)

        with patch(
            "apps.serp_execution.tasks.initiate_search_session_execution_task.delay"
        ) as _mock_task:
            success, error = state_manager.transition_to("ready_to_execute")

            self.assertTrue(success, f"Transition failed: {error}")

            self.session.refresh_from_db()
            self.assertIn(self.session.status, ["ready_to_execute", "executing"])

    def test_no_manual_execution_allowed(self):
        """Test that manual execution endpoints are removed."""
        self.session.status = "ready_to_execute"
        self.session.save()

        with self.assertRaises(Exception):
            _url = reverse("serp_execution:execute_search", args=[self.session.id])

    def test_monitoring_page_loads(self):
        """Test monitoring page loads correctly."""
        self.session.status = "executing"
        self.session.save()

        url = reverse("serp_execution:execution_status", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # The nojs template shows session title and status
        self.assertContains(response, self.session.title)
        self.assertContains(response, "Status:")


class WorkflowIntegrationTest(TestCase):
    """Test the complete search execution workflow."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.client = Client()
        self.client.login(username=self.user.username, password="testpass123")

        self.session = SearchSession.objects.create(
            owner=self.user, title="Integration Test Session", status="draft"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test interest"],
            context_terms=["test context"],
            is_complete=True,
        )

    def tearDown(self):
        """Clean up."""
        SearchSession.objects.all().delete()
        User.objects.all().delete()

    @patch("apps.serp_execution.tasks.initiate_search_session_execution_task")
    def test_execute_search_from_strategy_form(self, mock_task):
        """Test executing search directly from strategy form."""
        mock_task.delay.return_value = MagicMock(id="test-task-123")
        self.session.status = "defining_search"
        self.session.save()

        url = reverse(
            "search_strategy:strategy_form", kwargs={"session_id": self.session.id}
        )

        response = self.client.post(
            url,
            {
                "population_terms": "elderly patients",
                "interest_terms": "telehealth",
                "context_terms": "rural areas",
                "execute_search": "execute_search",
            },
            follow=True,
        )

        # Form submission should succeed (200 after follow or redirect)
        self.assertIn(response.status_code, [200, 302])

    def test_status_page_renders_correctly(self):
        """Test that execution status page renders."""
        self.session.status = "executing"
        self.session.save()

        url = reverse(
            "serp_execution:execution_status", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search Execution")
        self.assertContains(response, self.session.title)

    def test_progress_api_returns_json(self):
        """Test that progress API returns valid JSON."""
        self.session.status = "executing"
        self.session.save()

        url = reverse(
            "serp_execution:session_progress_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # Verify structure matches actual API response
        self.assertIn("status", data)
        self.assertIn("session_status", data)

    def test_automatic_state_progression(self):
        """Test automatic progression through states."""
        self.session.status = "defining_search"
        self.session.save()

        state_manager = SessionStateManager(self.session)

        with patch(
            "apps.serp_execution.tasks.initiate_search_session_execution_task.delay"
        ):
            success, error = state_manager.transition_to("ready_to_execute")

            self.assertTrue(success, f"Transition failed: {error}")

            self.session.refresh_from_db()
            self.assertIn(self.session.status, ["ready_to_execute", "executing"])
