"""
Tests for review_manager utility functions.

Tests for session statistics, status transitions, progress calculations,
and other utility functions.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from ..models import SearchSession, SessionActivity
from ..utils import (
    calculate_workflow_progress,
    get_dashboard_summary,
    get_session_statistics,
    transition_session_status,
    validate_status_transition,
)
from apps.core.tests.utils import create_test_user

User = get_user_model()


class UtilityFunctionTests(TestCase):
    """Test cases for utility functions."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        # Create test sessions
        self.session1 = SearchSession.objects.create(
            title="Test Session 1", owner=self.user, status="draft"
        )

        self.session2 = SearchSession.objects.create(
            title="Test Session 2",
            owner=self.user,
            status="completed",
            total_results=50,
            reviewed_results=50,
            included_results=25,
        )

    def test_get_session_statistics(self):
        """Test session statistics calculation."""
        stats = get_session_statistics(self.user)

        self.assertEqual(stats["total_sessions"], 2)
        self.assertEqual(stats["completed_sessions"], 1)
        self.assertEqual(stats["total_results_found"], 50)
        self.assertEqual(stats["total_results_reviewed"], 50)
        self.assertEqual(stats["total_results_included"], 25)
        self.assertEqual(stats["overall_inclusion_rate"], 50.0)

    def test_validate_status_transition(self):
        """Test status transition validation."""
        # Valid transition
        is_valid, error = validate_status_transition(self.session1, "defining_search")
        self.assertTrue(is_valid)
        self.assertIsNone(error)

        # Invalid transition
        is_valid, error = validate_status_transition(self.session1, "completed")
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_transition_session_status(self):
        """Test safe status transition."""
        success, error = transition_session_status(
            self.session1, "defining_search", self.user
        )

        self.assertTrue(success)
        self.assertIsNone(error)

        # Refresh from database
        self.session1.refresh_from_db()
        self.assertEqual(self.session1.status, "defining_search")

        # Check activity was logged
        activities = SessionActivity.objects.filter(session=self.session1)
        self.assertEqual(activities.count(), 1)

    def test_calculate_workflow_progress(self):
        """Test workflow progress calculation."""
        progress = calculate_workflow_progress(self.session2)

        self.assertIn("current_step", progress)
        self.assertIn("total_steps", progress)
        self.assertIn("percentage", progress)
        self.assertTrue(progress["is_complete"])
        self.assertFalse(progress["is_archived"])

    def test_get_dashboard_summary(self):
        """Test dashboard summary data."""
        summary = get_dashboard_summary(self.user)

        self.assertEqual(summary["total_sessions"], 2)
        self.assertEqual(summary["draft_sessions"], 1)
        self.assertEqual(summary["completed_sessions"], 1)
        self.assertEqual(summary["total_results_across_sessions"], 50)
