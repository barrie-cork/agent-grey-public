"""
Integration tests for zero-results workflow.
Tests the complete backend flow when searches return no results.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Tuple
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.results_manager.models import ProcessingSession
from apps.results_manager.tasks.orchestration import _handle_no_results
from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_manager.services.state_manager import SessionStateManager
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.serp_execution.tasks import initiate_search_session_execution_task
from apps.core.tests.utils import create_test_user

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

User = get_user_model()


class ZeroResultsTestSetupMixin:
    """Mixin providing common setup methods for zero results tests.

    Intended to be used with TestCase (provides assert methods via MRO).
    """

    def create_test_user(self) -> AbstractUser:
        """Create a test user."""
        return create_test_user()

    def create_zero_result_session(self, user: AbstractUser) -> SearchSession:
        """Create a session configured to return zero results."""
        session = SearchSession.objects.create(
            title="Zero Results Test",
            owner=user,
            status="ready_to_execute",
        )

        # Check if strategy already exists (OneToOneField constraint)
        try:
            strategy = session.search_strategy
            strategy.population_terms = ["nonexistentterm123"]
            strategy.interest_terms = ["doesnotexist456"]
            strategy.context_terms = ["invalid789"]
            strategy.save()
        except SearchStrategy.DoesNotExist:
            strategy = SearchStrategy.objects.create(
                session=session,
                user=user,
                population_terms=["nonexistentterm123"],
                interest_terms=["doesnotexist456"],
                context_terms=["invalid789"],
            )

        SearchQuery.objects.create(
            strategy=strategy,
            session=session,
            query_text="nonexistentterm123 filetype:xyz",
            is_active=True,
            execution_order=1,
        )

        return session

    def create_multiple_queries(
        self, strategy: SearchStrategy, count: int = 3
    ) -> List[SearchQuery]:
        """Create multiple search queries for a strategy."""
        queries: List[SearchQuery] = []
        for i in range(count):
            query = SearchQuery.objects.create(
                strategy=strategy,
                session=strategy.session,
                query_text=f"nonexistentterm{i} filetype:xyz",
                is_active=True,
                execution_order=i + 1,
            )
            queries.append(query)
        return queries

    def mock_zero_results_api_response(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Return a mocked API response with zero results."""
        return (
            {
                "organic": [],
                "searchParameters": {"q": "test query"},
            },
            {
                "credits_used": 1,
                "response_time": 0.5,
            },
        )

    def simulate_execution_completion(
        self, execution: SearchExecution, results_count: int = 0
    ) -> None:
        """Simulate an execution completing."""
        execution.status = "completed"
        execution.results_count = results_count
        execution.completed_at = timezone.now()
        execution.save()

    def verify_session_completed(self, session: SearchSession) -> None:
        """Verify a session completed successfully."""
        session.refresh_from_db()
        self.assertEqual(session.status, "completed")  # type: ignore[attr-defined]
        self.assertEqual(session.total_results, 0)  # type: ignore[attr-defined]
        self.assertIsNotNone(session.completed_at)  # type: ignore[attr-defined]

    def verify_activity_logged(
        self, session: SearchSession, text_fragment: str
    ) -> None:
        """Verify an activity was logged containing specific text."""
        activity = SessionActivity.objects.filter(
            session=session, description__icontains=text_fragment
        ).first()
        self.assertIsNotNone(  # type: ignore[attr-defined]
            activity, f"No activity found containing '{text_fragment}'"
        )


