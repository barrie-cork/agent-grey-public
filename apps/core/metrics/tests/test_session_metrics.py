"""
Tests for session workflow metrics instrumentation.

Tests transition recording, duration calculation, and state distribution updates.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from prometheus_client import REGISTRY

from apps.core.metrics.session_metrics import (
    calculate_state_duration,
    record_session_transition,
    update_session_state_distribution,
)
from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession, SessionActivity

User = get_user_model()


class SessionMetricsTest(TestCase):
    """Test cases for session metrics functions."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

    def test_update_session_state_distribution(self):
        """Test updating session state distribution gauge."""
        # Create sessions in different states
        SearchSession.objects.create(
            title="Draft Session", owner=self.user, status="draft"
        )
        SearchSession.objects.create(
            title="Executing Session", owner=self.user, status="executing"
        )

        # Update distribution
        update_session_state_distribution()

        # Check gauge values
        draft_count = REGISTRY.get_sample_value(
            "agent_grey_session_state", {"state": "draft"}
        )
        executing_count = REGISTRY.get_sample_value(
            "agent_grey_session_state", {"state": "executing"}
        )

        # Should have at least the sessions we created
        self.assertIsNotNone(draft_count)
        self.assertIsNotNone(executing_count)
        self.assertGreaterEqual(draft_count, 1.0)
        self.assertGreaterEqual(executing_count, 1.0)

    def test_record_session_transition_increments_counter(self):
        """Test recording transition increments counter."""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )

        # Get counter before
        before = REGISTRY.get_sample_value(
            "agent_grey_session_transitions_total",
            {"from_state": "draft", "to_state": "defining_search", "success": "true"},
        )
        if before is None:
            before = 0

        # Record transition
        record_session_transition(
            session,
            from_state="draft",
            to_state="defining_search",
            success=True,
            duration_seconds=10.5,
        )

        # Get counter after
        after = REGISTRY.get_sample_value(
            "agent_grey_session_transitions_total",
            {"from_state": "draft", "to_state": "defining_search", "success": "true"},
        )

        # Should increment by 1
        self.assertEqual(after - before, 1.0)

    def test_record_session_transition_with_duration(self):
        """Test transition recording with duration observation."""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        # Get count before
        count_before = REGISTRY.get_sample_value(
            "agent_grey_session_state_duration_seconds_count", {"state": "executing"}
        )
        if count_before is None:
            count_before = 0

        # Record transition with duration
        record_session_transition(
            session,
            from_state="executing",
            to_state="completed",
            success=True,
            duration_seconds=120.5,
        )

        # Check histogram count incremented
        count_after = REGISTRY.get_sample_value(
            "agent_grey_session_state_duration_seconds_count", {"state": "executing"}
        )
        self.assertIsNotNone(count_after)
        self.assertGreater(count_after, count_before)

    def test_calculate_state_duration_with_activity(self):
        """Test duration calculation from SessionActivity."""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        # Create activity 60 seconds ago
        past_time = timezone.now() - timedelta(seconds=60)
        activity = SessionActivity.objects.create(
            session=session,
            activity_type="state_change",
            description="State changed to executing",
            metadata={"to_state": "executing"},
        )
        # Update created_at to simulate past activity
        activity.created_at = past_time
        activity.save()

        # Calculate duration
        duration = calculate_state_duration(session, "executing")

        # Should be approximately 60 seconds (allow 5s tolerance)
        self.assertIsNotNone(duration)
        self.assertGreaterEqual(duration, 55)
        self.assertLessEqual(duration, 65)

    def test_calculate_state_duration_fallback_to_created_at(self):
        """Test duration calculation falls back to created_at for draft state."""
        # Create session 30 seconds ago
        past_time = timezone.now() - timedelta(seconds=30)
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )
        session.created_at = past_time
        session.save()

        # Calculate duration for draft state (no activity exists)
        duration = calculate_state_duration(session, "draft")

        # Should be approximately 30 seconds (allow tolerance)
        self.assertIsNotNone(duration)
        self.assertGreaterEqual(duration, 25)
        self.assertLessEqual(duration, 35)

    def test_calculate_state_duration_returns_none_for_no_data(self):
        """Test duration calculation returns None when no data available."""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        # Try to calculate duration for state that never existed
        duration = calculate_state_duration(session, "completed")

        self.assertIsNone(duration)

    def test_record_transition_handles_errors_gracefully(self):
        """Test transition recording doesn't raise on errors."""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )

        # Mock update_session_state_distribution to raise error
        with patch(
            "apps.core.metrics.session_metrics.update_session_state_distribution"
        ) as mock_update:
            mock_update.side_effect = Exception("Database error")

            # Should not raise
            try:
                record_session_transition(
                    session, from_state="draft", to_state="defining_search"
                )
            except Exception as e:
                self.fail(f"record_session_transition raised {e}")
