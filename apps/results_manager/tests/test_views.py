"""
Tests for results_manager views, specifically zero results handling.
"""

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchStrategy
from apps.search_strategy.models import SearchQuery
from apps.serp_execution.models import SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ProcessingStatusViewTestCase(TestCase):
    """Test cases for ProcessingStatusView."""

    def setUp(self) -> None:
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user(username_prefix="test@example.com")
        self.client.login(username=self.user.username, password="testpass123")

    def test_zero_results_renders_special_template(self) -> None:
        """Test that zero results sessions render the no_results_found template."""
        # Create a completed session with zero results
        session = SearchSession.objects.create(
            title="Zero Results Test",
            owner=self.user,
            status="completed",
            total_results=0,
        )

        # Create search strategy and execution for context
        strategy = SearchStrategy.objects.create(
            session=session,
            user=self.user,
        )
        query = SearchQuery.objects.create(
            strategy=strategy,
            session=session,
            query_text="rare medical condition XYZ123",
            is_active=True,
        )
        SearchExecution.objects.create(query=query, status="completed", results_count=0)

        url = reverse(
            "results_manager:processing_status", kwargs={"session_id": session.id}
        )
        response = self.client.get(url)

        # Should render the no_results_found template
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "results_manager/no_results_found.html")
        self.assertIn("session", response.context)
        self.assertIn("search_executions", response.context)
        self.assertEqual(response.context["session"], session)

    def test_no_results_page_shows_create_new_search_button(self) -> None:
        """Test that no results page shows 'Create New Search' instead of 'Modify Search Strategy'."""
        # Create a completed session with zero results
        session = SearchSession.objects.create(
            title="No Results Session",
            owner=self.user,
            status="completed",
            total_results=0,
        )

        # Create minimal search data
        strategy = SearchStrategy.objects.create(
            session=session,
            user=self.user,
        )
        query = SearchQuery.objects.create(
            strategy=strategy, session=session, query_text="test query", is_active=True
        )
        SearchExecution.objects.create(query=query, status="completed", results_count=0)

        url = reverse(
            "results_manager:processing_status", kwargs={"session_id": session.id}
        )
        response = self.client.get(url)

        # Check for correct button text and link
        self.assertContains(response, "Create New Search")
        self.assertContains(response, reverse("review_manager:create_session"))
        self.assertNotContains(response, "Modify Search Strategy")

        # Check for data integrity message
        self.assertContains(
            response,
            "To modify your search strategy, please create a new search session",
        )
        self.assertContains(
            response, "Completed sessions cannot be edited to maintain data integrity"
        )

    def test_normal_processing_renders_standard_template(self) -> None:
        """Test that normal processing sessions render the standard template."""
        # Create a session that's still processing
        session = SearchSession.objects.create(
            title="Normal Processing Test",
            owner=self.user,
            status="processing_results",
            total_results=50,
        )

        url = reverse(
            "results_manager:processing_status", kwargs={"session_id": session.id}
        )
        response = self.client.get(url)

        # Should render the standard processing status template
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "results_manager/processing_status.html")

    def test_completed_with_results_renders_standard_template(self) -> None:
        """Test that completed sessions with results render the standard template."""
        # Create a completed session with results
        session = SearchSession.objects.create(
            title="Completed With Results Test",
            owner=self.user,
            status="completed",
            total_results=25,
        )

        url = reverse(
            "results_manager:processing_status", kwargs={"session_id": session.id}
        )
        response = self.client.get(url)

        # Should render the standard template (not the no results template)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "results_manager/processing_status.html")

    def test_unauthorized_access_denied(self) -> None:
        """Test that unauthorized users cannot access processing status."""
        # Create another user's session
        other_user = create_test_user(username_prefix="other@example.com")
        session = SearchSession.objects.create(
            title="Other User Session", owner=other_user, status="processing_results"
        )

        url = reverse(
            "results_manager:processing_status", kwargs={"session_id": session.id}
        )
        response = self.client.get(url)

        # Should return 404 (not found) for security
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_session_returns_404(self) -> None:
        """Test that nonexistent sessions return 404."""
        fake_session_id = uuid.uuid4()
        url = reverse(
            "results_manager:processing_status", kwargs={"session_id": fake_session_id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