class ZeroResultsFlowTestCase(ZeroResultsTestSetupMixin, TestCase):
    """Test the complete zero-results workflow from execution to completion.

    Tests the execution task with mocked external services (SerperClient, Redis,
    event bus) and verifies the zero-results processing path directly.
    """

    def setUp(self) -> None:
        """Set up test data."""
        self.user = self.create_test_user()

    @patch("apps.serp_execution.tasks.simple_tasks.process_session_results_simple")
    @patch("time.sleep")
    @patch("apps.serp_execution.tasks.simple_tasks.event_bus")
    @patch("apps.serp_execution.providers.get_default_provider")
    @patch("apps.serp_execution.tasks.simple_tasks.SearchResultProcessor")
    def test_complete_zero_results_flow(
        self,
        mock_processor_cls: MagicMock,
        mock_get_provider: MagicMock,
        mock_event_bus: MagicMock,
        mock_sleep: MagicMock,
        mock_chain_task: MagicMock,
    ) -> None:
        """Test execution with zero results transitions session correctly.

        Verifies that when the SERP provider returns no organic results, the
        execution task creates SearchExecution records and transitions
        the session to processing_results.
        """
        # Setup mocks
        mock_provider = MagicMock()
        mock_provider.provider_key = "serper"
        mock_provider.safe_search.return_value = ({"organic": []}, {"credits_used": 0})
        mock_get_provider.return_value = mock_provider

        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        session = self.create_zero_result_session(self.user)
        session_id = str(session.id)

        # Step 1: Execute search (calls execute_search_session_simple directly)
        result = initiate_search_session_execution_task(session_id)  # type: ignore[call-arg]

        # Verify execution result
        self.assertTrue(result["success"])
        self.assertEqual(result["queries_executed"], 1)
        self.assertEqual(result["results_processed"], 0)

        # Verify session transitioned to processing_results
        session.refresh_from_db()
        self.assertEqual(session.status, "processing_results")

        # Verify SearchExecution was created with zero results
        execution = SearchExecution.objects.filter(query__session=session).first()
        self.assertIsNotNone(execution)
        self.assertEqual(execution.status, "completed")

        # Verify chained task was triggered
        mock_chain_task.delay.assert_called_once_with(session_id)

        # Step 2: Process results (test zero-results path directly)
        SearchSession.objects.filter(id=session.id).update(status="processing_results")
        session.refresh_from_db()

        processing_session = ProcessingSession.objects.create(
            search_session=session, status="running"
        )

        no_results = _handle_no_results(processing_session, session_id)

        # Verify processing completed
        self.assertIsInstance(no_results, dict)
        self.verify_session_completed(session)

        processing_session.refresh_from_db()
        self.assertEqual(processing_session.status, "completed")

    def test_handle_no_results_function(self) -> None:
        """Test the _handle_no_results function directly."""
        session = self.create_zero_result_session(self.user)
        SearchSession.objects.filter(id=session.id).update(status="processing_results")
        session.refresh_from_db()

        # Create ProcessingSession
        processing_session = ProcessingSession.objects.create(
            search_session=session, status="running"
        )

        # Call _handle_no_results
        result = _handle_no_results(processing_session, str(session.id))

        # Verify result is a dict (NoResultsResponse TypedDict)
        self.assertIsInstance(result, dict)
        self.assertEqual(str(result["session_id"]), str(session.id))

        # Verify states
        self.verify_session_completed(session)

        processing_session.refresh_from_db()
        self.assertEqual(processing_session.status, "completed")

    @patch("apps.serp_execution.tasks.simple_tasks.process_session_results_simple")
    @patch("time.sleep")
    @patch("apps.serp_execution.tasks.simple_tasks.event_bus")
    @patch("apps.serp_execution.providers.get_default_provider")
    @patch("apps.serp_execution.tasks.simple_tasks.SearchResultProcessor")
    def test_multiple_queries_all_zero_results(
        self,
        mock_processor_cls: MagicMock,
        mock_get_provider: MagicMock,
        mock_event_bus: MagicMock,
        mock_sleep: MagicMock,
        mock_chain_task: MagicMock,
    ) -> None:
        """Test workflow with multiple queries all returning zero results."""
        # Setup mocks
        mock_provider = MagicMock()
        mock_provider.provider_key = "serper"
        mock_provider.safe_search.return_value = ({"organic": []}, {"credits_used": 0})
        mock_get_provider.return_value = mock_provider

        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        session = self.create_zero_result_session(self.user)

        # Add more queries (session already has 1 from create_zero_result_session)
        self.create_multiple_queries(session.search_strategy, count=2)

        # Execute all queries
        result = initiate_search_session_execution_task(str(session.id))  # type: ignore[call-arg]
        self.assertTrue(result["success"])
        self.assertEqual(result["queries_executed"], 3)
        self.assertEqual(result["results_processed"], 0)

        # Verify all executions were created
        executions = SearchExecution.objects.filter(query__session=session)
        self.assertEqual(executions.count(), 3)
        self.assertTrue(all(e.status == "completed" for e in executions))

        # Verify session transitioned to processing_results
        session.refresh_from_db()
        self.assertEqual(session.status, "processing_results")


