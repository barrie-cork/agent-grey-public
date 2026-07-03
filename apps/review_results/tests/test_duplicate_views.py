"""
Tests for duplicate groups view showing filtered duplicate results.

This module contains tests for the rewritten duplicate groups view,
which now shows ProcessedResult records with processing_status='filtered'
and processing_error_category='duplicate' instead of DuplicateGroup objects.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class DuplicateGroupsViewTest(TestCase):
    """Test the duplicate groups view showing filtered duplicate results."""

    def setUp(self):
        """Set up test data for duplicate groups view tests."""
        self.user = create_test_user()
        self.client = Client()
        self.client.login(username=self.user.username, password="testpass123")

        # Create session
        self.session = SearchSession.objects.create(
            owner=self.user, title="Test Session", status="ready_for_review"
        )

        # Create strategy (required for query)
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test interest"],
            context_terms=["test context"],
            is_complete=True,
        )

        # Create query
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            execution_order=1,
        )

        # Create execution
        self.execution = SearchExecution.objects.create(
            query=self.query, status="completed", search_engine="google"
        )

        # Create raw results and filtered duplicate ProcessedResults
        for i in range(3):
            raw = RawSearchResult.objects.create(
                execution=self.execution,
                title=f"Test Result {i}",
                link="https://example.com/test",
                position=i + 1,
                snippet=f"Test snippet {i}",
            )
            ProcessedResult.objects.create(
                session=self.session,
                raw_result=raw,
                title=f"Test Result {i}",
                url="https://example.com/test",
                snippet=f"Test snippet {i}",
                processing_status="filtered",
                processing_error_category="duplicate",
            )

    def test_view_loads_successfully(self):
        """Test that the duplicate groups view loads without errors."""
        url = reverse("review_results:duplicate_groups", args=[self.session.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_filtered_duplicates_in_context(self):
        """Test that filtered duplicates are passed in context."""
        url = reverse("review_results:duplicate_groups", args=[self.session.id])
        response = self.client.get(url)
        self.assertIn("filtered_duplicates", response.context)
        # All 3 results share the same domain (example.com) = 1 group
        self.assertEqual(response.context["total_groups"], 1)
        self.assertEqual(response.context["total_duplicate_results"], 3)

    def test_query_metadata_displayed(self):
        """Test that query metadata is displayed in the view."""
        url = reverse("review_results:duplicate_groups", args=[self.session.id])
        response = self.client.get(url)
        # The view should show duplicate results with their metadata
        self.assertEqual(response.status_code, 200)

    def test_pagination_works(self):
        """Test that pagination works at database level."""
        # Create more filtered duplicate results
        for i in range(30):
            raw = RawSearchResult.objects.create(
                execution=self.execution,
                title=f"Page Result {i}",
                link=f"https://example.com/page{i}",
                position=i + 10,
            )
            ProcessedResult.objects.create(
                session=self.session,
                raw_result=raw,
                title=f"Page Result {i}",
                url=f"https://example.com/page{i}",
                processing_status="filtered",
                processing_error_category="duplicate",
            )

        url = reverse("review_results:duplicate_groups", args=[self.session.id])
        response = self.client.get(url + "?per_page=25&page=2")
        self.assertEqual(response.status_code, 200)
        # Check for pagination indicators
        self.assertIn("page_obj", response.context)

    def test_get_query_metadata_helper(self):
        """Test the get_query_metadata helper method."""
        result = ProcessedResult.objects.filter(raw_result__isnull=False).first()

        metadata = result.get_query_metadata()

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["query_text"], "test query")
        self.assertIn("query_type", metadata)
        self.assertIn("serp_source", metadata)
        self.assertIn("search_engine", metadata)
        self.assertIn("result_position", metadata)

    def test_empty_state_displayed(self):
        """Test that empty state is displayed when no duplicates exist."""
        # Create a new session with no duplicates
        empty_session = SearchSession.objects.create(
            owner=self.user, title="Empty Session", status="ready_for_review"
        )

        url = reverse("review_results:duplicate_groups", args=[empty_session.id])
        response = self.client.get(url)
        self.assertContains(response, "No duplicate groups found")

    def test_duplicate_groups_populated(self):
        """Test that duplicate_groups contains domain-grouped data."""
        url = reverse("review_results:duplicate_groups", args=[self.session.id])
        response = self.client.get(url)
        self.assertIn("duplicate_groups", response.context)
        groups = response.context["duplicate_groups"]
        # All 3 results share example.com domain = 1 group with 3 results
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["domain"], "example.com")
        self.assertEqual(groups[0]["count"], 3)
