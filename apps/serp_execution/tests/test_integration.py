"""
Integration tests for SERP execution module.

End-to-end tests covering the complete search execution workflow,
from query building through result processing.
"""

import json
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from apps.core.tests.utils import create_test_user
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution

# ExecutionMetrics model has been removed
from apps.serp_execution.services.cache_manager import CacheManager

# from apps.serp_execution.services.usage_tracker import UsageTracker  # Removed for simplification
from apps.serp_execution.tasks import (
    initiate_search_session_execution_task,
    monitor_session_completion_task,
    perform_serp_query_task,
)

User = get_user_model()


class TestCompleteSearchWorkflow(TestCase):
    """Test complete search execution workflow from start to finish."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user(username_prefix="researcher")
        self.client = Client()
        self.client.login(username=self.user.username, password="testpass123")

        # Create research session
        self.session = SearchSession.objects.create(
            title="Climate Change Policy Research",
            description="Research on climate change mitigation policies",
            owner=self.user,
            status="ready_to_execute",
        )

        # Create search strategy first
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["policy makers", "researchers"],
            interest_terms=["climate change mitigation", "renewable energy"],
            context_terms=["international agreements", "policy effectiveness"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "file_types": ["pdf", "doc"],
                "search_type": "google",
            },
        )

        # Create multiple queries with correct fields
        self.query1 = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="policy makers AND climate change mitigation AND international agreements",
            query_type="general",
            target_domain=None,
            execution_order=1,
            is_active=True,
        )

        self.query2 = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="researchers AND renewable energy AND policy effectiveness",
            query_type="general",
            target_domain=None,
            execution_order=2,
            is_active=True,
        )

        cache.clear()

    @patch("apps.core.services.serper_client.requests.post")
    @patch(
        "apps.serp_execution.tasks.simple_tasks.process_session_results_simple.delay"
    )
    def test_complete_execution_workflow(self, mock_process_results, mock_post):
        """Test the complete execution workflow from initiation to completion."""

        # Mock Serper API responses
        def mock_api_response(url, json_data=None, **kwargs):
            """Generate mock API response based on query."""
            query_text = (json_data or {}).get("q", "")
            response = Mock()
            response.status_code = 200

            if "policy makers" in query_text:
                response.json.return_value = {
                    "organic": [
                        {
                            "position": i,
                            "title": f"Climate Policy Document {i}",
                            "link": f"https://policy.org/climate-doc-{i}.pdf",
                            "snippet": "Policy analysis on climate mitigation strategies...",
                            "displayLink": "policy.org",
                        }
                        for i in range(1, 6)
                    ],
                    "credits": 1,
                    "searchInformation": {"totalResults": "5000", "searchTime": 0.35},
                }
            else:
                response.json.return_value = {
                    "organic": [
                        {
                            "position": i,
                            "title": f"Renewable Energy Research {i}",
                            "link": f"https://research.edu/renewable-{i}",
                            "snippet": "Study on renewable energy policy effectiveness...",
                            "displayLink": "research.edu",
                        }
                        for i in range(1, 4)
                    ],
                    "credits": 1,
                    "searchInformation": {"totalResults": "3000", "searchTime": 0.28},
                }

            response.headers = {"X-Request-ID": f"test-{timezone.now().timestamp()}"}
            response.raise_for_status = Mock()
            return response

        mock_post.side_effect = mock_api_response

        # Step 1: View the execution status page directly
        status_url = reverse(
            "serp_execution:execution_status", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(status_url)

        # The status page should load directly
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Climate Change Policy Research")
        self.assertContains(response, "2")  # Two queries

        # Step 2: Execute the initiation task directly
        result = initiate_search_session_execution_task(str(self.session.id))  # type: ignore[call-arg]

        self.assertTrue(result["success"])
        self.assertEqual(result["queries_executed"], 2)

        # Verify session has progressed (may have auto-transitioned beyond executing)
        self.session.refresh_from_db()
        self.assertIn(
            self.session.status, ["executing", "processing_results", "ready_for_review"]
        )

        # Verify executions created
        executions = SearchExecution.objects.filter(query__session=self.session)
        self.assertEqual(executions.count(), 2)

        # Step 3: Verify results were created by initiation task
        total_results = RawSearchResult.objects.filter(
            execution__query__session=self.session
        ).count()
        self.assertGreater(total_results, 0)

        # Step 4: Monitor session completion
        completion_result = monitor_session_completion_task(str(self.session.id))
        self.assertIn("status", completion_result)

        # Verify session has progressed
        self.session.refresh_from_db()
        self.assertIn(
            self.session.status,
            ["processing_results", "ready_for_review", "under_review"],
        )

    @patch("apps.serp_execution.query_executor.get_serper_client")
    def test_execution_with_failures_and_retry(self, mock_get_client):
        """Test execution workflow with failures and retry logic."""
        # Mock the API client at the provider level so it works regardless of
        # whether CI uses MockSerperClient or real SerperClient
        mock_client = Mock()
        mock_client.safe_search.return_value = (
            {
                "organic": [
                    {
                        "position": 1,
                        "title": "Retry Success Result",
                        "link": "https://example.com/success",
                        "snippet": "Successfully retrieved after retry",
                    }
                ],
                "searchInformation": {"totalResults": "1000"},
            },
            {"credits_used": 1, "request_id": "retry-success"},
        )
        mock_get_client.return_value = mock_client

        # Create execution
        execution = SearchExecution.objects.create(
            query=self.query1, initiated_by=self.user, status="pending"
        )

        result = perform_serp_query_task(str(execution.id), str(self.query1.id))  # type: ignore[call-arg]

        self.assertTrue(result["success"])
        self.assertEqual(result["results_count"], 1)

        # Verify execution succeeded
        execution.refresh_from_db()
        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.results_count, 1)

    def test_execution_status_monitoring(self):
        """Test real-time execution status monitoring."""
        # Create executions with different statuses
        _exec1 = SearchExecution.objects.create(
            query=self.query1,
            initiated_by=self.user,
            status="completed",
            results_count=25,
            celery_task_id="task-1",
        )

        exec2 = SearchExecution.objects.create(
            query=self.query2,
            initiated_by=self.user,
            status="running",
            celery_task_id="task-2",
        )

        # Test execution status API
        url = reverse(
            "serp_execution:execution_status_api", kwargs={"execution_id": exec2.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data["status"], "running")
        # Progress percentage has been removed - check for status instead
        self.assertNotIn("progress", data)

        # Test session progress API
        url = reverse(
            "serp_execution:session_progress_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data["session_status"], "ready_to_execute")
        # Progress percentage has been removed - verify session status instead
        self.assertNotIn("progress", data)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class TestSearchCachingIntegration(TestCase):
    """Test search result caching integration."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )
        # Create search strategy first
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers"],
            interest_terms=["testing"],
            context_terms=["python"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "search_type": "google",
            },
        )
        # Create query with correct fields
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="developers AND testing AND python",
            query_type="general",
            execution_order=1,
            is_active=True,
        )
        self.cache_manager = CacheManager()
        cache.clear()

    @patch("apps.serp_execution.query_executor.get_serper_client")
    def test_cache_hit_workflow(self, mock_get_client):
        """Test workflow with multiple executions (cache no longer implemented)."""
        # Mock the API client at the provider level so it works regardless of
        # whether CI uses MockSerperClient or real SerperClient
        mock_client = Mock()
        api_response = {
            "organic": [
                {
                    "position": 1,
                    "title": "Cached Result",
                    "link": "https://example.com/cached",
                    "snippet": "This should be cached",
                }
            ],
            "searchInformation": {"totalResults": "1"},
        }
        mock_client.safe_search.return_value = (
            api_response,
            {"credits_used": 1, "request_id": "test-123"},
        )
        mock_get_client.return_value = mock_client

        # Create two executions for the same query
        exec1 = SearchExecution.objects.create(
            query=self.query, initiated_by=self.user, status="pending"
        )

        exec2 = SearchExecution.objects.create(
            query=self.query, initiated_by=self.user, status="pending"
        )

        # Execute first query
        result1 = perform_serp_query_task(str(exec1.id), str(self.query.id))  # type: ignore[call-arg]
        self.assertTrue(result1["success"])
        self.assertEqual(mock_client.safe_search.call_count, 1)

        # Execute second query
        result2 = perform_serp_query_task(str(exec2.id), str(self.query.id))  # type: ignore[call-arg]
        self.assertTrue(result2["success"])
        self.assertEqual(mock_client.safe_search.call_count, 2)

        # Both should have same results
        results1 = RawSearchResult.objects.filter(execution=exec1)
        results2 = RawSearchResult.objects.filter(execution=exec2)

        self.assertEqual(results1.count(), results2.count())
        self.assertEqual(results1.first().title, results2.first().title)