class RecoveryManagerTestCase(ZeroResultsTestSetupMixin, TestCase):
    """Test recovery manager handling of stuck zero-result sessions."""

    def setUp(self) -> None:
        """Set up test data."""
        self.user = self.create_test_user()

    def test_recovery_manager_handles_stuck_zero_results(self) -> None:
        """Test that recovery manager recovers zero-result sessions via orphan check.

        The WorkflowRecoveryManager._check_orphaned_states detects sessions with
        total_results=0 stuck in processing_results and transitions them to completed.
        """
        from apps.review_manager.services.recovery_manager import (
            WorkflowRecoveryManager,
        )

        # Create a session in processing_results with 0 results.
        # Use recent updated_at so _find_stuck_sessions (timeout-based) ignores it.
        # Only _check_orphaned_states (zero-results-based) picks it up.
        session = self._create_zero_result_orphaned_session()

        # Run recovery
        recovery_manager = WorkflowRecoveryManager()
        results = recovery_manager.recover_stuck_sessions()

        # Verify recovery detected and handled the orphaned session
        self.assertGreater(results["issues_detected"], 0)
        self.assertGreater(results["recoveries_succeeded"], 0)

        # Verify session was transitioned to completed
        # (_check_orphaned_states transitions processing_results -> completed for 0-result sessions)
        session.refresh_from_db()
        self.assertEqual(session.status, "completed")

    def _create_zero_result_orphaned_session(self) -> SearchSession:
        """Create a session in processing_results with zero results (orphaned state)."""
        session = self.create_zero_result_session(self.user)
        # Use update() to bypass state transition validation
        SearchSession.objects.filter(id=session.id).update(
            status="processing_results",
            total_results=0,
        )
        session.refresh_from_db()
        return session

    def test_recovery_manager_handles_stuck_timeout(self) -> None:
        """Test that recovery manager handles sessions stuck by timeout.

        Sessions in processing_results for longer than the timeout threshold
        are detected by _find_stuck_sessions and recovered.
        """
        from apps.review_manager.services.recovery_manager import (
            WorkflowRecoveryManager,
        )

        # Create a session stuck in processing_results for over 30 minutes
        session = self.create_zero_result_session(self.user)
        SearchSession.objects.filter(id=session.id).update(
            status="processing_results",
            total_results=0,
            updated_at=timezone.now() - timezone.timedelta(hours=1),
        )
        session.refresh_from_db()

        # Run recovery
        recovery_manager = WorkflowRecoveryManager()
        results = recovery_manager.recover_stuck_sessions()

        # Verify issues were detected
        self.assertGreater(results["issues_detected"], 0)
        self.assertGreater(results["recoveries_succeeded"], 0)

        # Session should have been recovered (exact final state depends on
        # which recovery path runs -- timeout-based or orphan check)
        session.refresh_from_db()
        self.assertIn(
            session.status,
            ["ready_for_review", "completed", "archived"],
            f"Session should have been recovered from processing_results, "
            f"got '{session.status}'",
        )


