"""
Tests for SERP execution views.

Tests for view classes and AJAX endpoints including SearchExecutionStatusView,
ErrorRecoveryView, and API endpoints.
"""

import json
import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestSearchExecutionStatusView(TestCase):
    """Test the search execution status view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Search Session", owner=self.user, status="executing"
        )

        # Create test strategy
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers"],
            interest_terms=["testing", "agile"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "file_types": [],
                "search_type": "google",
            },
        )

        # Create test query
        self.query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="developers testing agile",
            query_type="general",
            is_active=True,
        )

        # Create test execution
        self.execution = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            results_count=50,
        )

    def test_status_view_get(self):
        """Test GET request to status view."""
        url = reverse(
            "serp_execution:execution_status", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search Execution")  # Page title
        self.assertContains(response, self.session.title)

    def test_status_view_with_statistics(self):
        """Test status view with detailed statistics."""
        # Create additional executions to test statistics
        for i in range(2):
            _execution = SearchExecution.objects.create(
                query=self.query,
                initiated_by=self.user,
                status="completed" if i == 0 else "failed",
                results_count=50 if i == 0 else 0,
                error_message="" if i == 0 else "Rate limit exceeded",
                started_at=timezone.now() - timedelta(seconds=5),
                completed_at=timezone.now() - timedelta(seconds=3),
                duration_seconds=2.0,
            )

        # Update session status
        self.session.status = "ready_for_review"
        self.session.save()

        url = reverse(
            "serp_execution:execution_status", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        context = response.context
        # We should have 3 executions total (1 from setUp + 2 created here)
        self.assertEqual(context["stats"]["total_executions"], 3)
        self.assertEqual(context["stats"]["successful_executions"], 2)
        self.assertEqual(context["stats"]["failed_executions"], 1)
        self.assertEqual(context["stats"]["total_results"], 100)  # 50 + 50 + 0
        self.assertTrue(context["failed_executions"])
        self.assertFalse(context["has_running"])  # No running executions
        self.assertEqual(context["refresh_interval"], 0)  # No auto-refresh

    def test_status_view_with_running_executions(self):
        """Test status view with running executions."""
        # Create running execution
        SearchExecution.objects.create(
            query=self.query, initiated_by=self.user, status="running"
        )

        url = reverse(
            "serp_execution:execution_status", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        context = response.context
        self.assertTrue(context["has_running"])
        self.assertEqual(context["refresh_interval"], 5000)  # Auto-refresh enabled

    def test_status_view_ordering(self):
        """Test execution ordering in status view."""
        # Create multiple executions with different timestamps
        for i in range(3):
            SearchExecution.objects.create(
                query=self.query,
                initiated_by=self.user,
                status="completed",
                created_at=timezone.now() - timedelta(hours=i),
            )

        url = reverse(
            "serp_execution:execution_status", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        executions = response.context["executions"]
        # Should be ordered by created_at descending (newest first)
        for i in range(len(executions) - 1):
            self.assertGreater(executions[i].created_at, executions[i + 1].created_at)

    def test_status_view_shows_executions_with_strategy(self):
        """Test that executions are properly shown when query has a strategy.

        Verifies that execution statistics are correctly displayed
        for sessions with active queries and completed executions.
        """
        # Update the existing strategy with test data
        self.strategy.population_terms = ["air"]
        self.strategy.interest_terms = ["water"]
        self.strategy.context_terms = []
        self.strategy.save()

        # Create a completed execution
        _execution = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="completed",
            results_count=49,
            started_at=timezone.now() - timedelta(seconds=2),
            completed_at=timezone.now() - timedelta(seconds=0.5),
            duration_seconds=1.5,
        )

        # Update session status to processing_results
        self.session.status = "processing_results"
        self.session.save()

        url = reverse(
            "serp_execution:execution_status", kwargs={"session_id": self.session.id}
        )
        response = self.client.get(url)

        # Should show the execution count
        context = response.context
        self.assertGreater(context["stats"]["total_executions"], 0)
        self.assertEqual(
            context["stats"]["successful_executions"], 2
        )  # Including setUp execution
        self.assertEqual(context["stats"]["total_results"], 99)  # 50 from setUp + 49


class TestErrorRecoveryView(TestCase):
    """Test the error recovery view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Search Session", owner=self.user, status="executing"
        )

        # Create test strategy
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers"],
            interest_terms=["testing", "agile"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "file_types": [],
                "search_type": "google",
            },
        )

        # Create test query
        self.query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="developers testing agile",
            query_type="general",
            is_active=True,
        )

        # Create failed execution
        self.execution = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="failed",
            error_message="Rate limit exceeded",
            retry_count=0,
        )

    def test_error_recovery_view_get(self):
        """Test GET request to error recovery view."""
        url = reverse(
            "serp_execution:error_recovery", kwargs={"execution_id": self.execution.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Error Recovery")
        self.assertContains(response, "Rate limit exceeded")
        self.assertContains(response, "Retry Execution")

    def test_error_recovery_view_validates_retry_eligibility(self):
        """Test that view validates retry eligibility."""
        self.execution.retry_count = 3  # Max retries reached
        self.execution.save()

        url = reverse(
            "serp_execution:error_recovery", kwargs={"execution_id": self.execution.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(str(self.session.id), response.url)

    @patch("apps.serp_execution.tasks.retry_failed_execution_task", create=True)
    def test_error_recovery_view_post_retry(self, mock_task):
        """Test POST request to retry execution."""
        mock_task.delay.return_value = Mock(id="test-task-id")

        url = reverse(
            "serp_execution:error_recovery", kwargs={"execution_id": self.execution.id}
        )
        data = {
            "recovery_action": "retry",
            "retry_delay": 60,
            "notes": "Retrying after rate limit",
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        self.assertIn(str(self.session.id), response.url)
        mock_task.delay.assert_called_once()

        # Check success message
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(len(messages_list) > 0)

    def test_error_recovery_view_post_skip(self):
        """Test POST request to skip execution."""
        url = reverse(
            "serp_execution:error_recovery", kwargs={"execution_id": self.execution.id}
        )
        data = {"recovery_action": "skip", "notes": "Skipping problematic query"}

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)

        # Verify execution marked as skipped
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, "skipped")

    def test_error_recovery_view_post_manual(self):
        """Test POST request for manual intervention."""
        url = reverse(
            "serp_execution:error_recovery", kwargs={"execution_id": self.execution.id}
        )
        data = {"recovery_action": "manual", "notes": "Need to check API credentials"}

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertIn("manual", str(messages[0]))

        # Verify execution status remains failed with manual intervention message
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, "failed")
        self.assertIn("Manual intervention required", self.execution.error_message)


class TestAjaxAPIViews(TestCase):
    """Test AJAX API views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.client.login(username=self.user.username, password="testpass123")

        # Create test session
        self.session = SearchSession.objects.create(
            title="Test Search Session", owner=self.user, status="executing"
        )

        # Create test strategy
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers"],
            interest_terms=["testing", "agile"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "file_types": [],
                "search_type": "google",
            },
        )

        # Create test query
        self.query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="developers testing agile",
            query_type="general",
            is_active=True,
        )

        # Create test execution
        self.execution = SearchExecution.objects.create(
            query=self.query, initiated_by=self.user, status="running", results_count=25
        )

    def test_execution_status_api(self):
        """Test execution status API endpoint."""
        url = reverse(
            "serp_execution:execution_status_api",
            kwargs={"execution_id": self.execution.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data["id"], str(self.execution.id))
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["results_count"], 25)
        self.assertNotIn("progress", data)

    def test_session_progress_api(self):
        """Test session progress API endpoint."""
        url = reverse(
            "serp_execution:session_progress_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data["session_id"], str(self.session.id))
        self.assertEqual(data["session_status"], "executing")
        self.assertIn("status", data)
        self.assertIn("current_step", data)

    @patch("apps.serp_execution.tasks.retry_failed_execution_task", create=True)
    def test_retry_execution_api(self, mock_task):
        """Test retry execution API endpoint."""
        # Update execution to failed status
        self.execution.status = "failed"
        self.execution.error_message = "Test error"
        self.execution.save()

        # Mock task
        mock_task.delay.return_value = Mock(id="test-task-id")

        url = reverse(
            "serp_execution:retry_execution_api",
            kwargs={"execution_id": self.execution.id},
        )
        response = self.client.post(url, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # Check response data (RecoveryAPIService format)
        self.assertTrue(data["success"])
        self.assertEqual(data["execution_id"], str(self.execution.id))
        self.assertEqual(data["new_status"], "pending")

        # Verify execution updated
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, "pending")
        self.assertEqual(self.execution.retry_count, 1)

    def test_retry_execution_api_not_recommended(self):
        """Test retry API when retry is not recommended."""
        # Set execution to failed with max retries
        self.execution.status = "failed"
        self.execution.retry_count = 3  # Max retries reached
        self.execution.save()

        url = reverse(
            "serp_execution:retry_execution_api",
            kwargs={"execution_id": self.execution.id},
        )
        response = self.client.post(url, content_type="application/json")

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)

        # Check error response - based on RecoveryAPIService implementation
        self.assertIn("error", data)
        self.assertIn("cannot be retried", data["error"].lower())

    def test_api_authentication_required(self):
        """Test that API endpoints require authentication."""
        self.client.logout()

        endpoints = [
            (
                "serp_execution:execution_status_api",
                {"execution_id": self.execution.id},
            ),
            ("serp_execution:session_progress_api", {"session_id": self.session.id}),
            ("serp_execution:retry_execution_api", {"execution_id": self.execution.id}),
        ]

        for url_name, kwargs in endpoints:
            url = reverse(url_name, kwargs=kwargs)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_api_ownership_validation(self):
        """Test that API endpoints validate ownership."""
        # Create another user and their execution
        other_user = create_test_user(username_prefix="otheruser")
        other_session = SearchSession.objects.create(
            title="Other Session", owner=other_user
        )
        # Create strategy first (required for SearchQuery)
        other_strategy = SearchStrategy.objects.create(
            session=other_session,
            user=other_user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
        )
        other_query = SearchQuery.objects.create(
            session=other_session,
            strategy=other_strategy,
            query_text="test query",
            query_type="general",
        )
        other_execution = SearchExecution.objects.create(
            query=other_query, initiated_by=other_user
        )

        # Try to access other user's data
        url = reverse(
            "serp_execution:execution_status_api",
            kwargs={"execution_id": other_execution.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)
        data = json.loads(response.content)
        self.assertIn("Permission denied", data["error"])

    def test_api_error_handling(self):
        """Test API error handling."""
        # Test with non-existent execution
        url = reverse(
            "serp_execution:execution_status_api",
            kwargs={"execution_id": str(uuid.uuid4())},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.content)
        self.assertIn("not found", data["error"])

    def test_session_progress_api_calculations(self):
        """Test session progress calculations."""
        url = reverse(
            "serp_execution:session_progress_api",
            kwargs={"session_id": self.session.id},
        )
        response = self.client.get(url)

        data = json.loads(response.content)
        # API returns simplified session status
        self.assertEqual(data["session_id"], str(self.session.id))
        self.assertEqual(data["session_status"], "executing")
        self.assertNotIn("progress", data)  # No percentage field
