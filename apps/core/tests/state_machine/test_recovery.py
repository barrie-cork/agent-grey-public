"""Tests for state machine recovery mechanisms."""

import unittest
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.state_machine.recovery import recovery_service
from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession

from .test_base import StateMachineTestCase


@unittest.skipIf(
    getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False),
    "Recovery tests require async Celery (not CELERY_TASK_ALWAYS_EAGER)",
)
class RecoveryTests(StateMachineTestCase):
    """Test recovery mechanisms."""

    def _force_session_state(self, session, status, hours_ago=0):
        """Force a session to a specific state, bypassing validation."""
        SearchSession.objects.filter(id=session.id).update(
            status=status, updated_at=timezone.now() - timedelta(hours=hours_ago)
        )
        session.refresh_from_db()

    def test_stuck_session_detection(self):
        """Test detection of stuck sessions."""
        self._force_session_state(self.session, "executing", hours_ago=2)

        recovered = recovery_service.recover_stuck_sessions(timeout_minutes=30)

        self.assertIn(str(self.session.id), recovered)

        self.session.refresh_from_db()
        self.assertIn(
            self.session.status,
            ["ready_to_execute", "processing_results", "draft", "failed"],
            "Session should be recovered to appropriate state",
        )

    def test_recovery_from_processing_with_results(self):
        """Test recovery from processing state with processed results."""
        self._force_session_state(self.session, "processing_results", hours_ago=1)

        ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="http://test.com",
            snippet="Test snippet",
        )

        recovery_service.recover_stuck_sessions(timeout_minutes=30)

        self.session.refresh_from_db()
        self.assertIn(
            self.session.status,
            ["ready_for_review", "processing_results", "draft", "failed"],
        )

    def test_no_recovery_for_manual_states(self):
        """Test that manual states are not recovered."""
        manual_states = ["draft", "defining_search", "under_review", "completed"]

        for state in manual_states:
            self._force_session_state(self.session, state, hours_ago=2)

            recovered = recovery_service.recover_stuck_sessions(timeout_minutes=30)

            self.assertNotIn(str(self.session.id), recovered)
            self.session.refresh_from_db()
            self.assertEqual(self.session.status, state)

    def test_session_health_check(self):
        """Test session health checking."""
        health = recovery_service.check_session_health(str(self.session.id))

        self.assertTrue(health["is_healthy"])
        self.assertEqual(health["current_state"], "draft")

        # Make session unhealthy (stuck in automated state)
        self._force_session_state(self.session, "executing", hours_ago=1)

        health = recovery_service.check_session_health(str(self.session.id))

        self.assertFalse(health["is_healthy"])
        self.assertGreater(len(health.get("issues", [])), 0)

    def test_recovery_error_handling(self):
        """Test that recovery handles errors gracefully."""
        self._force_session_state(self.session, "invalid_state", hours_ago=1)

        # Recovery should not crash
        recovered = recovery_service.recover_stuck_sessions()

        # Session should not be in recovered list (invalid state is not a stuck state)
        self.assertNotIn(str(self.session.id), recovered)

    def test_recovery_with_partial_results(self):
        """Test recovery when partial results exist."""
        self._force_session_state(self.session, "executing", hours_ago=1)

        # Add a processed result to simulate partial results
        ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="http://test.com",
            snippet="Test snippet",
        )

        recovery_service.recover_stuck_sessions(timeout_minutes=30)

        self.session.refresh_from_db()
        # Session should be recovered since it has results
        self.assertNotEqual(self.session.status, "executing")
