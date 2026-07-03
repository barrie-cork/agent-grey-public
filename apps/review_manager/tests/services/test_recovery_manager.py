"""
Tests for the WorkflowRecoveryManager service.
"""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.results_manager.models import ProcessingSession
from apps.review_manager.models import SearchSession
from apps.review_manager.services.recovery_manager import WorkflowRecoveryManager
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class WorkflowRecoveryManagerTests(TestCase):
    """Test automatic workflow recovery functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.recovery_manager = WorkflowRecoveryManager()

    def create_stuck_session(self, status, hours_old=2):
        """Helper to create a stuck session."""
        session = SearchSession.objects.create(
            title=f"Stuck {status} Session", owner=self.user, status=status
        )

        # Manually set updated_at to simulate being stuck
        old_time = timezone.now() - timedelta(hours=hours_old)
        SearchSession.objects.filter(pk=session.pk).update(updated_at=old_time)

        return session

    def test_find_stuck_executing_sessions(self):
        """Test detection of sessions stuck in executing state."""
        # Create sessions with different ages
        stuck_session = self.create_stuck_session("executing", hours_old=2)
        _recent_session = self.create_stuck_session("executing", hours_old=0.5)  # type: ignore[arg-type]

        # Find stuck sessions (timeout is 1 hour)
        stuck = self.recovery_manager._find_stuck_sessions(
            "executing", timedelta(hours=1)
        )

        self.assertEqual(len(stuck), 1)
        self.assertEqual(stuck[0].id, stuck_session.id)

    def test_recover_executing_with_no_executions(self):
        """Test recovery of executing session with no executions."""
        session = self.create_stuck_session("executing", hours_old=2)

        # Add strategy but no queries
        SearchStrategy.objects.create(
            session=session,
            user=self.user,
            population_terms=["Test"],
            interest_terms=["Test"],
            context_terms=["Test"],
        )

        # Run recovery
        results = self.recovery_manager.recover_stuck_sessions()

        self.assertEqual(results["issues_detected"], 1)
        self.assertEqual(results["recoveries_succeeded"], 1)

        # Check session was recovered
        session.refresh_from_db()
        self.assertEqual(session.status, "ready_to_execute")

    def test_recover_executing_with_all_completed(self):
        """Test recovery of executing session with all executions done."""
        session = self.create_stuck_session("executing", hours_old=2)

        # Add completed execution
        strategy = SearchStrategy.objects.create(session=session, user=self.user)
        query = SearchQuery.objects.create(
            strategy=strategy,
            session=session,
            query_text="test",
            is_active=False,
        )
        SearchQuery.objects.filter(id=query.id).update(is_active=True)
        SearchExecution.objects.create(
            query=query, initiated_by=self.user, status="completed", results_count=10
        )

        # Run recovery
        results = self.recovery_manager.recover_stuck_sessions()

        self.assertEqual(results["recoveries_succeeded"], 1)

        # Check session was moved to ready_to_execute
        session.refresh_from_db()
        self.assertEqual(session.status, "ready_to_execute")

    def test_recover_processing_with_no_processing_session(self):
        """Test recovery of processing_results with no ProcessingSession."""
        session = self.create_stuck_session("processing_results", hours_old=1)
        # Use update() to avoid resetting auto_now updated_at field
        SearchSession.objects.filter(pk=session.pk).update(total_results=10)

        # Run recovery
        results = self.recovery_manager.recover_stuck_sessions()

        self.assertEqual(results["recoveries_succeeded"], 1)

        # Check session was moved to ready_for_review
        session.refresh_from_db()
        self.assertEqual(session.status, "ready_for_review")

    def test_recover_processing_with_stale_heartbeat(self):
        """Test recovery of processing with stale heartbeat."""
        session = self.create_stuck_session("processing_results", hours_old=1)
        # Set total_results > 0 to avoid _check_orphaned_states double-recovery
        SearchSession.objects.filter(pk=session.pk).update(total_results=10)

        # Add processing session with old heartbeat
        _processing = ProcessingSession.objects.create(
            search_session=session,
            status="in_progress",
            last_heartbeat=timezone.now() - timedelta(minutes=20),
        )

        # Run recovery
        results = self.recovery_manager.recover_stuck_sessions()

        self.assertEqual(results["recoveries_succeeded"], 1)
        session.refresh_from_db()
        self.assertEqual(session.status, "ready_for_review")

    def test_healthy_session_not_recovered(self):
        """Test that healthy sessions are not recovered."""
        # Create executing session with active execution
        session = self.create_stuck_session("executing", hours_old=0.1)  # type: ignore[arg-type]

        strategy = SearchStrategy.objects.create(session=session, user=self.user)
        query = SearchQuery.objects.create(
            strategy=strategy,
            session=session,
            query_text="test",
            is_active=False,
        )
        SearchQuery.objects.filter(id=query.id).update(is_active=True)
        SearchExecution.objects.create(
            query=query,
            initiated_by=self.user,
            status="running",
            started_at=timezone.now() - timedelta(minutes=5),
        )

        # Run recovery
        results = self.recovery_manager.recover_stuck_sessions()

        # Should detect but not recover (healthy)
        self.assertEqual(results["issues_detected"], 0)
        self.assertEqual(results["recoveries_succeeded"], 0)

    def test_orphaned_zero_result_sessions(self):
        """Test recovery of sessions with 0 results stuck in wrong state."""
        # Create session stuck in processing with 0 results
        session = SearchSession.objects.create(
            title="Zero Result Session",
            owner=self.user,
            status="processing_results",
            total_results=0,
        )

        # Run recovery
        results = self.recovery_manager.recover_stuck_sessions()

        self.assertEqual(results["recoveries_succeeded"], 1)

        # Should be moved to completed
        session.refresh_from_db()
        self.assertEqual(session.status, "completed")

    def test_get_session_diagnostics(self):
        """Test comprehensive session diagnostics."""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        strategy = SearchStrategy.objects.create(session=session, user=self.user)
        query = SearchQuery.objects.create(
            strategy=strategy,
            session=session,
            query_text="test query",
            is_active=False,
        )
        SearchQuery.objects.filter(id=query.id).update(is_active=True)

        _execution = SearchExecution.objects.create(
            query=query, initiated_by=self.user, status="completed", results_count=5
        )

        # Get diagnostics
        diagnostics = self.recovery_manager.get_session_diagnostics(str(session.id))

        # Verify diagnostic data
        self.assertEqual(diagnostics["session_id"], str(session.id))
        self.assertEqual(diagnostics["status"], "executing")
        self.assertEqual(diagnostics["queries"]["total"], 1)
        self.assertEqual(diagnostics["queries"]["active"], 1)
        self.assertEqual(diagnostics["executions"]["completed"], 1)
        self.assertIn("health_check", diagnostics)
        self.assertIn("validations", diagnostics)
        self.assertIn("data_integrity", diagnostics)

    def test_recovery_with_force_transition(self):
        """Test recovery that requires force transition."""
        _session = self.create_stuck_session("executing", hours_old=2)

        # Mock state manager to fail normal transition
        with patch(
            "apps.review_manager.services.recovery_manager.SessionStateManager"
        ) as mock_sm:
            mock_instance = Mock()
            mock_sm.return_value = mock_instance

            # Normal transition returns failure (triggers StateTransitionError path)
            mock_instance.transition_to.return_value = (
                False,
                "Transition failed",
            )
            # Force transition succeeds
            mock_instance.force_transition.return_value = True

            # Run recovery
            _results = self.recovery_manager.recover_stuck_sessions()

            # Should use force transition after normal transition fails
            self.assertTrue(mock_instance.force_transition.called)

    def test_recovery_statistics(self):
        """Test recovery statistics tracking."""
        # Create multiple stuck sessions
        _stuck1 = self.create_stuck_session("executing", hours_old=2)
        _stuck2 = self.create_stuck_session("processing_results", hours_old=1)

        # Run recovery
        results = self.recovery_manager.recover_stuck_sessions()

        # Check statistics - both sessions found via timeout + orphan checks
        self.assertGreaterEqual(results["sessions_checked"], 2)
        self.assertGreaterEqual(results["issues_detected"], 2)
        self.assertGreaterEqual(results["recoveries_attempted"], 2)
        self.assertIn("execution_time_seconds", results)
        self.assertIn("timestamp", results)
        self.assertIsInstance(results["details"], list)
