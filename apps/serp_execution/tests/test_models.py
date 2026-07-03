"""
Tests for serp_execution models.

Tests for SearchExecution, RawSearchResult, and ExecutionMetrics models
including execution tracking, API integration, and metrics calculation.
"""

from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery

from ..models import RawSearchResult, SearchExecution
from apps.core.tests.utils import create_test_user

# Note: ExecutionMetrics import removed as model no longer exists

User = get_user_model()


class SearchExecutionModelTests(TestCase):
    """Test cases for SearchExecution model."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )

        # Create SearchStrategy first
        from apps.search_strategy.models import SearchStrategy

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test interest"],
            context_terms=["test context"],
            search_config={"domains": [], "include_general_search": True},
        )

        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test population AND test interest AND test context",
            query_type="general",
        )

    def test_execution_creation(self):
        """Test creating a search execution."""
        execution = SearchExecution.objects.create(
            query=self.query, initiated_by=self.user, search_engine="google"
        )

        self.assertEqual(execution.query, self.query)
        self.assertEqual(execution.status, "pending")
        self.assertEqual(execution.search_engine, "google")
        # Note: api_credits_used and estimated_cost fields removed from SearchExecution model
        self.assertIsNotNone(execution.id)
        self.assertTrue(execution.api_parameters == {})

    def test_execution_string_representation(self):
        """Test string representation of execution."""
        execution = SearchExecution.objects.create(
            query=self.query, search_engine="google", status="completed"
        )

        str_repr = str(execution)
        self.assertIn(str(execution.id), str_repr)
        self.assertIn("completed", str_repr)
        self.assertIn("google", str_repr)

    def test_can_retry_logic(self):
        """Test retry logic for failed executions."""
        execution = SearchExecution.objects.create(
            query=self.query, status="failed", retry_count=0
        )

        self.assertTrue(execution.can_retry())

        # After max retries
        execution.retry_count = 3
        self.assertFalse(execution.can_retry())

        # Different status
        execution.retry_count = 0
        execution.status = "completed"
        self.assertFalse(execution.can_retry())

        # Rate limited can retry
        execution.status = "rate_limited"
        execution.retry_count = 1
        self.assertTrue(execution.can_retry())

    def test_duration_calculation_on_save(self):
        """Test automatic duration calculation on save."""
        execution = SearchExecution.objects.create(query=self.query, status="running")

        # Set started_at
        execution.started_at = timezone.now() - timedelta(seconds=30)
        execution.status = "completed"
        execution.save()

        # Duration should be calculated
        self.assertIsNotNone(execution.duration_seconds)
        self.assertAlmostEqual(execution.duration_seconds, 30, delta=1)
        self.assertIsNotNone(execution.completed_at)

    def test_duration_not_calculated_for_non_completed(self):
        """Test duration not calculated for non-completed status."""
        execution = SearchExecution.objects.create(
            query=self.query,
            status="running",
            started_at=timezone.now() - timedelta(seconds=30),
        )

        execution.status = "failed"
        execution.save()

        # Duration should not be calculated for failed status
        self.assertIsNone(execution.duration_seconds)

    def test_status_choices(self):
        """Test all valid status choices."""
        valid_statuses = [
            "pending",
            "running",
            "completed",
            "failed",
            "cancelled",
            "rate_limited",
        ]

        for status in valid_statuses:
            execution = SearchExecution.objects.create(query=self.query, status=status)
            self.assertEqual(execution.status, status)
            self.assertIsNotNone(execution.get_status_display())

    def test_api_parameters_json_field(self):
        """Test API parameters JSON field."""
        params = {
            "q": "test query",
            "num": 100,
            "location": "United States",
            "filters": ["academic", "recent"],
        }

        execution = SearchExecution.objects.create(
            query=self.query, api_parameters=params
        )

        execution.refresh_from_db()
        self.assertEqual(execution.api_parameters, params)
        self.assertEqual(execution.api_parameters["q"], "test query")
        self.assertEqual(len(execution.api_parameters["filters"]), 2)

    # def test_cost_tracking(self):
    #     """Test cost tracking fields."""
    #     # NOTE: This test is commented out because api_credits_used and estimated_cost
    #     # fields have been removed from the SearchExecution model
    #     execution = SearchExecution.objects.create(
    #         query=self.query, api_credits_used=150, estimated_cost=Decimal("0.15")
    #     )
    #
    #     self.assertEqual(execution.api_credits_used, 150)
    #     self.assertEqual(execution.estimated_cost, Decimal("0.15"))
    #
    #     # Test decimal precision
    #     execution.estimated_cost = Decimal("0.1234")
    #     execution.save()
    #     execution.refresh_from_db()
    #     self.assertEqual(execution.estimated_cost, Decimal("0.1234"))

    def test_execution_relationships(self):
        """Test relationships with other models."""
        execution = SearchExecution.objects.create(
            query=self.query, initiated_by=self.user
        )

        # Test query relationship
        self.assertEqual(execution.query.session, self.session)
        # Note: SearchQuery doesn't have 'population' field, it's in the related strategy
        self.assertEqual(execution.query.strategy.population_terms, ["test population"])

        # Test user relationship
        self.assertEqual(execution.initiated_by, self.user)

        # Test cascade delete for query
        query_id = self.query.id
        self.query.delete()
        with self.assertRaises(SearchExecution.DoesNotExist):
            SearchExecution.objects.get(query__id=query_id)

    def test_execution_indexes(self):
        """Test database indexes are properly created."""
        # This is more of a migration test, but we can verify queries use indexes
        # by checking query performance with many records

        # Create multiple executions
        for i in range(10):
            SearchExecution.objects.create(
                query=self.query,
                status="completed" if i % 2 == 0 else "failed",
                celery_task_id=f"task-{i}",
            )

        # These queries should use indexes
        executions = SearchExecution.objects.filter(
            query=self.query, status="completed"
        )
        self.assertEqual(executions.count(), 5)

        execution = SearchExecution.objects.filter(celery_task_id="task-5").first()
        self.assertIsNotNone(execution)


class RawSearchResultModelTests(TestCase):
    """Test cases for RawSearchResult model."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )

        # Create SearchStrategy first
        from apps.search_strategy.models import SearchStrategy

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test interest"],
            context_terms=["test context"],
            search_config={"domains": [], "include_general_search": True},
        )

        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test population AND test interest AND test context",
            query_type="general",
        )
        self.execution = SearchExecution.objects.create(
            query=self.query, search_engine="google"
        )

    def test_raw_result_creation(self):
        """Test creating raw search results."""
        result = RawSearchResult.objects.create(
            execution=self.execution,
            position=1,
            title="Test Result",
            link="https://example.com/test",
            snippet="Test snippet content",
        )

        self.assertEqual(result.position, 1)
        self.assertEqual(result.title, "Test Result")
        self.assertEqual(result.link, "https://example.com/test")
        self.assertFalse(result.is_processed)
        self.assertFalse(result.has_pdf)
        self.assertFalse(result.has_date)
        # Note: is_academic field removed from RawSearchResult model
        self.assertEqual(result.raw_data, {})

    def test_string_representation(self):
        """Test string representation of result."""
        result = RawSearchResult.objects.create(
            execution=self.execution,
            position=1,
            title="A very long title that should be truncated in the string representation to avoid issues",
            link="https://example.com/test",
            snippet="Test snippet",
        )

        str_repr = str(result)
        self.assertIn("A very long title that should be truncated", str_repr)
        self.assertIn("Position 1", str_repr)
        self.assertTrue(len(str_repr) < 100)  # Should be truncated

    def test_get_domain(self):
        """Test domain extraction from URL."""
        test_cases = [
            ("https://www.example.com/path/to/page", "www.example.com"),
            ("http://subdomain.example.org", "subdomain.example.org"),
            ("https://example.co.uk/research", "example.co.uk"),
            ("https://user:pass@example.com/path", "example.com"),
            ("https://example.com:8080/path", "example.com:8080"),
        ]

        for url, expected_domain in test_cases:
            result = RawSearchResult.objects.create(
                execution=self.execution,
                position=1,
                title="Test",
                link=url,
                snippet="Test",
            )
            self.assertEqual(result.get_domain(), expected_domain)
            result.delete()

    def test_unique_position_constraint(self):
        """Test unique together constraint for execution and position."""
        # Create first result
        RawSearchResult.objects.create(
            execution=self.execution,
            position=1,
            title="First Result",
            link="https://example.com/1",
            snippet="First snippet",
        )

        # Try to create duplicate position
        with self.assertRaises(IntegrityError):
            RawSearchResult.objects.create(
                execution=self.execution,
                position=1,  # Same position
                title="Second Result",
                link="https://example.com/2",
                snippet="Second snippet",
            )

    def test_content_indicators(self):
        """Test content indicator fields."""
        result = RawSearchResult.objects.create(
            execution=self.execution,
            position=1,
            title="Research Paper PDF",
            link="https://university.edu/paper.pdf",
            snippet="Academic research on climate change",
            has_pdf=True,
            has_date=True,
            detected_date=datetime(2023, 6, 15).date(),
            # Note: is_academic field removed from RawSearchResult model
            language_code="en",
        )

        self.assertTrue(result.has_pdf)
        self.assertTrue(result.has_date)
        self.assertEqual(result.detected_date, datetime(2023, 6, 15).date())
        # Note: is_academic field removed from RawSearchResult model
        self.assertEqual(result.language_code, "en")

    def test_processing_status_fields(self):
        """Test processing status tracking."""
        result = RawSearchResult.objects.create(
            execution=self.execution,
            position=1,
            title="Test Result",
            link="https://example.com/test",
            snippet="Test snippet",
            is_processed=True,
            processing_error="Failed to extract metadata: timeout",
        )

        self.assertTrue(result.is_processed)
        self.assertIn("timeout", result.processing_error)

    def test_raw_data_storage(self):
        """Test raw API response storage."""
        raw_api_data = {
            "position": 1,
            "title": "Test Result",
            "link": "https://example.com/test",
            "snippet": "Test snippet",
            "displayLink": "example.com",
            "formattedUrl": "https://example.com/test",
            "pagemap": {
                "cse_thumbnail": [{"src": "https://example.com/thumb.jpg"}],
                "metatags": [{"author": "Test Author", "date": "2023-01-01"}],
            },
        }

        result = RawSearchResult.objects.create(
            execution=self.execution,
            position=1,
            title="Test Result",
            link="https://example.com/test",
            snippet="Test snippet",
            raw_data=raw_api_data,
        )

        result.refresh_from_db()
        self.assertEqual(result.raw_data, raw_api_data)
        self.assertEqual(
            result.raw_data["pagemap"]["metatags"][0]["author"], "Test Author"
        )

    def test_long_url_handling(self):
        """Test handling of very long URLs."""
        long_url = "https://example.com/" + "a" * 2000  # Very long URL

        result = RawSearchResult.objects.create(
            execution=self.execution,
            position=1,
            title="Test Result",
            link=long_url,
            snippet="Test snippet",
        )

        self.assertEqual(len(result.link), len(long_url))
        self.assertTrue(result.link.startswith("https://example.com/"))

    def test_cascade_delete(self):
        """Test cascade delete from execution."""
        # Create multiple results
        for i in range(3):
            RawSearchResult.objects.create(
                execution=self.execution,
                position=i + 1,
                title=f"Result {i + 1}",
                link=f"https://example.com/{i + 1}",
                snippet=f"Snippet {i + 1}",
            )

        self.assertEqual(
            RawSearchResult.objects.filter(execution=self.execution).count(), 3
        )

        # Delete execution
        execution_id = self.execution.id
        self.execution.delete()

        # All results should be deleted
        self.assertEqual(
            RawSearchResult.objects.filter(execution_id=execution_id).count(), 0
        )


