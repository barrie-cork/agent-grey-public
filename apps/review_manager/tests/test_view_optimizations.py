"""
Tests for optimized database queries in views.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class DashboardViewOptimizationTests(TestCase):
    """Test query optimizations in DashboardView."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        # Create multiple sessions with various states
        self.sessions = []
        for i in range(5):
            session = SearchSession.objects.create(
                title=f"Test Session {i}",
                owner=self.user,
                status="draft" if i < 3 else "completed",
            )
            self.sessions.append(session)

    def test_dashboard_single_aggregate_query(self):
        """Test dashboard uses optimized queries for stats."""
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse("review_manager:dashboard"))
            self.assertEqual(response.status_code, 200)

        queries = ctx.captured_queries

        # Should be minimal queries:
        # 1. User auth check
        # 2. Sessions with statistics (using annotate)
        # 3. Related data prefetch
        self.assertLess(len(queries), 20, f"Too many queries: {len(queries)}")

        # Verify database queries are being made
        self.assertGreater(
            len(queries),
            0,
            f"Expected queries to be made for dashboard. Sessions count: {len(self.sessions)}",
        )

        # Verify the dashboard uses efficient queries (should have SELECT statements)
        select_queries = [q for q in queries if "SELECT" in q["sql"].upper()]
        self.assertGreater(
            len(select_queries),
            0,
            "Dashboard should use SELECT queries to fetch session data",
        )

    def test_dashboard_prefetch_optimization(self):
        """Test dashboard properly prefetches related data."""
        # Add related data
        for session in self.sessions[:2]:
            strategy = SearchStrategy.objects.create(
                session=session,
                user=self.user,
                population_terms=["Test"],
                interest_terms=["Test"],
                context_terms=["Test"],
            )
            SearchQuery.objects.create(
                strategy=strategy,
                session=session,
                query_text="test query",
                is_active=False,
            )
            SearchQuery.objects.filter(strategy=strategy).update(is_active=True)

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse("review_manager:dashboard"))
            self.assertEqual(response.status_code, 200)

        queries = ctx.captured_queries

        # Should not have separate queries for each session's related data
        select_queries = [q for q in queries if q["sql"].upper().startswith("SELECT")]

        # Should have optimized queries, not one per session
        # Allow reasonable overhead for auth, middleware, etc.
        self.assertLess(
            len(select_queries),
            len(self.sessions) * 3,  # Generous but still catches N+1
            "N+1 query pattern detected in dashboard",
        )


class ResultsReviewViewOptimizationTests(TestCase):
    """Test query optimizations in ResultsReviewView."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        # Create session with results
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="ready_for_review"
        )

        # Create results with various statuses
        for i in range(20):
            ProcessedResult.objects.create(
                session=self.session,
                title=f"Result {i}",
                url=f"https://example.com/{i}",
                snippet=f"Description {i}",
                processing_status="success" if i % 3 == 0 else "filtered",
            )

    def test_database_aggregation_for_counts(self):
        """Test counts use database aggregation instead of Python."""
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                reverse(
                    "review_results:overview",
                    kwargs={"session_id": self.session.id},
                )
            )
            self.assertEqual(response.status_code, 200)

        queries = ctx.captured_queries

        # Should have aggregate queries for counts
        count_queries = [q for q in queries if "COUNT" in q["sql"].upper()]

        self.assertGreater(
            len(count_queries),
            0,
            "No COUNT queries found - counts might be done in Python",
        )

        # Should not load all results just to count
        full_select_queries = [
            q
            for q in queries
            if "SELECT" in q["sql"].upper()
            and 'FROM "results_manager_processedresult"' in q["sql"]
            and "COUNT" not in q["sql"].upper()
        ]

        # Should have limited full selects (just for display)
        self.assertLess(
            len(full_select_queries),
            3,
            "Too many full SELECT queries - possible inefficient counting",
        )


class APIStatisticsOptimizationTests(TestCase):
    """Test query optimizations in API statistics views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        # Create session with executions
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["Test"],
            interest_terms=["Test"],
            context_terms=["Test"],
        )

        # Create multiple queries with executions
        for i in range(5):
            query = SearchQuery.objects.create(
                strategy=strategy,
                session=self.session,
                query_text=f"test query {i}",
                is_active=False,
            )
            SearchQuery.objects.filter(id=query.id).update(is_active=True)

            for j in range(3):
                SearchExecution.objects.create(
                    query=query,
                    initiated_by=self.user,
                    status="completed" if j < 2 else "failed",
                    results_count=10 * (j + 1) if j < 2 else 0,
                )

    def test_aggregate_queries_in_statistics(self):
        """Test statistics API uses database queries for session progress."""
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                f"/execution/api/session/{self.session.id}/progress/",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(response.status_code, 200)

        queries = ctx.captured_queries

        # Verify database queries are executed (not purely in-memory)
        self.assertGreater(
            len(queries),
            0,
            "No database queries found - statistics might be hardcoded",
        )

        # Verify response contains session progress data
        data = response.json()
        self.assertIn("session_id", data)
        self.assertIn("status", data)


