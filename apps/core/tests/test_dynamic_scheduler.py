"""
Tests for dynamic_scheduler tasks.

Tests the adaptive session monitoring and consolidated maintenance tasks.
"""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase

from apps.core.services.session_activity_detector import SessionActivityDetector
from apps.core.tasks.dynamic_scheduler import (
    _monitor_session,
    adaptive_session_monitor,
    consolidated_maintenance_task,
    monitoring_statistics,
)
from apps.core.tests.utils import create_test_user
from apps.review_manager.models import SearchSession

User = get_user_model()


class AdaptiveSessionMonitorTest(TestCase):
    """Test adaptive_session_monitor task"""

    def setUp(self):
        """Set up test data"""
        self.user = create_test_user()
        cache.clear()

    def tearDown(self):
        """Clean up after tests"""
        cache.clear()

    def test_adaptive_session_monitor_with_active_sessions(self):
        """Test monitoring with active sessions"""
        # Create active session
        _session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        # Run monitor
        result = adaptive_session_monitor()  # type: ignore[call-arg]

        # Verify result structure
        self.assertEqual(result["status"], "success")
        self.assertGreater(result["monitored_sessions"], 0)
        self.assertIn("total_active", result)
        self.assertIn("timestamp", result)

    def test_adaptive_session_monitor_no_active_sessions(self):
        """Test monitoring with no active sessions (all dormant)"""
        # Create dormant session
        SearchSession.objects.create(
            title="Completed Session", owner=self.user, status="completed"
        )

        # Run monitor
        result = adaptive_session_monitor()  # type: ignore[call-arg]

        # Should skip - no active sessions
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "no_active_sessions")

    def test_adaptive_session_monitor_skips_dormant_sessions(self):
        """Test that dormant sessions are not included in monitoring"""
        # Create mix of sessions
        SearchSession.objects.create(
            title="Active", owner=self.user, status="executing"
        )
        SearchSession.objects.create(
            title="Dormant", owner=self.user, status="completed"
        )
        SearchSession.objects.create(
            title="Archived", owner=self.user, status="archived"
        )

        # Run monitor
        result = adaptive_session_monitor()  # type: ignore[call-arg]

        # Should only monitor active session
        self.assertEqual(result["total_active"], 1)

    def test_adaptive_session_monitor_interval_not_elapsed(self):
        """Test that sessions are skipped if interval hasn't elapsed"""
        _session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        # Run monitor first time
        result1 = adaptive_session_monitor()  # type: ignore[call-arg]
        self.assertGreater(result1["monitored_sessions"], 0)

        # Run immediately again
        result2 = adaptive_session_monitor()  # type: ignore[call-arg]

        # Should be skipped
        self.assertEqual(result2["skipped_sessions"], 1)
        self.assertEqual(result2["monitored_sessions"], 0)

    def test_adaptive_session_monitor_efficiency_ratio(self):
        """Test efficiency ratio calculation"""
        # Create sessions
        for i in range(5):
            SearchSession.objects.create(
                title=f"Session {i}", owner=self.user, status="under_review"
            )

        # Run monitor
        result = adaptive_session_monitor()  # type: ignore[call-arg]

        # Verify efficiency ratio format
        self.assertIn("efficiency_ratio", result)
        self.assertRegex(result["efficiency_ratio"], r"\d+/\d+")


class MonitorSessionTest(TestCase):
    """Test _monitor_session helper function"""

    def setUp(self):
        """Set up test data"""
        self.user = create_test_user()
        self.detector = SessionActivityDetector()

    def test_monitor_session_active_state_health_check(self):
        """Test monitoring active state runs health check via recovery_service."""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        result = _monitor_session(session, self.detector)

        self.assertEqual(result["status"], "executing")
        self.assertIn("action_taken", result)
        # Health check runs successfully or falls back gracefully
        self.assertIn(
            result["action_taken"],
            ("health_check_performed", "health_issues_found", "status_checked"),
        )

    def test_monitor_session_review_state_validation(self):
        """Test monitoring review state validates status"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="under_review"
        )

        result = _monitor_session(session, self.detector)

        # Review states get validation action
        self.assertEqual(result["action_taken"], "status_validated")
        self.assertEqual(result["status"], "under_review")

    def test_monitor_session_setup_state(self):
        """Test monitoring setup state"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )

        result = _monitor_session(session, self.detector)

        # Setup states get basic validation
        self.assertEqual(result["action_taken"], "validated")
        self.assertIn("interval", result)

    def test_monitor_session_error_handling(self):
        """Test error handling in _monitor_session"""
        # Create invalid session mock
        session = Mock()
        session.id = "test-id"
        session.status = "executing"

        # Mock get_monitoring_interval to raise a ValueError - must match the
        # specific exception types caught by the handler (DatabaseError, AttributeError, ValueError)
        with patch.object(
            self.detector,
            "get_monitoring_interval",
            side_effect=ValueError("Test error"),
        ):
            result = _monitor_session(session, self.detector)

            # Should return error dict
            self.assertIn("error", result)
            self.assertEqual(result["error_type"], "ValueError")


