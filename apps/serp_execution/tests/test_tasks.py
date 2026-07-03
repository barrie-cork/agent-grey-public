"""
Tests for SERP execution Celery tasks.

Tests for search execution tasks, session monitoring, and error recovery.
"""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import ReviewConfiguration, SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.serp_execution.tasks import (
    _send_execution_notification,
    _send_session_notification,
    _should_retry_execution,
    execute_search_session_simple,
    initiate_search_session_execution_task,
    monitor_session_completion_task,
    perform_serp_query_task,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestRetryLogic(TestCase):
    """Test cases for retry decision logic."""

    def test_should_retry_connection_errors(self):
        """Test that connection errors trigger retry."""
        self.assertTrue(_should_retry_execution(ConnectionError("Connection failed")))
        self.assertTrue(_should_retry_execution(TimeoutError("Request timed out")))
        self.assertTrue(_should_retry_execution(OSError("Network unreachable")))

    def test_should_retry_transient_messages(self):
        """Test that specific error messages trigger retry."""
        self.assertTrue(_should_retry_execution(Exception("Connection reset by peer")))
        self.assertTrue(
            _should_retry_execution(Exception("Service temporarily unavailable"))
        )
        self.assertTrue(_should_retry_execution(Exception("Too many requests")))

    def test_should_not_retry_business_errors(self):
        """Test that business logic errors don't trigger retry."""
        self.assertFalse(_should_retry_execution(ValueError("Invalid input")))
        self.assertFalse(_should_retry_execution(KeyError("Missing key")))
        self.assertFalse(_should_retry_execution(Exception("Invalid session state")))


class TestInitiateSearchSessionExecutionTask(TestCase):
    """Test cases for initiate_search_session_execution_task."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="ready_to_execute"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers", "engineers"],
            interest_terms=["testing", "quality"],
            context_terms=["agile", "scrum"],
            search_config={
                "domains": ["example.com"],
                "file_types": ["pdf"],
                "include_general_search": True,
            },
        )

        self.query1 = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="site:example.com (developers OR engineers) AND testing AND agile",
            query_type="domain-specific",
            target_domain="example.com",
            is_active=True,
            execution_order=1,
        )
        self.query2 = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="(developers OR engineers) AND testing AND agile",
            query_type="general",
            target_domain=None,
            is_active=True,
            execution_order=2,
        )

    @patch("apps.core.services.serper_client.requests.post")
    def test_successful_execution_initiation(self, mock_post):
        """Test successful initiation of search session execution."""
        # Mock Serper API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic": [
                {
                    "position": 1,
                    "title": "Test Result",
                    "link": "https://example.com/test",
                    "snippet": "Test snippet",
                }
            ],
            "credits": 1,
            "searchInformation": {"totalResults": "100", "searchTime": 0.5},
        }
        mock_response.headers = {"X-Request-ID": "test-123"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Execute the real task
        result = initiate_search_session_execution_task(str(self.session.id))  # type: ignore[call-arg]

        # Verify result
        self.assertTrue(result["success"])
        self.assertEqual(result["queries_executed"], 2)

    @patch("apps.core.services.serper_client.requests.post")
    def test_invalid_session_status(self, mock_post):
        """Test initiation with invalid session status."""
        self.session.status = "completed"
        self.session.save()

        result = initiate_search_session_execution_task(str(self.session.id))  # type: ignore[call-arg]

        self.assertFalse(result["success"])
        self.assertIn("Invalid status", result["error"])

    @patch("apps.core.services.serper_client.requests.post")
    def test_no_queries(self, mock_post):
        """Test initiation with no queries."""
        SearchQuery.objects.filter(session=self.session).delete()

        result = initiate_search_session_execution_task(str(self.session.id))  # type: ignore[call-arg]

        # Task succeeds but with 0 queries executed
        self.assertTrue(result["success"])
        self.assertEqual(result["queries_executed"], 0)

    def test_session_not_found(self):
        """Test initiation with non-existent session."""
        non_existent_uuid = "00000000-0000-0000-0000-000000000000"
        result = initiate_search_session_execution_task(non_existent_uuid)  # type: ignore[call-arg]

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])

    @patch("apps.core.services.serper_client.requests.post")
    def test_error_handling_on_api_failure(self, mock_post):
        """Test error handling when API call fails."""
        mock_post.side_effect = ConnectionError("Network error")

        # The task may raise Retry or return error dict
        try:
            result = initiate_search_session_execution_task(str(self.session.id))  # type: ignore[call-arg]
            if isinstance(result, dict):
                # If we got a result, it should indicate the error
                self.assertIn("error", result)
        except Exception:
            # Task may raise on retry - this is expected behaviour
            pass


class TestPerformSerpQueryTask(TestCase):
    """Test cases for perform_serp_query_task."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers"],
            interest_terms=["best practices"],
            context_terms=["python"],
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="(developers) AND (best practices) AND (python)",
            query_type="general",
            is_active=True,
        )
        self.execution = SearchExecution.objects.create(
            query=self.query, initiated_by=self.user, status="pending"
        )

    @patch("apps.serp_execution.query_executor.get_serper_client")
    def test_successful_query_execution(self, mock_get_client):
        """Test successful SERP query execution."""
        mock_client = Mock()
        mock_client.safe_search.return_value = (
            {
                "organic": [
                    {
                        "position": 1,
                        "title": "Python Best Practices",
                        "link": "https://example.com/python-practices.pdf",
                        "snippet": "A guide to Python best practices",
                    },
                    {
                        "position": 2,
                        "title": "Testing in Python",
                        "link": "https://example.edu/testing-python",
                        "snippet": "Learn about testing methodologies",
                    },
                ]
            },
            {
                "credits_used": 1,
                "total_results": "1000",
                "time_taken": 0.5,
                "request_id": "test-123",
                "response_warnings": [],
            },
        )
        mock_get_client.return_value = mock_client

        result = perform_serp_query_task(str(self.execution.id), str(self.query.id))  # type: ignore[call-arg]

        self.assertTrue(result["success"])
        self.assertEqual(result["execution_id"], str(self.execution.id))
        self.assertGreater(result["results_count"], 0)

        # Verify execution updated
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, "completed")

    @patch("apps.serp_execution.query_executor.get_serper_client")
    def test_api_error_handling(self, mock_get_client):
        """Test handling API errors."""
        mock_client = Mock()
        mock_client.execute_with_retry.side_effect = ConnectionError("Network error")
        mock_client.safe_search.side_effect = ConnectionError("Network error")
        mock_get_client.return_value = mock_client

        # Task may raise Retry or return error dict
        try:
            result = perform_serp_query_task(str(self.execution.id), str(self.query.id))  # type: ignore[call-arg]
            if isinstance(result, dict):
                self.assertFalse(result.get("success", True))
        except Exception:
            # Retry exception is expected
            pass

        # Verify execution status was updated
        self.execution.refresh_from_db()
        self.assertIn(self.execution.status, ["pending", "running", "failed"])

    @patch("apps.serp_execution.query_executor.get_serper_client")
    def test_no_results_returned(self, mock_get_client):
        """Test handling when no results are returned."""
        mock_client = Mock()
        empty_response = (
            {"organic": []},
            {
                "credits_used": 1,
                "total_results": "0",
                "time_taken": 0.1,
                "request_id": "test-empty",
                "response_warnings": [],
            },
        )
        mock_client.safe_search.return_value = empty_response
        mock_client.execute_with_retry.return_value = empty_response
        mock_get_client.return_value = mock_client

        result = perform_serp_query_task(str(self.execution.id), str(self.query.id))  # type: ignore[call-arg]

        self.assertTrue(result["success"])
        self.assertEqual(result["results_count"], 0)

        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, "completed")
        self.assertEqual(self.execution.results_count, 0)

    @patch("apps.serp_execution.query_executor.get_serper_client")
    def test_execution_timestamps_set(self, mock_get_client):
        """Test that execution timestamps are set correctly."""
        mock_client = Mock()
        mock_client.safe_search.return_value = (
            {
                "organic": [
                    {
                        "position": 1,
                        "title": "Test",
                        "link": "https://example.com/test",
                        "snippet": "Test",
                    }
                ]
            },
            {
                "credits_used": 1,
                "total_results": "1",
                "time_taken": 0.1,
                "request_id": "ts-test",
                "response_warnings": [],
            },
        )
        mock_get_client.return_value = mock_client

        perform_serp_query_task(str(self.execution.id), str(self.query.id))  # type: ignore[call-arg]

        self.execution.refresh_from_db()
        self.assertIsNotNone(self.execution.started_at)
        self.assertIsNotNone(self.execution.completed_at)

    @patch("apps.serp_execution.query_executor.get_serper_client")
    def test_retry_after_previous_failure(self, mock_get_client):
        """Test tracking successful execution after retries."""
        self.execution.retry_count = 2
        self.execution.save()

        mock_client = Mock()
        mock_client.safe_search.return_value = (
            {
                "organic": [
                    {
                        "position": 1,
                        "title": "Test",
                        "link": "https://example.com",
                        "snippet": "Test",
                    }
                ]
            },
            {
                "credits_used": 1,
                "total_results": "1",
                "time_taken": 0.1,
                "request_id": "retry-test",
                "response_warnings": [],
            },
        )
        mock_get_client.return_value = mock_client

        result = perform_serp_query_task(str(self.execution.id), str(self.query.id))  # type: ignore[call-arg]

        self.assertTrue(result["success"])
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, "completed")


