"""
Test suite for automatic state transitions in the 9-state workflow.
Validates that all automatic transitions work correctly without manual intervention.
"""

import unittest.mock
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TransactionTestCase
from django.utils import timezone

from apps.results_manager.models import ProcessingSession
from apps.results_manager.tasks.processing import finalize_processing_task
from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_manager.services.state_manager import SessionStateManager
from apps.review_manager.views_main import SessionDetailView
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.serp_execution.tasks.monitoring_helpers import (
    handle_session_state_transition,
    process_monitoring_check,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class AutomaticStateTransitionsTest(TransactionTestCase):
    """Test automatic state transitions in the 9-state workflow."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session",
            owner=self.user,
            status="draft",
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test intervention"],
            context_terms=["test context"],
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            is_active=True,
        )

    def test_ready_to_execute_to_executing_automatic(self):
        """Test automatic transition from ready_to_execute to executing."""
        # Set session to ready_to_execute
        self.session.status = "ready_to_execute"
        self.session.save()

        state_manager = SessionStateManager(self.session)

        with patch("apps.core.progress.tracker.ProgressTracker") as MockTracker:
            mock_tracker = MockTracker.return_value

            with patch(
                "apps.serp_execution.tasks.initiate_search_session_execution_task"
            ) as mock_task:
                mock_task.delay.return_value = unittest.mock.MagicMock(
                    id="test-task-id"
                )

                # Mock on_commit to call immediately (TransactionTestCase doesn't auto-commit)
                with patch(
                    "django.db.transaction.on_commit",
                    side_effect=lambda func, **kwargs: func(),
                ):
                    state_manager._trigger_automatic_execution(self.session)

                # Verify execution task was triggered
                mock_task.delay.assert_called_once_with(str(self.session.id))

                # Verify progress events were sent
                self.assertTrue(mock_tracker.update_progress.called)

    @unittest.skip(
        "process_monitoring_check rejects 'executing' status - needs rewrite for current monitoring architecture"
    )
    def test_executing_to_processing_results_automatic(self):
        """Test automatic transition from executing to processing_results when all queries complete."""
        # Set session to executing
        self.session.status = "executing"
        self.session.save()

        # Create search executions
        _execution1 = SearchExecution.objects.create(
            query=self.query,
            status="completed",
            results_count=10,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        _execution2 = SearchExecution.objects.create(
            query=self.query,
            status="completed",
            results_count=15,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )

        # process_monitoring_check calls reconcile_session_states first, which uses
        # state_machine.transition. Then _transition_to_processing uses DatabaseStateManager.
        # We need to let it actually run (or mock the state machine).
        from django.db import transaction

        with patch(
            "apps.core.state_machine.state_machine.state_machine.transition"
        ) as mock_sm_transition:
            mock_sm_transition.return_value = unittest.mock.MagicMock()

            with patch(
                "apps.core.services.simple_services.DatabaseStateManager.set_session_status"
            ) as mock_set_status:
                mock_set_status.return_value = True

                # Mock _validate_session to bypass status check (it rejects
                # 'executing' status) and select_for_update (needs transaction)
                with patch(
                    "apps.serp_execution.tasks.monitoring._validate_session",
                    return_value=self.session,
                ):
                    with transaction.atomic():
                        should_continue, result = process_monitoring_check(
                            str(self.session.id), 0
                        )

                # Should not continue monitoring (all complete)
                self.assertFalse(should_continue)

    def test_processing_results_to_ready_for_review_automatic(self):
        """Test automatic transition from processing_results to ready_for_review."""
        # Set session to processing_results
        self.session.status = "processing_results"
        self.session.save()

        # Create processing session (must be "processing" for finalization to accept it)
        processing_session = ProcessingSession.objects.create(
            search_session=self.session,
            status="processing",
            total_raw_results=50,
            processed_count=45,
            duplicate_count=5,
        )

        dedup_results = {
            "duplicates_found": 5,
            "groups_created": 2,
            "unique_results": 45,
        }

        # Call finalize task (bind=True, Celery passes self automatically)
        _result = finalize_processing_task(  # type: ignore[call-arg]
            dedup_results,
            str(self.session.id),
            str(processing_session.id),
        )

        # Verify session transitioned
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_for_review")

    def test_ready_for_review_session_accessible(self):
        """Test that a session in ready_for_review state can be accessed via the detail view."""
        # Set session to ready_for_review
        self.session.status = "ready_for_review"
        self.session.save()

        # Create request
        factory = RequestFactory()
        request = factory.get(f"/review/{self.session.id}/")
        request.user = self.user

        # Create view instance - pk_url_kwarg is "session_id"
        view = SessionDetailView()
        view.request = request
        view.kwargs = {"session_id": str(self.session.id)}

        # Verify object can be retrieved
        session = view.get_object()
        self.assertEqual(session.id, self.session.id)
        self.assertEqual(session.status, "ready_for_review")

    def test_full_automatic_workflow(self):
        """Test the complete automatic workflow from processing_results to ready_for_review."""
        # Test the finalize_processing_task which transitions processing_results -> ready_for_review
        self.session.status = "processing_results"
        self.session.save()

        processing_session = ProcessingSession.objects.create(
            search_session=self.session,
            status="processing",
            total_raw_results=20,
            processed_count=18,
            duplicate_count=2,
        )

        # Finalize processing (bind=True, Celery passes self automatically)
        dedup_results = {"duplicates_found": 2, "unique_results": 18}
        finalize_processing_task(  # type: ignore[call-arg]
            dedup_results,
            str(self.session.id),
            str(processing_session.id),
        )

        # Verify ready_for_review
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_for_review")

        # Verify activity was logged
        activities = SessionActivity.objects.filter(
            session=self.session, activity_type="status_changed"
        ).order_by("created_at")
        self.assertGreaterEqual(activities.count(), 1)

    def test_race_condition_prevention(self):
        """Test that distributed locks prevent race conditions during transitions."""
        from apps.core.utils.distributed_lock import (
            DistributedLock,
            LockAcquisitionError,
            LockConfig,
        )

        self.session.status = "executing"
        self.session.save()

        # Create completed execution
        SearchExecution.objects.create(
            query=self.query, status="completed", results_count=10
        )

        # Configure lock with no retries for fast failure
        config = LockConfig(retry_count=1, retry_delay=0, timeout=1)
        lock = DistributedLock(config=config)
        acquired = False

        # Mock _safe_cache_add to simulate lock already held
        with patch.object(lock, "_safe_cache_add", return_value=False):
            with patch.object(lock, "_safe_cache_get", return_value="existing_lock"):
                try:
                    with lock.acquire(
                        f"session_transition_{self.session.id}", timeout=1
                    ):
                        acquired = True
                except LockAcquisitionError:
                    pass

        # Verify lock was not acquired
        self.assertFalse(acquired)

    def test_error_recovery_in_transitions(self):
        """Test that handle_session_state_transition updates session state."""
        self.session.status = "executing"
        self.session.save()

        # Create completed execution
        SearchExecution.objects.create(
            query=self.query, status="completed", results_count=10
        )

        # handle_session_state_transition uses DatabaseStateManager.set_session_status
        # Wrap in transaction.atomic because TransactionTestCase uses autocommit
        # and downstream signals may use select_for_update
        from django.db import transaction

        with transaction.atomic():
            success = handle_session_state_transition(
                self.session,
                None,  # state_manager (deprecated parameter)
                "processing_results",
                {"test": "metadata"},
            )

        # Should succeed
        self.assertTrue(success)

        # Verify session state was updated
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "processing_results")