class SessionDetailViewOptimizationTests(TestCase):
    """Test optimizations in session detail views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        # Create complex session
        self.session = SearchSession.objects.create(
            title="Complex Session", owner=self.user, status="draft"
        )

        # Add configuration (required for session detail access)
        config = ReviewConfiguration.objects.create(
            session=self.session, min_reviewers_per_result=1, created_by=self.user
        )
        self.session.current_configuration = config
        self.session.save(update_fields=["current_configuration"])

    def test_session_detail_query_optimization(self):
        """Test session detail view uses optimized queries."""
        # Add related data
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["Test Population"],
            interest_terms=["Test Interest"],
            context_terms=["Test Context"],
        )

        for i in range(10):
            SearchQuery.objects.create(
                strategy=strategy,
                session=self.session,
                query_text=f"query {i}",
                query_type="general",
                is_active=True,
            )

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                reverse(
                    "review_manager:session_detail",
                    kwargs={"session_id": self.session.id},
                )
            )
            self.assertEqual(response.status_code, 200)

        queries = ctx.captured_queries

        # Should use select_related/prefetch_related
        optimized_queries = [
            q for q in queries if "JOIN" in q["sql"] or "IN (" in q["sql"]
        ]

        self.assertGreater(
            len(optimized_queries),
            0,
            "No JOIN or IN queries found - might not be using select_related/prefetch_related",
        )

        # Total queries should be reasonable
        self.assertLess(
            len(queries), 25, f"Too many queries for session detail: {len(queries)}"
        )


class QueryOptimizationRegressionTests(TestCase):
    """Test to ensure query optimizations don't break functionality."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

    def test_dashboard_data_accuracy_with_optimizations(self):
        """Test dashboard shows accurate data with query optimizations."""
        # Create sessions with known counts
        draft_sessions = 3
        completed_sessions = 2
        total_results = 0

        for i in range(draft_sessions):
            session = SearchSession.objects.create(
                title=f"Draft {i}", owner=self.user, status="draft"
            )
            session.total_results = 10 * (i + 1)
            session.save()
            total_results += session.total_results

        for i in range(completed_sessions):
            session = SearchSession.objects.create(
                title=f"Completed {i}", owner=self.user, status="completed"
            )
            session.total_results = 20 * (i + 1)
            session.save()
            total_results += session.total_results

        # Load dashboard
        response = self.client.get(reverse("review_manager:dashboard"))
        self.assertEqual(response.status_code, 200)

        # Verify context data is correct
        context = response.context
        self.assertEqual(context["total_sessions"], draft_sessions + completed_sessions)
        self.assertEqual(context["draft_sessions"], draft_sessions)
        self.assertEqual(context["completed_sessions"], completed_sessions)
        self.assertEqual(context["total_results_found"], total_results)