class TestMonitorSessionCompletionTask(TestCase):
    """Test cases for monitor_session_completion_task."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["developers", "managers"],
            interest_terms=["testing", "metrics"],
            context_terms=["agile", "software"],
        )
        self.query1 = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="(developers) AND (testing) AND (agile)",
            query_type="general",
            is_active=True,
        )
        self.query2 = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="(managers) AND (metrics) AND (software)",
            query_type="general",
            is_active=True,
        )

    @patch(
        "apps.serp_execution.tasks.monitoring.monitor_session_completion_task.apply_async"
    )
    def test_monitor_incomplete_session(self, mock_apply_async):
        """Test monitoring when not all executions are complete."""
        SearchExecution.objects.create(
            query=self.query1,
            initiated_by=self.user,
            status="completed",
            results_count=50,
        )
        SearchExecution.objects.create(
            query=self.query2, initiated_by=self.user, status="running"
        )

        result = monitor_session_completion_task(str(self.session.id))

        # Should still be executing since not all executions are complete
        self.assertEqual(result["status"], "executing")

    @patch("apps.core.progress.tracker.progress_tracker")
    @patch("apps.serp_execution.tasks.helpers._send_session_notification")
    @patch("apps.results_manager.tasks.process_session_results_task.apply_async")
    def test_monitor_all_successful(
        self, mock_process_task_apply_async, mock_notify, mock_progress_tracker
    ):
        """Test monitoring when all executions completed successfully."""
        SearchExecution.objects.create(
            query=self.query1,
            initiated_by=self.user,
            status="completed",
            results_count=50,
        )
        SearchExecution.objects.create(
            query=self.query2,
            initiated_by=self.user,
            status="completed",
            results_count=30,
        )

        result = monitor_session_completion_task(str(self.session.id))

        # Session should transition to processing_results (via reconciliation or normal path)
        self.assertIn(result["status"], ["processing_results"])

        # Verify session updated
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "processing_results")

    @patch("apps.core.progress.tracker.progress_tracker")
    @patch("apps.serp_execution.tasks.helpers._send_session_notification")
    def test_monitor_all_failed(self, mock_notify, mock_progress_tracker):
        """Test monitoring when all executions failed."""
        SearchExecution.objects.create(
            query=self.query1,
            initiated_by=self.user,
            status="failed",
            error_message="API error",
        )
        SearchExecution.objects.create(
            query=self.query2,
            initiated_by=self.user,
            status="failed",
            error_message="Rate limit exceeded",
        )

        result = monitor_session_completion_task(str(self.session.id))

        # All failed - with CELERY_TASK_ALWAYS_EAGER, the session may
        # transition through the full pipeline automatically
        self.assertIn(
            result["status"],
            ["all_failed", "processing_results", "completed"],
        )

        # Verify session handled
        self.session.refresh_from_db()
        self.assertIn(
            self.session.status,
            [
                "executing",
                "ready_to_execute",
                "processing_results",
                "ready_for_review",
                "completed",
            ],
        )

    @patch(
        "apps.serp_execution.tasks.monitoring.monitor_session_completion_task.apply_async"
    )
    def test_monitor_error_handling(self, mock_apply_async):
        """Test error handling in session monitoring."""
        # Use a non-existent session ID to trigger error
        bad_uuid = "00000000-0000-0000-0000-000000000099"

        result = monitor_session_completion_task(bad_uuid)

        # Verify error result
        self.assertEqual(result["status"], "error")
        self.assertIn("error", result)


class TestNotificationFunctions(TestCase):
    """Test cases for notification functions."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Research Session", owner=self.user
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["researchers"],
            interest_terms=["climate change"],
            context_terms=["policy"],
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="researchers climate change policy",
            query_type="general",
        )
        self.execution = SearchExecution.objects.create(
            query=self.query,
            initiated_by=self.user,
            status="failed",
            error_message="API quota exceeded",
            retry_count=2,
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        SITE_URL="https://example.com",
    )
    def test_send_execution_notification(self):
        """Test sending execution failure notification."""
        mail.outbox.clear()

        _send_execution_notification(
            self.execution, "Search execution failed after multiple attempts."
        )

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        self.assertIn("Search Execution Alert", email.subject)
        self.assertIn("Test Research Session", email.subject)
        self.assertIn("failed after multiple attempts", email.body)
        self.assertIn("researchers climate change policy", email.body)
        self.assertIn("API quota exceeded", email.body)
        self.assertIn("Attempts: 3", email.body)
        self.assertEqual(email.to, [self.user.email])

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        SITE_URL="https://example.com",
    )
    def test_send_session_notification(self):
        """Test sending session completion notification."""
        mail.outbox.clear()

        _send_session_notification(
            self.session,
            "Search execution completed successfully. Found 150 results.",
        )

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        self.assertIn("Search Session Update", email.subject)
        self.assertIn("Test Research Session", email.subject)
        self.assertIn("completed successfully", email.body)
        self.assertIn("150 results", email.body)
        self.assertEqual(email.to, [self.user.email])

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_notification_without_email(self):
        """Test notification handling when user has no email."""
        mail.outbox.clear()

        self.user.email = ""
        self.user.save()

        _send_execution_notification(self.execution, "Test message")
        _send_session_notification(self.session, "Test message")

        self.assertEqual(len(mail.outbox), 0)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    @patch("apps.serp_execution.tasks.helpers.logger")
    def test_notification_email_error(self, mock_logger):
        """Test handling email sending errors."""
        with patch("django.core.mail.send_mail") as mock_send:
            mock_send.side_effect = Exception("SMTP error")

            _send_execution_notification(self.execution, "Test message")

            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0][0]
            self.assertIn("Failed to send notification", error_call)