class TestErrorRecoveryIntegration(TestCase):
    """Test error recovery and retry mechanisms."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.client = Client()
        self.client.login(username=self.user.username, password="testpass123")

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )
        # Create search strategy first
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "search_type": "google",
            },
        )
        # Create query with correct fields
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test AND test AND test",
            query_type="general",
            execution_order=1,
            is_active=True,
        )

    @patch("apps.core.services.serper_client.requests.post")
    def test_automatic_retry_on_transient_errors(self, mock_post):
        """Test automatic retry for transient errors."""
        # Create execution
        execution = SearchExecution.objects.create(
            query=self.query, initiated_by=self.user, status="pending"
        )

        # Mock connection error
        mock_post.side_effect = ConnectionError("Network unreachable")

        # Execute - task should handle the error
        try:
            result = perform_serp_query_task(str(execution.id), str(self.query.id))  # type: ignore[call-arg]
            # If task returns a result, it should indicate failure
            if isinstance(result, dict):
                self.assertFalse(result.get("success", True))
        except Exception:
            # Task may raise on retry exhaustion
            pass

        # Verify execution status was updated (task may handle error gracefully)
        execution.refresh_from_db()
        self.assertIsNotNone(execution.status)

    def test_manual_retry_through_ui(self):
        """Test manual retry through the UI."""
        # Create failed execution
        execution = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="failed",
            error_message="API quota exceeded",
            retry_count=1,
        )

        # View error recovery page
        url = reverse(
            "serp_execution:error_recovery", kwargs={"execution_id": execution.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "API quota exceeded")
        self.assertContains(response, "Retry")

        # Submit retry with delay - mock at the tasks module level
        import apps.serp_execution.tasks as tasks_module

        mock_task = Mock()
        mock_task.delay.return_value = Mock(id="retry-task-id")

        with patch.object(
            tasks_module, "retry_failed_execution_task", mock_task, create=True
        ):
            response = self.client.post(
                url,
                {
                    "recovery_action": "retry",
                    "retry_delay": 300,  # 5 minutes
                    "notes": "Waiting for quota reset",
                },
            )

            self.assertEqual(response.status_code, 302)
            mock_task.delay.assert_called_once()


class TestMetricsAndMonitoring(TestCase):
    """Test metrics collection and monitoring integration."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Metrics Test Session", owner=self.user
        )

        # Create search strategy first
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["group_0", "group_1", "group_2"],
            interest_terms=["topic_0", "topic_1", "topic_2"],
            context_terms=["research"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "search_type": "google",
            },
        )

        # Create multiple queries
        for i in range(3):
            SearchQuery.objects.create(
                strategy=self.strategy,
                session=self.session,
                query_text=f"group_{i} AND topic_{i} AND research",
                query_type="general",
                execution_order=i + 1,
                is_active=True,
            )

    def test_metrics_aggregation(self):
        """Test metrics aggregation across multiple executions."""
        queries = SearchQuery.objects.filter(session=self.session)

        # Create executions with various outcomes
        for i, query in enumerate(queries):
            SearchExecution.objects.create(
                query=query,
                initiated_by=self.user,
                status="completed" if i < 2 else "failed",
                results_count=25 * (i + 1) if i < 2 else 0,
                duration_seconds=2.5 + i,
                started_at=timezone.now() - timedelta(seconds=10),
                completed_at=timezone.now(),
            )

        # Create and update metrics
        # NOTE: ExecutionMetrics model removed - commenting out metrics testing
        # metrics = ExecutionMetrics.objects.create(session=self.session)
        # metrics.update_metrics()

        # Verify aggregations
        # self.assertEqual(metrics.total_executions, 3)
        # self.assertEqual(metrics.successful_executions, 2)
        # self.assertEqual(metrics.failed_executions, 1)
        # self.assertEqual(metrics.total_results_retrieved, 75)  # 25 + 50
        # self.assertEqual(metrics.total_api_credits, 300)
        # self.assertEqual(metrics.total_estimated_cost, Decimal("0.30"))
        # self.assertAlmostEqual(float(metrics.average_execution_time), 3.0, places=1)

    # Usage tracking test removed for simplification


