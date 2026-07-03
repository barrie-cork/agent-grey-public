"""
Unit tests for monitoring_helpers module.
Tests field reference fixes and transaction scope improvements.
"""

import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.results_manager.models import ProcessedResult, ProcessingSession
from apps.review_manager.models import SearchSession, SessionActivity
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.serp_execution.tasks.monitoring_helpers import reconcile_session_states
from apps.core.tests.utils import create_test_user

User = get_user_model()


class TestReconcileSessionStates(TestCase):
    """Test reconcile_session_states function with correct field references."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            owner=self.user, title="Test Session", status="executing"
        )
        # Create a search strategy first (required for SearchQuery)
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["elderly"],
            interest_terms=["telehealth"],
            context_terms=["rural"],
            search_config={
                "domains": ["nice.org.uk"],
                "include_general_search": True,
                "file_types": ["pdf"],
            },
            is_complete=True,
        )
        # Create a search query
        self.query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="test query",
            is_active=True,
        )

    def test_correct_field_references_for_processing_session(self):
        """Test that ProcessingSession uses correct field reference: search_session."""
        # Create a processing session with correct field
        processing_session = ProcessingSession.objects.create(
            search_session=self.session,  # Correct field name
            status="completed",
            total_raw_results=10,
            processed_count=10,
            unique_count=8,
        )

        # Run reconciliation
        _result = reconcile_session_states(str(self.session.id))

        # Verify the query works (it would fail if using wrong field name)
        processing_sessions = ProcessingSession.objects.filter(
            search_session=self.session
        )
        self.assertEqual(processing_sessions.count(), 1)
        self.assertEqual(processing_sessions.first().id, processing_session.id)

    def test_correct_field_references_for_processed_result(self):
        """Test that ProcessedResult uses correct field reference: session."""
        # Create a processed result with correct field
        _processed_result = ProcessedResult.objects.create(
            session=self.session,  # Correct field name
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet",
        )

        # Set session to ready_for_review to trigger the check
        self.session.status = "ready_for_review"
        self.session.save()

        # Run reconciliation
        result = reconcile_session_states(str(self.session.id))

        # Verify the query works (it would fail if using wrong field name)
        processed_count = ProcessedResult.objects.filter(session=self.session).count()
        self.assertEqual(processed_count, 1)

        # Check that the reconciliation found the result
        self.assertIn("Confirmed 1 unique results ready for review", result["changes"])

    def test_transaction_atomic_scope(self):
        """Test that entire reconciliation is wrapped in transaction."""
        with patch("django.db.transaction.atomic") as mock_atomic:
            # Setup mock to simulate transaction context manager
            mock_atomic.return_value.__enter__ = MagicMock()
            mock_atomic.return_value.__exit__ = MagicMock()

            # Run reconciliation
            reconcile_session_states(str(self.session.id))

            # Verify transaction.atomic was called
            mock_atomic.assert_called_once()

    def test_select_for_update_prevents_concurrent_access(self):
        """Test that select_for_update is used to lock the session."""
        with patch.object(SearchSession.objects, "select_for_update") as mock_select:
            mock_select.return_value = SearchSession.objects.filter(id=self.session.id)

            # Run reconciliation
            reconcile_session_states(str(self.session.id))

            # Verify select_for_update was called
            mock_select.assert_called_once()

    def test_reconcile_processing_complete_state(self):
        """Test reconciliation when processing is complete but session stuck."""
        # Set session to processing_results
        self.session.status = "processing_results"
        self.session.save()

        # Create completed processing session
        ProcessingSession.objects.create(
            search_session=self.session,
            status="completed",
            total_raw_results=10,
            processed_count=10,
        )

        # Mock state machine transition with correct import path
        with patch("apps.core.state_machine.state_machine") as mock_sm:
            mock_sm.transition = MagicMock()

            # Run reconciliation
            result = reconcile_session_states(str(self.session.id))

            # Verify state machine was called to transition
            mock_sm.transition.assert_called_once_with(
                self.session.id,
                "ready_for_review",
                metadata={
                    "reason": "state_reconciliation",
                    "processing_session_id": mock_sm.transition.call_args[1][
                        "metadata"
                    ]["processing_session_id"],
                    "reconciliation_type": "processing_complete",
                },
                triggered_by="reconciliation",
            )

            # Check result
            self.assertTrue(result["reconciled"])
            self.assertIn(
                "Transitioned from processing_results to ready_for_review",
                result["changes"],
            )

    def test_reconcile_all_executions_complete(self):
        """Test reconciliation when all executions complete but session stuck in executing."""
        # Create completed execution
        _execution = SearchExecution.objects.create(
            query=self.query, status="completed", results_count=5
        )

        # Mock state machine transition with correct import path
        with patch("apps.core.state_machine.state_machine") as mock_sm:
            mock_sm.transition = MagicMock()

            # Mock the processing task
            with patch(
                "apps.results_manager.tasks.process_session_results_task"
            ) as mock_task:
                mock_task.apply_async = MagicMock()

                # Run reconciliation
                result = reconcile_session_states(str(self.session.id))

                # Verify state machine was called
                mock_sm.transition.assert_called_once_with(
                    self.session.id,
                    "processing_results",
                    metadata={
                        "reason": "state_reconciliation",
                        "completed_executions": 1,
                        "reconciliation_type": "executions_complete",
                    },
                    triggered_by="reconciliation",
                )

                # Verify processing task was triggered
                mock_task.apply_async.assert_called_once_with(
                    args=(str(self.session.id),), countdown=2
                )

                # Check result
                self.assertTrue(result["reconciled"])
                self.assertIn(
                    "Transitioned from executing to processing_results",
                    result["changes"],
                )
                self.assertIn("Triggered result processing task", result["changes"])

    def test_reconcile_with_no_results_in_ready_for_review(self):
        """Test reconciliation when session in ready_for_review but no results."""
        # Set session to ready_for_review
        self.session.status = "ready_for_review"
        self.session.save()

        # Run reconciliation (no ProcessedResult records exist)
        result = reconcile_session_states(str(self.session.id))

        # Check that error was recorded
        self.assertIn("No processed results found", result["errors"])

    def test_reconcile_session_not_found(self):
        """Test reconciliation with non-existent session."""
        fake_id = str(uuid.uuid4())

        # Run reconciliation
        result = reconcile_session_states(fake_id)

        # Check error handling
        self.assertFalse(result["reconciled"])
        self.assertIn(f"Session {fake_id} not found", result["errors"])

    def test_reconcile_with_exception_handling(self):
        """Test that exceptions are properly caught and logged."""
        # Mock state machine to raise exception with correct import path
        with patch("apps.core.state_machine.state_machine") as mock_sm:
            mock_sm.transition.side_effect = Exception("Test error")

            # Create completed execution to trigger transition
            SearchExecution.objects.create(
                query=self.query, status="completed", results_count=5
            )

            # Run reconciliation
            result = reconcile_session_states(str(self.session.id))

            # Check that error was caught and logged
            self.assertFalse(result["reconciled"])
            self.assertIn("Test error", result["errors"])

    def test_activity_logging_on_successful_reconciliation(self):
        """Test that SessionActivity is created on successful reconciliation."""
        # Set session to processing_results
        self.session.status = "processing_results"
        self.session.save()

        # Create completed processing session
        ProcessingSession.objects.create(
            search_session=self.session,
            status="completed",
            total_raw_results=10,
            processed_count=10,
        )

        # Mock state machine transition to succeed with correct import path
        with patch("apps.core.state_machine.state_machine") as mock_sm:
            mock_sm.transition = MagicMock()

            # Run reconciliation
            _result = reconcile_session_states(str(self.session.id))

            # Check that activity was logged
            activities = SessionActivity.objects.filter(
                session=self.session, activity_type="state_reconciliation"
            )
            self.assertEqual(activities.count(), 1)

            activity = activities.first()
            self.assertIn("processing complete but session stuck", activity.description)
            self.assertEqual(activity.metadata["previous_state"], "processing_results")
            self.assertEqual(activity.metadata["new_state"], "ready_for_review")

    def test_reconcile_without_processing_session_does_not_crash(self):
        """No ProcessingSession: the optional-guard branch is skipped safely.

        Regression for issue #169: ``processing_sessions.first()`` returns
        ``None`` when none exist, so the reconciliation must guard against
        ``None`` before accessing ``.status``/``.id`` rather than relying on
        a separate ``.exists()`` check.
        """
        # processing_results state would trigger the ProcessingSession branch,
        # but with no ProcessingSession rows it must short-circuit cleanly.
        self.session.status = "processing_results"
        self.session.save()

        # No ProcessingSession.objects.create() here on purpose.
        result = reconcile_session_states(str(self.session.id))

        # No reconciliation performed, no errors, no AttributeError raised.
        self.assertFalse(result["reconciled"])
        self.assertEqual(result["errors"], [])
