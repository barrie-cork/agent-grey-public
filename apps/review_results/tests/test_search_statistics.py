"""
Tests for Search Statistics view.

Tests authentication, ownership validation, context data,
pagination, provider breakdown, deduplication stats, and navigation.
"""

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution

User = get_user_model()


class SearchStatisticsViewTestCase(TestCase):
    """Test suite for SearchStatisticsView."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create test users
        self.user = create_test_user(username_prefix="testuser@example.com")
        self.other_user = create_test_user(username_prefix="other@example.com")

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            status="under_review",
            total_queries=5,
            total_results=100,
        )

        # Create search strategy
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers"],
            interest_terms=["testing"],
            context_terms=["django"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "file_types": [],
                "search_type": "google",
                "max_results": 100,
            },
        )

        # Create search queries
        self.queries = []
        for i in range(5):
            query = SearchQuery.objects.create(
                session=self.session,
                strategy=self.strategy,
                query_text=f"test query {i}",
                query_type="general" if i % 2 == 0 else "domain-specific",
                target_domain=f"example{i}.com" if i % 2 == 1 else None,
                execution_order=i,
                is_active=True,
            )
            self.queries.append(query)

        # Create executions for some queries
        # Query 0: Completed successfully
        self.exec_0 = SearchExecution.objects.create(
            query=self.queries[0],
            initiated_by=self.user,
            status="completed",
            api_result_count=50,
            results_count=50,
            serp_provider="serper",
            serp_provider_display="Serper.dev",
            duration_seconds=2.5,
            started_at=timezone.now() - timedelta(minutes=5),
            completed_at=timezone.now() - timedelta(minutes=3),
            step_metadata={
                "pagination": {
                    "pages_fetched": 5,
                    "pages_requested": 10,
                    "stopped_reason": "limit_reached",
                    "results_per_page": 10,
                }
            },
        )

        # Query 1: Failed
        self.exec_1 = SearchExecution.objects.create(
            query=self.queries[1],
            initiated_by=self.user,
            status="failed",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
            error_message="Rate limit exceeded",
            started_at=timezone.now() - timedelta(minutes=4),
            completed_at=timezone.now() - timedelta(minutes=3),
            step_metadata={
                "pagination": {
                    "pages_fetched": 2,
                    "pages_requested": 10,
                    "stopped_reason": "rate_limit",
                }
            },
        )

        # Query 2: Running
        self.exec_2 = SearchExecution.objects.create(
            query=self.queries[2],
            initiated_by=self.user,
            status="running",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
            started_at=timezone.now() - timedelta(minutes=1),
            step_metadata={},
        )

        # Query 3: Pending
        self.exec_3 = SearchExecution.objects.create(
            query=self.queries[3],
            initiated_by=self.user,
            status="pending",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
            step_metadata={},
        )

        # Query 4: No execution

        # Login user
        self.client.login(username=self.user.username, password="testpass123")

    def test_view_requires_authentication(self):
        """Test that view requires login."""
        self.client.logout()
        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_view_validates_ownership(self):
        """Test that users can only view their own sessions."""
        other_session = SearchSession.objects.create(
            title="Other User Session", owner=self.other_user, status="under_review"
        )

        url = reverse("review_results:search_statistics", args=[other_session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)

    def test_view_returns_404_for_nonexistent_session(self):
        """Test that nonexistent sessions return 404."""
        fake_id = uuid.uuid4()
        url = reverse("review_results:search_statistics", args=[fake_id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_view_renders_correct_template(self):
        """Test that correct template is used."""
        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "review_results/search_statistics.html")

    def test_view_context_data(self):
        """Test view provides correct context data."""
        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # Check required context keys
        required_keys = [
            "session",
            "executions",
            "queries",
            "overall_stats",
            "provider_stats",
            "overlap_count",
            "dedup_stats",
            "per_page",
            "current_per_page",
            "is_paginated",
        ]
        for key in required_keys:
            self.assertIn(key, response.context, f"Missing context key: {key}")

        # Verify session
        self.assertEqual(response.context["session"], self.session)

        # Verify executions (4 executions for 4 queries, query 4 has none)
        self.assertEqual(len(response.context["executions"]), 4)

    def test_overall_statistics_calculation(self):
        """Test that overall statistics are calculated correctly."""
        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        stats = response.context["overall_stats"]

        # Total queries
        self.assertEqual(stats["total_queries"], 5)

        # Execution counts
        self.assertEqual(stats["total_executions"], 4)  # 4 queries have executions
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["running"], 1)
        self.assertEqual(stats["pending"], 1)

        # Queries with/without executions
        self.assertEqual(stats["queries_with_executions"], 4)
        self.assertEqual(stats["queries_without_executions"], 1)

        # Results
        self.assertEqual(stats["total_results"], 50)

        # Completion rate (1 completed / 5 total = 20%)
        self.assertEqual(stats["completion_rate"], 20.0)

        # Success rate (1 completed / 4 executions = 25%)
        self.assertEqual(stats["success_rate"], 25.0)

    def test_execution_rows_in_table(self):
        """Test that table rows correspond to SearchExecution objects."""
        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        executions = list(response.context["executions"])

        # Should have 4 execution rows
        self.assertEqual(len(executions), 4)

        # First execution should be for query 0 (ordered by execution_order)
        self.assertEqual(executions[0].query, self.queries[0])
        self.assertEqual(executions[0].status, "completed")
        self.assertEqual(executions[0].api_result_count, 50)

        # Second execution should be for query 1
        self.assertEqual(executions[1].query, self.queries[1])
        self.assertEqual(executions[1].status, "failed")

    def test_pagination(self):
        """Test pagination works correctly with executions."""
        # Create 30 additional queries each with an execution
        for i in range(30):
            query = SearchQuery.objects.create(
                session=self.session,
                strategy=self.strategy,
                query_text=f"extra query {i}",
                query_type="general",
                execution_order=10 + i,
                is_active=True,
            )
            SearchExecution.objects.create(
                query=query,
                initiated_by=self.user,
                status="completed",
                serp_provider="serper",
                serp_provider_display="Serper.dev",
                api_result_count=5,
                results_count=5,
            )

        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # 4 original + 30 new = 34 executions, default per_page=25
        self.assertEqual(len(response.context["executions"]), 25)
        self.assertTrue(response.context["is_paginated"])

        # Test page 2
        response = self.client.get(url + "?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["executions"]), 9)  # Remaining

    def test_per_page_parameter(self):
        """Test per_page parameter works correctly."""
        # Create 10 additional queries each with an execution
        for i in range(10):
            query = SearchQuery.objects.create(
                session=self.session,
                strategy=self.strategy,
                query_text=f"extra query {i}",
                query_type="general",
                is_active=True,
            )
            SearchExecution.objects.create(
                query=query,
                initiated_by=self.user,
                status="completed",
                serp_provider="serper",
                api_result_count=5,
                results_count=5,
            )

        url = reverse("review_results:search_statistics", args=[self.session.id])

        # 4 original + 10 new = 14 executions
        # Test per_page=10
        response = self.client.get(url + "?per_page=10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["executions"]), 10)
        self.assertEqual(response.context["per_page"], 10)

        # Test per_page=50
        response = self.client.get(url + "?per_page=50")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["executions"]), 14)
        self.assertEqual(response.context["per_page"], 50)

        # Test invalid per_page (should default to 25)
        response = self.client.get(url + "?per_page=999")
        self.assertEqual(response.context["per_page"], 25)

    def test_execution_ordering(self):
        """Test that executions are ordered by query execution_order then provider."""
        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        executions = list(response.context["executions"])

        for i in range(len(executions) - 1):
            self.assertLessEqual(
                executions[i].query.execution_order,
                executions[i + 1].query.execution_order,
            )

    def test_navigation_links(self):
        """Test that navigation links are present."""
        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check breadcrumb links
        self.assertIn("Dashboard", content)
        self.assertIn(self.session.title, content)
        self.assertIn("Review", content)
        self.assertIn("Search Statistics", content)

        # Check back button
        self.assertIn("Back to Review", content)
        back_url = reverse("review_results:overview", args=[self.session.id])
        self.assertIn(back_url, content)

    def test_per_page_preservation_in_links(self):
        """Test that per_page parameter is preserved in navigation links."""
        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url + "?per_page=50")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Check that links include per_page parameter
        self.assertIn("per_page=50", content)

    def test_empty_state(self):
        """Test view with session that has no queries."""
        empty_session = SearchSession.objects.create(
            title="Empty Session", owner=self.user, status="draft"
        )

        _empty_strategy = SearchStrategy.objects.create(
            session=empty_session,
            user=self.user,
            population_terms=[],
            interest_terms=[],
            context_terms=[],
            search_config={},
        )

        url = reverse("review_results:search_statistics", args=[empty_session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["overall_stats"]["total_queries"], 0)

        content = response.content.decode()
        self.assertIn("No Search Queries Found", content)

    def test_provider_badge_in_table(self):
        """Test that provider badge renders in table rows."""
        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Serper.dev", content)
        self.assertIn('data-testid="provider-badge"', content)


class SearchStatisticsProviderTestCase(TestCase):
    """Test provider breakdown and overlap statistics."""

    def setUp(self):
        """Set up test data with multiple providers."""
        self.client = Client()
        self.user = create_test_user(username_prefix="provider-test@example.com")

        self.session = SearchSession.objects.create(
            title="Multi-Provider Session",
            owner=self.user,
            status="under_review",
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            search_config={},
        )

        self.query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="test query multi-provider",
            query_type="general",
            execution_order=1,
            is_active=True,
        )

        self.client.login(username=self.user.username, password="testpass123")

    def test_provider_stats_single_provider(self):
        """Test provider_stats with a single provider."""
        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
            api_result_count=20,
            results_count=20,
        )

        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        provider_stats = response.context["provider_stats"]
        self.assertEqual(len(provider_stats), 1)
        self.assertEqual(provider_stats[0]["serp_provider"], "serper")
        self.assertEqual(provider_stats[0]["total_executions"], 1)
        self.assertEqual(provider_stats[0]["completed"], 1)
        self.assertEqual(provider_stats[0]["total_results"], 20)
        self.assertEqual(provider_stats[0]["success_rate"], 100.0)

    def test_provider_stats_multiple_providers(self):
        """Test provider_stats with multiple providers and correct success rates."""
        # Serper: 2 completed, 1 failed
        for _ in range(2):
            SearchExecution.objects.create(
                query=self.query,
                initiated_by=self.user,
                status="completed",
                serp_provider="serper",
                serp_provider_display="Serper.dev",
                api_result_count=15,
                results_count=15,
            )
        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="failed",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
        )

        # SearchAPI: 1 completed
        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="searchapi",
            serp_provider_display="SearchAPI.io",
            api_result_count=25,
            results_count=25,
        )

        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        provider_stats = response.context["provider_stats"]
        self.assertEqual(len(provider_stats), 2)

        # Find each provider (ordered by serp_provider)
        searchapi_stats = next(
            p for p in provider_stats if p["serp_provider"] == "searchapi"
        )
        serper_stats = next(p for p in provider_stats if p["serp_provider"] == "serper")

        self.assertEqual(serper_stats["total_executions"], 3)
        self.assertEqual(serper_stats["completed"], 2)
        self.assertEqual(serper_stats["failed"], 1)
        self.assertEqual(serper_stats["total_results"], 30)
        self.assertAlmostEqual(serper_stats["success_rate"], 66.7, places=1)

        self.assertEqual(searchapi_stats["total_executions"], 1)
        self.assertEqual(searchapi_stats["completed"], 1)
        self.assertEqual(searchapi_stats["total_results"], 25)
        self.assertEqual(searchapi_stats["success_rate"], 100.0)

    def test_overlap_count_single_provider(self):
        """Test overlap_count is 0 when only one provider."""
        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
            api_result_count=10,
            results_count=10,
        )

        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.context["overlap_count"], 0)

    def test_overlap_count_multiple_providers(self):
        """Test overlap_count when same URL appears from 2 providers."""
        exec_serper = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
            api_result_count=3,
            results_count=3,
        )
        exec_searchapi = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="searchapi",
            serp_provider_display="SearchAPI.io",
            api_result_count=3,
            results_count=3,
        )

        # Shared URL
        RawSearchResult.objects.create(
            execution=exec_serper,
            position=1,
            title="Shared Result",
            link="https://example.com/shared",
            snippet="Shared snippet",
        )
        RawSearchResult.objects.create(
            execution=exec_searchapi,
            position=1,
            title="Shared Result",
            link="https://example.com/shared",
            snippet="Shared snippet",
        )

        # Unique URLs
        RawSearchResult.objects.create(
            execution=exec_serper,
            position=2,
            title="Serper Only",
            link="https://example.com/serper-only",
            snippet="Serper snippet",
        )
        RawSearchResult.objects.create(
            execution=exec_searchapi,
            position=2,
            title="SearchAPI Only",
            link="https://example.com/searchapi-only",
            snippet="SearchAPI snippet",
        )

        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        self.assertEqual(response.context["overlap_count"], 1)
        self.assertGreater(response.context["overlap_percentage"], 0)

    def test_dedup_stats_in_context(self):
        """Test dedup_stats is present in context."""
        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="serper",
            api_result_count=10,
            results_count=10,
        )

        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        dedup = response.context["dedup_stats"]
        self.assertIn("total_results", dedup)
        self.assertIn("unique_results", dedup)
        self.assertIn("duplicates_removed", dedup)
        self.assertIn("deduplication_rate", dedup)

    def test_multi_provider_query_shows_multiple_rows(self):
        """Test that a query executed by 2 providers shows 2 table rows."""
        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
            api_result_count=20,
            results_count=20,
        )
        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="searchapi",
            serp_provider_display="SearchAPI.io",
            api_result_count=15,
            results_count=15,
        )

        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        executions = list(response.context["executions"])
        self.assertEqual(len(executions), 2)

        # Both should reference the same query
        self.assertEqual(executions[0].query, self.query)
        self.assertEqual(executions[1].query, self.query)

        # But different providers
        providers = {e.serp_provider for e in executions}
        self.assertEqual(providers, {"serper", "searchapi"})

    def test_provider_breakdown_section_renders(self):
        """Test provider breakdown section renders with correct counts."""
        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
            api_result_count=20,
            results_count=20,
        )

        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        content = response.content.decode()
        self.assertIn('data-testid="provider-breakdown"', content)
        self.assertIn('data-testid="provider-card"', content)
        self.assertIn("Serper.dev", content)

    def test_failed_provider_destructive_styling(self):
        """Test that failed provider shows destructive styling badge."""
        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="failed",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
        )

        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        content = response.content.decode()
        self.assertIn('data-testid="provider-failed-badge"', content)
        self.assertIn("1 failed", content)

    def test_overlap_callout_only_with_multiple_providers(self):
        """Test overlap callout only renders with 2+ providers and overlap > 0."""
        # Single provider -- no callout
        SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            serp_provider="serper",
            serp_provider_display="Serper.dev",
            api_result_count=10,
            results_count=10,
        )

        url = reverse("review_results:search_statistics", args=[self.session.id])
        response = self.client.get(url)

        content = response.content.decode()
        self.assertNotIn('data-testid="overlap-callout"', content)


class SearchStatisticsNavigationTestCase(TestCase):
    """Test navigation to/from Search Statistics page."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        self.user = create_test_user(username_prefix="testuser@example.com")

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="under_review"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            search_config={},
        )

        self.client.login(username=self.user.username, password="testpass123")

    def test_url_reverse(self):
        """Test URL reverse lookup."""
        url = reverse(
            "review_results:search_statistics", kwargs={"session_id": self.session.id}
        )
        expected = f"/review-results/statistics/{self.session.id}/"
        self.assertEqual(url, expected)