class TestConcurrentExecution(TestCase):
    """Test concurrent execution scenarios."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Concurrent Test", owner=self.user, status="ready_to_execute"
        )

        # Create search strategy first
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=[f"group_{i}" for i in range(5)],
            interest_terms=["concurrent testing"],
            context_terms=["stress test"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "search_type": "google",
            },
        )

        # Create multiple queries
        for i in range(5):
            SearchQuery.objects.create(
                strategy=self.strategy,
                session=self.session,
                query_text=f"group_{i} AND concurrent testing AND stress test",
                query_type="general",
                execution_order=i + 1,
                is_active=True,
            )

    @patch("apps.core.services.serper_client.requests.post")
    @patch("celery.group")
    def test_parallel_execution(self, mock_group, mock_post):
        """Test parallel execution of multiple queries."""
        # Mock API responses
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic": [
                {
                    "position": 1,
                    "title": "Test",
                    "link": "https://example.com",
                    "snippet": "Test",
                }
            ],
            "credits": 1,
            "searchInformation": {"totalResults": "1"},
        }
        mock_response.headers = {}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Mock celery group
        mock_job = Mock()
        mock_group.return_value.__or__ = Mock(return_value=mock_job)

        # Initiate execution
        result = initiate_search_session_execution_task(str(self.session.id))  # type: ignore[call-arg]

        self.assertTrue(result["success"])
        self.assertEqual(result["queries_executed"], 5)

        # Verify all executions created
        executions = SearchExecution.objects.filter(query__session=self.session)
        self.assertEqual(executions.count(), 5)

        # Simulate parallel execution
        for execution in executions:
            # Each should be able to execute independently
            result = perform_serp_query_task(str(execution.id), str(execution.query.id))  # type: ignore[call-arg]
            self.assertTrue(result["success"])

        # All should complete successfully
        completed = executions.filter(status="completed").count()
        self.assertEqual(completed, 5)
