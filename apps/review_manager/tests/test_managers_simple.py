"""
Simple tests for custom model managers in review_manager app.

Tests basic functionality without complex relationships.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.review_manager.models import SearchSession
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SearchSessionManagerSimpleTests(TestCase):
    """Test custom SearchSession manager methods with minimal setup."""

    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = create_test_user(username_prefix="test@example.com")

        # Create sessions without related models
        self.draft_session = SearchSession.objects.create(
            title="Draft Session",
            description="Test draft session",
            owner=self.user,
            status="draft",
            total_results=100,
            reviewed_results=20,
        )

        self.active_session = SearchSession.objects.create(
            title="Active Session",
            description="Test active session",
            owner=self.user,
            status="executing",
            total_results=200,
            reviewed_results=100,
        )

        self.completed_session = SearchSession.objects.create(
            title="Completed Session",
            description="Test completed session",
            owner=self.user,
            status="completed",
            total_results=150,
            reviewed_results=150,
        )

    def test_with_statistics_basic(self):
        """Test basic statistics annotation without related models."""
        sessions = SearchSession.objects.with_statistics()

        for session in sessions:
            # Check basic annotations exist
            self.assertTrue(hasattr(session, "pending_reviews"))
            self.assertTrue(hasattr(session, "completion_percentage"))

            # Verify pending_reviews calculation
            expected_pending = session.total_results - session.reviewed_results
            self.assertEqual(session.pending_reviews, expected_pending)

            # Verify completion percentage
            if session.total_results > 0:
                expected_percentage = (
                    session.reviewed_results * 100.0 / session.total_results
                )
                self.assertAlmostEqual(
                    session.completion_percentage, expected_percentage, places=2
                )

    def test_active_only_filter(self):
        """Test active_only() filter works correctly."""
        active_sessions = SearchSession.objects.active_only()

        # Should include draft and executing, not completed
        self.assertIn(self.draft_session, active_sessions)
        self.assertIn(self.active_session, active_sessions)
        self.assertNotIn(self.completed_session, active_sessions)

        # Check count
        self.assertEqual(active_sessions.count(), 2)

    def test_owned_by_filter(self):
        """Test owned_by() filter."""
        # Create another user with a session
        other_user = create_test_user(username_prefix="other@example.com")
        other_session = SearchSession.objects.create(
            title="Other User Session", owner=other_user, status="draft"
        )

        # Test filtering by user
        user_sessions = SearchSession.objects.owned_by(self.user)
        self.assertEqual(user_sessions.count(), 3)
        self.assertNotIn(other_session, user_sessions)

        # Test filtering by other user
        other_user_sessions = SearchSession.objects.owned_by(other_user)
        self.assertEqual(other_user_sessions.count(), 1)
        self.assertIn(other_session, other_user_sessions)

    def test_stuck_sessions(self):
        """Test stuck_sessions() detection."""
        # Make active session "stuck" by setting old updated_at
        old_time = timezone.now() - timedelta(hours=3)
        SearchSession.objects.filter(id=self.active_session.id).update(
            updated_at=old_time
        )

        # Check stuck sessions (default 2 hours)
        stuck = SearchSession.objects.stuck_sessions()
        self.assertEqual(stuck.count(), 1)
        self.assertEqual(stuck.first().id, self.active_session.id)

        # Check with custom threshold
        stuck_1hr = SearchSession.objects.stuck_sessions(hours=1)
        self.assertEqual(stuck_1hr.count(), 1)

        # Non-executing sessions shouldn't be considered stuck
        SearchSession.objects.filter(id=self.draft_session.id).update(
            updated_at=old_time
        )
        stuck_again = SearchSession.objects.stuck_sessions()
        self.assertEqual(stuck_again.count(), 1)  # Still only the executing one

    def test_get_status_summary(self):
        """Test status summary aggregation."""
        summary = SearchSession.objects.get_status_summary(user=self.user)

        self.assertEqual(summary["total_sessions"], 3)
        self.assertEqual(summary["draft_sessions"], 1)
        self.assertEqual(summary["completed_sessions"], 1)
        self.assertEqual(
            summary["active_sessions"], 2
        )  # Draft + executing (both are active)

        # Check totals
        self.assertEqual(summary["total_results_found"], 450)  # 100+200+150
        self.assertEqual(summary["total_results_reviewed"], 270)  # 20+100+150

    def test_manager_chaining(self):
        """Test that manager methods can be chained."""
        # Chain multiple filters
        sessions = (
            SearchSession.objects.owned_by(self.user).active_only().with_statistics()
        )

        self.assertEqual(sessions.count(), 2)

        # Verify statistics are still available
        for session in sessions:
            self.assertTrue(hasattr(session, "pending_reviews"))
            self.assertTrue(hasattr(session, "completion_percentage"))