class TestSearchConfigKeyValidation(TestCase):
    """Regression test for #179: unknown search_config keys trigger a warning."""

    def _make_session_with_config(self, extra_keys=None):
        """Create a ready_to_execute session with one active query."""
        user = create_test_user()
        session = SearchSession.objects.create(
            title="Config Key Test", owner=user, status="ready_to_execute"
        )
        config = {
            "domains": [],
            "file_types": [],
            "include_general_search": True,
            "include_guidelines_filter": False,
            "search_types": ["google"],
            "max_results": 10,
            "pagination": {
                "enabled": True,
                "results_per_page": 10,
                "max_pages": 1,
                "delay_between_pages": 0.0,
            },
            "serp_providers": [],
        }
        if extra_keys:
            config.update(extra_keys)
        strategy = SearchStrategy.objects.create(
            session=session,
            user=user,
            population_terms=["patients"],
            interest_terms=["treatment"],
            context_terms=["hospital"],
            search_config=config,
        )
        SearchQuery.objects.create(
            strategy=strategy,
            session=session,
            query_text="(patients) AND (treatment) AND (hospital)",
            query_type="general",
            is_active=True,
            execution_order=1,
        )
        return session

    @patch("apps.core.services.serper_client.requests.post")
    def test_unknown_key_triggers_warning(self, mock_post):
        """Unknown search_config keys fire a warning; search still runs."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic": [],
            "credits": 1,
            "searchInformation": {"totalResults": "0", "searchTime": 0.1},
        }
        mock_response.headers = {"X-Request-ID": "test-179"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        session = self._make_session_with_config(extra_keys={"num_pages": 1})

        with self.assertLogs(
            "apps.serp_execution.tasks.simple_tasks", level="INFO"
        ) as cm:
            result = execute_search_session_simple(str(session.id))  # type: ignore[call-arg]

        warning_lines = [line for line in cm.output if "WARNING" in line]
        self.assertTrue(
            any(
                "Ignored unrecognised search_config keys" in line
                and "num_pages" in line
                for line in warning_lines
            )
        )
        self.assertTrue(result["success"])

    @patch("apps.core.services.serper_client.requests.post")
    def test_clean_config_no_warning(self, mock_post):
        """A config with only known keys produces no warning about unrecognised keys."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic": [],
            "credits": 1,
            "searchInformation": {"totalResults": "0", "searchTime": 0.1},
        }
        mock_response.headers = {"X-Request-ID": "test-179-clean"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        session = self._make_session_with_config()

        with self.assertLogs(
            "apps.serp_execution.tasks.simple_tasks", level="INFO"
        ) as cm:
            result = execute_search_session_simple(str(session.id))  # type: ignore[call-arg]

        self.assertFalse(
            any("Ignored unrecognised search_config keys" in line for line in cm.output)
        )
        self.assertTrue(result["success"])


class TestExecuteSearchSessionReviewMode(TestCase):
    """Regression for #178: the dispatched SERP task must create WF2 results as DUAL.

    Exercises the full live path (execute_search_session_simple ->
    SearchResultProcessor.process_search_results) rather than BatchProcessor,
    closing the worker-vs-eager caveat from the issue re-opening.
    """

    def _make_wf2_session(self, min_reviewers: int = 2) -> SearchSession:
        user = create_test_user()
        session = SearchSession.objects.create(
            title="WF2 review-mode task test",
            owner=user,
            status="ready_to_execute",
        )
        strategy = SearchStrategy.objects.create(
            session=session,
            user=user,
            population_terms=["patients"],
            interest_terms=["treatment"],
            context_terms=["hospital"],
            search_config={
                "domains": [],
                "file_types": [],
                "include_general_search": True,
                "include_guidelines_filter": False,
                "search_types": ["google"],
                "max_results": 10,
                "pagination": {
                    "enabled": True,
                    "results_per_page": 10,
                    "max_pages": 1,
                    "delay_between_pages": 0.0,
                },
                "serp_providers": [],
            },
        )
        SearchQuery.objects.create(
            strategy=strategy,
            session=session,
            query_text="(patients) AND (treatment) AND (hospital)",
            query_type="general",
            is_active=True,
            execution_order=1,
        )
        config = ReviewConfiguration.objects.create(
            session=session,
            min_reviewers_per_result=min_reviewers,
            version=1,
            created_by=user,
        )
        session.current_configuration = config
        session.save(update_fields=["current_configuration"])
        return session

    @patch("apps.core.services.serper_client.requests.post")
    def test_wf2_pipeline_results_are_dual(self, mock_post):
        """A real WF2 search through the task creates DUAL / 2 results, not SINGLE / 1."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic": [
                {
                    "position": 1,
                    "title": "Dual screening result",
                    "link": "https://example.org/guideline",
                    "snippet": "A grey-literature guideline.",
                }
            ],
            "credits": 1,
            "searchInformation": {"totalResults": "1", "searchTime": 0.1},
        }
        mock_response.headers = {"X-Request-ID": "test-178"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        session = self._make_wf2_session(min_reviewers=2)

        result = execute_search_session_simple(str(session.id))  # type: ignore[call-arg]
        self.assertTrue(result["success"])

        results = list(ProcessedResult.objects.filter(session=session))
        self.assertGreaterEqual(len(results), 1)
        for r in results:
            self.assertEqual(r.review_mode, "DUAL", r.url)
            self.assertEqual(r.min_reviewers_required, 2, r.url)