# class ExecutionMetricsModelTests(TransactionTestCase):
#     """Test cases for ExecutionMetrics model."""
#     # NOTE: This entire test class is commented out because ExecutionMetrics
#     # model has been removed from the SearchExecution models
#
#     def setUp(self):
#         """Set up test data."""
#         self.user = create_test_user()
#         self.session = SearchSession.objects.create(
#             title="Test Session", owner=self.user
#         )
#         self.query1 = SearchQuery.objects.create(
#             session=self.session,
#             population="developers",
#             interest="testing",
#             context="python",
#             search_engines=["google"],
#         )
#         self.query2 = SearchQuery.objects.create(
#             session=self.session,
#             population="researchers",
#             interest="climate",
#             context="policy",
#             search_engines=["google", "bing"],
#         )
#
#     def test_metrics_creation(self):
#         """Test creating execution metrics."""
#         metrics = ExecutionMetrics.objects.create(
#             session=self.session,
#             total_executions=5,
#             successful_executions=4,
#             failed_executions=1,
#             total_results_retrieved=250,
#             unique_results=200,
#             total_api_credits=500,
#             total_estimated_cost=Decimal("0.50"),
#         )
#
#         self.assertEqual(metrics.session, self.session)
#         self.assertEqual(metrics.total_executions, 5)
#         self.assertEqual(metrics.successful_executions, 4)
#         self.assertEqual(metrics.failed_executions, 1)
#         self.assertEqual(metrics.total_results_retrieved, 250)
#         self.assertEqual(metrics.unique_results, 200)
#         self.assertEqual(metrics.total_api_credits, 500)
#         self.assertEqual(metrics.total_estimated_cost, Decimal("0.50"))
#
#     def test_one_to_one_relationship(self):
#         """Test one-to-one relationship with session."""
#         metrics = ExecutionMetrics.objects.create(session=self.session)
#
#         # Try to create another metrics for same session
#         with self.assertRaises(IntegrityError):
#             ExecutionMetrics.objects.create(session=self.session)
#
#         # Access from session
#         self.assertEqual(self.session.execution_metrics, metrics)
#
#     def test_string_representation(self):
#         """Test string representation."""
#         metrics = ExecutionMetrics.objects.create(session=self.session)
#
#         self.assertEqual(str(metrics), f"Metrics for {self.session.title}")
#
#     def test_update_metrics_method(self):
#         """Test the update_metrics method."""
#         # Create executions with different statuses
#         exec1 = SearchExecution.objects.create(
#             query=self.query1,
#             initiated_by=self.user,
#             status="completed",
#             results_count=50,
#             duration_seconds=2.5,
#         )
#
#         exec2 = SearchExecution.objects.create(
#             query=self.query1,
#             initiated_by=self.user,
#             status="completed",
#             results_count=75,
#             duration_seconds=3.0,
#             completed_at=timezone.now(),
#         )
#
#         exec3 = SearchExecution.objects.create(
#             query=self.query2,
#             initiated_by=self.user,
#             status="failed",
#         )
#
#         # Create metrics and update
#         metrics = ExecutionMetrics.objects.create(session=self.session)
#         metrics.update_metrics()
#
#         # Verify calculations
#         self.assertEqual(metrics.total_executions, 3)
#         self.assertEqual(metrics.successful_executions, 2)
#         self.assertEqual(metrics.failed_executions, 1)
#         self.assertEqual(metrics.total_results_retrieved, 125)  # 50 + 75
#         self.assertEqual(metrics.total_api_credits, 300)  # 100 + 150 + 50
#         self.assertEqual(metrics.total_estimated_cost, Decimal("0.30"))
#         self.assertAlmostEqual(
#             float(metrics.average_execution_time), 2.75, places=2
#         )  # (2.5 + 3.0) / 2
#         self.assertEqual(metrics.last_execution, exec2.completed_at)
#
#     def test_quality_metrics(self):
#         """Test quality metrics fields."""
#         metrics = ExecutionMetrics.objects.create(
#             session=self.session, academic_results_count=45, pdf_results_count=30
#         )
#
#         self.assertEqual(metrics.academic_results_count, 45)
#         self.assertEqual(metrics.pdf_results_count, 30)
#
#     def test_rate_limiting_metrics(self):
#         """Test rate limiting tracking."""
#         now = timezone.now()
#         metrics = ExecutionMetrics.objects.create(
#             session=self.session, rate_limit_hits=3, last_rate_limit=now
#         )
#
#         self.assertEqual(metrics.rate_limit_hits, 3)
#         self.assertEqual(metrics.last_rate_limit, now)
#
#     def test_metrics_with_no_executions(self):
#         """Test update_metrics with no executions."""
#         metrics = ExecutionMetrics.objects.create(session=self.session)
#         metrics.update_metrics()
#
#         # Should handle gracefully with zeros
#         self.assertEqual(metrics.total_executions, 0)
#         self.assertEqual(metrics.successful_executions, 0)
#         self.assertEqual(metrics.failed_executions, 0)
#         self.assertEqual(metrics.total_results_retrieved, 0)
#         self.assertEqual(metrics.total_api_credits, 0)
#         self.assertEqual(metrics.total_estimated_cost, Decimal("0.00"))
#         self.assertIsNone(metrics.average_execution_time)
#         self.assertIsNone(metrics.last_execution)
#
#     def test_cascade_delete_with_session(self):
#         """Test cascade delete when session is deleted."""
#         metrics = ExecutionMetrics.objects.create(
#             session=self.session, total_executions=10
#         )
#
#         metrics_id = metrics.id
#         self.session.delete()
#
#         # Metrics should be deleted
#         with self.assertRaises(ExecutionMetrics.DoesNotExist):
#             ExecutionMetrics.objects.get(id=metrics_id)