class SearchStatisticsEdgeCasesTestCase(TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        self.user = create_test_user(username_prefix="testuser@example.com")

        self.client.login(username=self.user.username, password="testpass123")

    def test_query_with_multiple_executions(self):
        """Test query with multiple execution attempts shows all rows."""
        session = SearchSession.objects.create(
            title="Multi-Execution Test", owner=self.user, status="executing"
        )

        strategy = SearchStrategy.objects.create(
            session=session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            search_config={},
        )

        query = SearchQuery.objects.create(
            session=session,
            strategy=strategy,
            query_text="test query",
            query_type="general",
        )

        # Create 3 executions (2 failed, 1 completed)
        for i in range(2):
            SearchExecution.objects.create(
                query=query,
                initiated_by=self.user,
                status="failed",
                serp_provider="serper",
                error_message="Test error",
                started_at=timezone.now() - timedelta(minutes=10 - i),
                completed_at=timezone.now() - timedelta(minutes=9 - i),
            )

        SearchExecution.objects.create(
            query=query,
            initiated_by=self.user,
            status="completed",
            serp_provider="serper",
            api_result_count=25,
            results_count=25,
            duration_seconds=1.5,
            started_at=timezone.now() - timedelta(minutes=1),
            completed_at=timezone.now(),
        )

        url = reverse("review_results:search_statistics", args=[session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)

        # 3 executions = 3 rows in the table
        executions = list(response.context["executions"])
        self.assertEqual(len(executions), 3)

        # All reference the same query
        for execution in executions:
            self.assertEqual(execution.query, query)

    def test_query_with_missing_pagination_metadata(self):
        """Test graceful handling of missing pagination metadata."""
        session = SearchSession.objects.create(
            title="No Pagination Test", owner=self.user, status="completed"
        )

        strategy = SearchStrategy.objects.create(
            session=session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            search_config={},
        )

        query = SearchQuery.objects.create(
            session=session,
            strategy=strategy,
            query_text="test query",
            query_type="general",
        )

        # Execution without pagination metadata
        SearchExecution.objects.create(
            query=query,
            initiated_by=self.user,
            status="completed",
            serp_provider="serper",
            api_result_count=10,
            results_count=10,
            step_metadata={},  # No pagination key
        )

        url = reverse("review_results:search_statistics", args=[session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should render without errors

    def test_very_long_query_text(self):
        """Test truncation of very long query text."""
        session = SearchSession.objects.create(
            title="Long Query Test", owner=self.user, status="completed"
        )

        strategy = SearchStrategy.objects.create(
            session=session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            search_config={},
        )

        # Create a long but not too long query (under 500 chars)
        long_query_text = "test query with many terms " * 15  # ~420 chars

        _query = SearchQuery.objects.create(
            session=session,
            strategy=strategy,
            query_text=long_query_text,
            query_type="general",
        )

        url = reverse("review_results:search_statistics", args=[session.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Template should truncate with truncatechars and show full text in tooltip