class ZeroResultsWithErrorsTestCase(ZeroResultsTestSetupMixin, TestCase):
    """Test zero results workflow when some queries fail."""

    def setUp(self) -> None:
        """Set up test data."""
        self.user = self.create_test_user()

    @patch("apps.serp_execution.tasks.simple_tasks.retry_manager")
    @patch("apps.serp_execution.tasks.simple_tasks.process_session_results_simple")
    @patch("time.sleep")
    @patch("apps.serp_execution.tasks.simple_tasks.event_bus")
    @patch("apps.serp_execution.tasks.simple_tasks.SearchResultProcessor")
    @patch("apps.serp_execution.providers.get_default_provider")
    def test_zero_results_with_api_errors(
        self,
        mock_get_provider: MagicMock,
        mock_processor_cls: MagicMock,
        mock_event_bus: MagicMock,
        mock_sleep: MagicMock,
        mock_chain_task: MagicMock,
        mock_retry_mgr: MagicMock,
    ) -> None:
        """Test execution when some queries fail and remaining return zero results.

        Verifies that when one query succeeds with 0 results and another fails,
        the execution task handles both gracefully and transitions the session.
        """
        # Setup: first call returns zero results, second raises an error
        mock_provider = MagicMock()
        mock_provider.provider_key = "serper"
        mock_provider.safe_search.side_effect = [
            (
                {"organic": []},
                {"credits_used": 0},
            ),  # First query: success with 0 results
            ConnectionError("API rate limit exceeded"),  # Second query: fails
        ]
        mock_get_provider.return_value = mock_provider

        # Prevent retry logic from calling self.retry() (no Celery context)
        mock_retry_mgr.categorize_error.return_value = "unknown"

        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        session = self.create_zero_result_session(self.user)

        # Add another query
        SearchQuery.objects.create(
            strategy=session.search_strategy,
            session=session,
            query_text="another nonexistent query",
            is_active=True,
            execution_order=2,
        )

        # Execute -- the task handles errors per-query and continues
        result = initiate_search_session_execution_task(str(session.id))  # type: ignore[call-arg]

        # Verify execution completed (task catches per-query exceptions)
        self.assertTrue(result["success"])
        self.assertEqual(result["queries_executed"], 2)

        # Verify session transitioned to processing_results
        session.refresh_from_db()
        self.assertEqual(session.status, "processing_results")

        # Verify executions: one completed, one failed
        executions = SearchExecution.objects.filter(query__session=session).order_by(
            "query__execution_order"
        )
        self.assertEqual(executions.count(), 2)

        completed = executions.filter(status="completed")
        failed = executions.filter(status="failed")
        self.assertEqual(completed.count(), 1)
        self.assertEqual(failed.count(), 1)

    @patch("apps.serp_execution.tasks.simple_tasks.process_session_results_simple")
    @patch("time.sleep")
    @patch("apps.serp_execution.tasks.simple_tasks.event_bus")
    @patch("apps.serp_execution.tasks.simple_tasks.SearchResultProcessor")
    @patch("apps.serp_execution.providers.get_default_provider")
    def test_all_queries_fail(
        self,
        mock_get_provider: MagicMock,
        mock_processor_cls: MagicMock,
        mock_event_bus: MagicMock,
        mock_sleep: MagicMock,
        mock_chain_task: MagicMock,
    ) -> None:
        """Test that when all queries fail, the session still transitions."""
        mock_provider = MagicMock()
        mock_provider.provider_key = "serper"
        mock_provider.safe_search.side_effect = ValueError("API unavailable")
        mock_get_provider.return_value = mock_provider

        mock_processor = MagicMock()
        mock_processor_cls.return_value = mock_processor

        session = self.create_zero_result_session(self.user)
        session_id = str(session.id)

        result = initiate_search_session_execution_task(session_id)  # type: ignore[call-arg]

        # Even with all failures, the task returns success=True
        # (it catches per-query exceptions and continues)
        self.assertTrue(result["success"])
        self.assertEqual(result["results_processed"], 0)

        # Session should be at processing_results (task always transitions at end)
        session.refresh_from_db()
        self.assertEqual(session.status, "processing_results")

        # The failed execution should be recorded
        execution = SearchExecution.objects.filter(query__session=session).first()
        self.assertIsNotNone(execution)
        self.assertEqual(execution.status, "failed")


class ZeroResultsStateTransitionTestCase(ZeroResultsTestSetupMixin, TestCase):
    """Test state transitions specific to zero-results scenarios."""

    def setUp(self) -> None:
        """Set up test data."""
        self.user = self.create_test_user()

        self.session = SearchSession.objects.create(
            title="State Transition Test", owner=self.user, status="processing_results"
        )

    def test_processing_to_completed_transition(self) -> None:
        """Test transition from processing_results to completed."""
        state_manager = SessionStateManager(self.session)

        # Should be able to transition to completed
        state_manager.transition_to(
            "completed", metadata={"reason": "zero_results", "total_results": 0}
        )

        self._verify_transition_successful()

    def _verify_transition_successful(self) -> None:
        """Verify the state transition was successful."""
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")

    def test_cannot_transition_from_completed(self) -> None:
        """Test that completed status is final (cannot go backwards)."""
        SearchSession.objects.filter(id=self.session.id).update(status="completed")
        self.session.refresh_from_db()

        # completed -> processing_results should not be allowed
        can_transition = self.session.can_transition_to("processing_results")
        self.assertFalse(can_transition)

        # Status should remain completed
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")
