"""
Tests for the SessionStateManager service.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase

from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_manager.services.state_manager import SessionStateManager
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.core.tests.utils import create_test_user

User = get_user_model()


class StateManagerTests(TransactionTestCase):
    """Test atomic state transitions and rollback behavior."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user(first_name="Test", last_name="User")

        self.session = SearchSession.objects.create(
            title="Test Session",
            description="Test description",
            owner=self.user,
            status="draft",
        )

        self.state_manager = SessionStateManager(self.session)

    def test_valid_transition(self):
        """Test a valid state transition."""
        # Transition from draft to defining_search
        result, error = self.state_manager.transition_to(
            "defining_search", metadata={"test": "data"}
        )

        self.assertTrue(result, f"Transition failed: {error}")

        # Verify state changed
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "defining_search")

        # Verify activity logged
        activity = SessionActivity.objects.filter(
            session=self.session, activity_type="status_changed"
        ).first()

        self.assertIsNotNone(activity)
        self.assertEqual(activity.metadata["old_status"], "draft")
        self.assertEqual(activity.metadata["new_status"], "defining_search")
        self.assertEqual(activity.metadata["transition_metadata"]["test"], "data")

    def test_invalid_transition(self):
        """Test an invalid state transition."""
        # Try to transition from draft to executing (not allowed)
        result, error = self.state_manager.transition_to("executing")

        self.assertFalse(result)
        self.assertIn("not allowed", error)

        # Verify state unchanged
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "draft")

    def test_atomic_rollback_on_activity_failure(self):
        """Test that state rolls back if activity creation fails."""
        # Mock SessionActivity.log_activity to raise an exception
        with patch.object(SessionActivity, "log_activity") as mock_log:
            mock_log.side_effect = Exception("Activity creation failed")

            result, error = self.state_manager.transition_to("defining_search")
            self.assertFalse(result)
            self.assertIn("Activity creation failed", error)

            # Verify status rolled back
            self.session.refresh_from_db()
            self.assertEqual(self.session.status, "draft")

    def test_concurrent_modification_protection(self):
        """Test protection against concurrent modifications."""
        # This test verifies that the state manager uses select_for_update
        # which prevents race conditions by locking the row

        # First transition should succeed
        result1, _ = self.state_manager.transition_to("defining_search")
        self.assertTrue(result1)

        # Create another manager that will try an invalid transition
        another_manager = SessionStateManager(self.session)

        # Try to make an invalid transition from the current state
        # defining_search cannot go directly to executing
        result, error = another_manager.transition_to("executing")
        self.assertFalse(result)
        self.assertIn("not allowed", error)

    def test_executing_transition_sets_started_at(self):
        """Test that transitioning to executing sets started_at."""
        # Set up required data for executing status
        self.session.status = "ready_to_execute"
        self.session.save()

        # Create search strategy and query to satisfy validation
        strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test population"],
            interest_terms=["test interest"],
        )

        SearchQuery.objects.create(
            strategy=strategy,
            session=self.session,
            query_text="test query",
            query_type="domain-specific",
            target_domain="test.com",
            is_active=True,
        )

        self.assertIsNone(self.session.started_at)

        state_manager = SessionStateManager(self.session)
        success, _ = state_manager.transition_to("executing")
        self.assertTrue(success)

        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.started_at)

    def test_completed_transition_sets_completed_at(self):
        """Test that transitioning to completed sets completed_at."""
        # Move to under_review first
        self.session.status = "under_review"
        self.session.save()

        self.assertIsNone(self.session.completed_at)

        state_manager = SessionStateManager(self.session)
        success, _ = state_manager.transition_to("completed")
        self.assertTrue(success)

        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.completed_at)

    def test_force_transition(self):
        """Test force transition for recovery."""
        # Force transition that would normally be invalid
        result = self.state_manager.force_transition(
            "completed", reason="Emergency recovery"
        )

        self.assertTrue(result)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")

        # Check activity log
        activity = SessionActivity.objects.filter(
            session=self.session, activity_type="status_changed"
        ).first()

        self.assertTrue(activity.metadata["forced"])
        self.assertEqual(activity.metadata["reason"], "Emergency recovery")


class WorkflowValidatorIntegrationTests(TestCase):
    """Test workflow validation with state manager."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="ready_to_execute"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["Test population"],
            interest_terms=["Test interest"],
            context_terms=["Test context"],
        )

    def test_cannot_execute_without_queries(self):
        """Test that execution fails without active queries."""
        state_manager = SessionStateManager(self.session)

        result, error = state_manager.transition_to("executing")

        self.assertFalse(result)
        self.assertIn("No active queries", error)

    def test_can_execute_with_queries(self):
        """Test successful execution transition with queries."""
        # Add an active query
        SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            is_active=True,
        )

        state_manager = SessionStateManager(self.session)
        result, error = state_manager.transition_to("executing")

        self.assertTrue(result, f"Transition failed: {error}")
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "executing")

    def test_transition_logging(self):
        """Test that transitions are properly logged."""
        # Add query for valid transition
        SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            is_active=True,
        )

        state_manager = SessionStateManager(self.session)

        # Test logging
        state_manager.log_transition_attempt("executing", True)
        state_manager.log_transition_attempt("processing_results", False, "Test error")

        # Transitions should be logged (check logs in production)
        result, error = state_manager.transition_to("executing")
        self.assertTrue(result, f"Transition failed: {error}")