class ConsolidatedMaintenanceTest(TestCase):
    """Test consolidated_maintenance_task"""

    def setUp(self):
        """Set up test data"""
        self.user = create_test_user()

    def test_consolidated_maintenance_task_success(self):
        """Test successful maintenance task execution"""
        # Create test sessions
        SearchSession.objects.create(
            title="Active", owner=self.user, status="executing"
        )
        SearchSession.objects.create(
            title="Review", owner=self.user, status="under_review"
        )

        # Run task
        result = consolidated_maintenance_task()

        # Verify result structure
        self.assertEqual(result["status"], "success")
        self.assertIn("tasks_run", result)
        self.assertGreater(len(result["tasks_run"]), 0)

    def test_consolidated_maintenance_task_counts_sessions(self):
        """Test that maintenance task counts sessions correctly"""
        # Create sessions
        SearchSession.objects.create(
            title="Active", owner=self.user, status="processing_results"
        )
        SearchSession.objects.create(
            title="Review", owner=self.user, status="ready_for_review"
        )

        # Run task
        result = consolidated_maintenance_task()

        # Find session validation task
        validation_task = next(
            (t for t in result["tasks_run"] if t["task"] == "session_state_validation"),
            None,
        )

        self.assertIsNotNone(validation_task)
        assert validation_task is not None
        self.assertEqual(validation_task["status"], "completed")
        self.assertEqual(validation_task["active_sessions"], 1)
        self.assertEqual(validation_task["review_sessions"], 1)

    def test_consolidated_maintenance_task_error_handling(self):
        """Test error handling in maintenance task when sub-task fails."""
        # Mock SearchSession to raise a DB error - must match the specific
        # exception types caught by the sub-task handler (DatabaseError, AttributeError)
        with patch(
            "apps.review_manager.models.SearchSession.objects.filter",
            side_effect=DatabaseError("DB error"),
        ):
            result = consolidated_maintenance_task()

            # Overall status remains "success" because individual sub-task
            # failures are caught and recorded (not propagated)
            self.assertEqual(result["status"], "success")
            # But the session_state_validation sub-task should show "failed"
            validation_task = next(
                (
                    t
                    for t in result["tasks_run"]
                    if t["task"] == "session_state_validation"
                ),
                None,
            )
            self.assertIsNotNone(validation_task)
            assert validation_task is not None
            self.assertEqual(validation_task["status"], "failed")
            self.assertIn("DB error", validation_task["error"])


class MonitoringStatisticsTest(TestCase):
    """Test monitoring_statistics task"""

    def setUp(self):
        """Set up test data"""
        self.user = create_test_user()
        cache.clear()

    def tearDown(self):
        """Clean up cache"""
        cache.clear()

    def test_monitoring_statistics_calculation(self):
        """Test statistics calculation with various session states"""
        # Create mix of sessions
        SearchSession.objects.create(
            title="Active 1", owner=self.user, status="executing"
        )
        SearchSession.objects.create(
            title="Active 2", owner=self.user, status="processing_results"
        )
        SearchSession.objects.create(
            title="Review 1", owner=self.user, status="under_review"
        )
        SearchSession.objects.create(
            title="Review 2", owner=self.user, status="ready_for_review"
        )
        SearchSession.objects.create(
            title="Dormant", owner=self.user, status="completed"
        )
        SearchSession.objects.create(title="Setup", owner=self.user, status="draft")

        # Run statistics
        result = monitoring_statistics()

        # Verify counts
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["active_sessions"], 2)
        self.assertEqual(result["review_sessions"], 2)
        self.assertEqual(result["dormant_sessions"], 1)
        self.assertEqual(result["setup_sessions"], 1)
        self.assertEqual(result["total_sessions"], 6)

    def test_monitoring_statistics_efficiency_improvement(self):
        """Test efficiency improvement calculation"""
        # Create sessions that will show efficiency improvement
        for i in range(10):
            SearchSession.objects.create(
                title=f"Review {i}", owner=self.user, status="under_review"
            )

        # Run statistics
        result = monitoring_statistics()

        # Old system: 10 sessions × 120 monitors/hour = 1200
        # New system: 10 review × 12 monitors/hour = 120
        # Efficiency: (1200 - 120) / 1200 = 90%
        self.assertEqual(result["old_monitors_per_hour"], 1200)
        self.assertEqual(result["new_monitors_per_hour"], 120)
        self.assertEqual(result["efficiency_improvement_percent"], 90.0)

    def test_monitoring_statistics_caching(self):
        """Test that statistics are cached"""
        # Create session
        SearchSession.objects.create(title="Test", owner=self.user, status="executing")

        # Run statistics
        result = monitoring_statistics()

        # Verify cached
        cached_stats = cache.get("monitoring_statistics")
        self.assertIsNotNone(cached_stats)
        self.assertEqual(cached_stats["total_sessions"], result["total_sessions"])

    def test_monitoring_statistics_zero_sessions(self):
        """Test statistics with no sessions"""
        # Run with no sessions
        result = monitoring_statistics()

        # Should handle gracefully
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total_sessions"], 0)
        self.assertEqual(result["efficiency_improvement_percent"], 0)

    def test_monitoring_statistics_error_handling(self):
        """Test error handling in statistics task"""
        # Mock SearchSession to raise a DB error - patch at source since it's a local import
        with patch(
            "apps.review_manager.models.SearchSession.objects.filter",
            side_effect=DatabaseError("DB error"),
        ):
            result = monitoring_statistics()

            # Should handle error
            self.assertEqual(result["status"], "error")
            self.assertIn("error", result)
