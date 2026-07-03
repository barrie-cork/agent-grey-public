"""
Tests for query-level progress tracking API endpoint.
"""

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestSessionQueryProgressAPI(TestCase):
    """Test the session_query_progress_api endpoint."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Search Session", owner=self.user, status="executing"
        )

        # Create search strategy
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers"],
            interest_terms=["testing"],
            context_terms=["python"],
        )

        # Create test queries
        self.query1 = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="developers AND testing",
            query_type="general",
            is_active=True,
        )

        self.query2 = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="python testing practices",
            query_type="general",
            is_active=True,
        )

        # Create executions with different states
        self.execution1 = SearchExecution.objects.create(
            query=self.query1,
            initiated_by=self.user,
            status="completed",
            current_step="Completed",
            processing_phase="finalizing",
            api_result_count=25,
            started_at=timezone.now() - timezone.timedelta(minutes=10),
            completed_at=timezone.now() - timezone.timedelta(minutes=5),
            duration_seconds=300,
        )

        self.execution2 = SearchExecution.objects.create(
            query=self.query2,
            initiated_by=self.user,
            status="running",
            current_step="Parsing results",
            processing_phase="parsing",
            api_result_count=10,
            started_at=timezone.now() - timezone.timedelta(minutes=2),
        )

    def test_api_requires_authentication(self):
        """Test that API requires authentication."""
        self.client.logout()
        url = reverse(
            "serp_execution:session_query_progress_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_api_validates_ownership(self):
        """Test that API validates session ownership."""
        other_user = create_test_user(username_prefix="otheruser")
        self.client.login(username=other_user.username, password="testpass123")

        url = reverse(
            "serp_execution:session_query_progress_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        data = json.loads(response.content)
        self.assertEqual(data["error"], "Permission denied")

    def test_api_returns_404_for_nonexistent_session(self):
        """Test that API returns 404 for non-existent session."""
        fake_session_id = uuid.uuid4()
        url = reverse(
            "serp_execution:session_query_progress_api",
            kwargs={"session_id": fake_session_id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        data = json.loads(response.content)
        self.assertEqual(data["error"], "Session not found")

    def test_api_returns_query_progress_data(self):
        """Test that API returns correct query progress data."""
        url = reverse(
            "serp_execution:session_query_progress_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)

        # Check basic structure
        self.assertIn("session_id", data)
        self.assertIn("session_status", data)
        self.assertIn("total_queries", data)
        self.assertIn("completed_queries", data)
        self.assertIn("current_query", data)
        self.assertIn("queries", data)
        # Verify no progress percentage fields
        self.assertNotIn("overall_progress", data)
        self.assertNotIn("progress_percentage", data)

        # Check values
        self.assertEqual(data["session_id"], str(self.session.id))
        self.assertEqual(data["session_status"], "executing")
        self.assertEqual(data["total_queries"], 2)
        self.assertEqual(data["completed_queries"], 1)

        # Check queries array
        self.assertEqual(len(data["queries"]), 2)

        # Find the running query
        running_query = next(
            (q for q in data["queries"] if q["status"] == "running"), None
        )
        self.assertIsNotNone(running_query)
        assert running_query is not None
        self.assertEqual(running_query["query_text"], "python testing practices")
        self.assertEqual(running_query["current_step"], "Parsing results")
        # Verify no progress percentage
        self.assertNotIn("progress_percentage", running_query)

        # Find the completed query
        completed_query = next(
            (q for q in data["queries"] if q["status"] == "completed"), None
        )
        self.assertIsNotNone(completed_query)
        assert completed_query is not None
        self.assertEqual(completed_query["query_text"], "developers AND testing")
        self.assertEqual(completed_query["results_count"], 25)
        # Verify no progress percentage
        self.assertNotIn("progress_percentage", completed_query)

    def test_api_identifies_current_query(self):
        """Test that API correctly identifies the currently executing query."""
        url = reverse(
            "serp_execution:session_query_progress_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)

        # Check current query
        self.assertIsNotNone(data["current_query"])
        self.assertEqual(data["current_query"]["status"], "running")
        self.assertEqual(data["current_query"]["execution_id"], str(self.execution2.id))

    def test_api_handles_no_executions(self):
        """Test that API handles sessions with no executions."""
        # Create a new session without executions
        empty_session = SearchSession.objects.create(
            title="Empty Session", owner=self.user, status="ready_to_execute"
        )

        url = reverse(
            "serp_execution:session_query_progress_api",
            kwargs={"session_id": empty_session.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEqual(data["total_queries"], 0)
        self.assertEqual(data["completed_queries"], 0)
        self.assertIsNone(data["current_query"])
        self.assertEqual(len(data["queries"]), 0)
        # Verify no progress percentage
        self.assertNotIn("overall_progress", data)

    def test_api_handles_all_failed_executions(self):
        """Test that API handles sessions where all executions failed."""
        # Update all executions to failed
        self.execution1.status = "failed"
        self.execution1.error_message = "API rate limit exceeded"
        self.execution1.save()

        self.execution2.status = "failed"
        self.execution2.error_message = "Network error"
        self.execution2.save()

        url = reverse(
            "serp_execution:session_query_progress_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)

        self.assertEqual(data["completed_queries"], 0)
        self.assertIsNone(data["current_query"])

        # Check that error messages are included
        for query in data["queries"]:
            self.assertEqual(query["status"], "failed")
            self.assertIn("error_message", query)
            self.assertTrue(query["error_message"])

    def test_api_includes_timestamp(self):
        """Test that API response includes a timestamp."""
        url = reverse(
            "serp_execution:session_query_progress_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)

        self.assertIn("timestamp", data)
        # Verify timestamp is valid ISO format
        from datetime import datetime

        datetime.fromisoformat(data["timestamp"])

    def test_api_performance_with_many_queries(self):
        """Test API performance with many queries."""
        # Create 20 more queries and executions
        for i in range(20):
            query = SearchQuery.objects.create(
                session=self.session,
                strategy=self.strategy,
                query_text=f"test query {i}",
                query_type="general",
                is_active=True,
            )
            SearchExecution.objects.create(
                query=query,
                initiated_by=self.user,
                status="completed" if i % 2 == 0 else "pending",
            )

        url = reverse(
            "serp_execution:session_query_progress_api",
            kwargs={"session_id": self.session.id},
        )

        # Measure response time
        import time

        start_time = time.time()
        response = self.client.get(url)
        response_time = time.time() - start_time

        self.assertEqual(response.status_code, 200)
        # Response should be fast even with many queries
        self.assertLess(response_time, 1.0)  # Less than 1 second

        data = json.loads(response.content)
        self.assertEqual(data["total_queries"], 22)  # 2 original + 20 new
