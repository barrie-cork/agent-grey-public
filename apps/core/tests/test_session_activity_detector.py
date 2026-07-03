"""
Tests for SessionActivityDetector service.

Tests the adaptive monitoring intervals based on session state and activity.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.services.session_activity_detector import SessionActivityDetector
from apps.review_manager.models import SearchSession, SessionActivity
from apps.core.tests.utils import create_test_user

User = get_user_model()


class SessionActivityDetectorTest(TestCase):
    """Test SessionActivityDetector adaptive monitoring"""

    def setUp(self):
        """Set up test data"""
        self.user = create_test_user()

        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests"""
        cache.clear()

    def test_active_state_monitoring_interval(self):
        """Test that active states (executing, processing_results) get short intervals"""
        # Create session in executing state
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        interval = SessionActivityDetector.get_monitoring_interval(session)

        # Active states should have 30 second interval
        self.assertEqual(interval, 30)

    def test_review_state_base_interval(self):
        """Test that review states get base interval without recent activity"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="under_review"
        )

        interval = SessionActivityDetector.get_monitoring_interval(session)

        # Review states with no activity should use low-frequency interval
        self.assertEqual(interval, 3600)  # 1 hour

    def test_review_state_with_recent_activity(self):
        """Test that review states with recent activity get shorter intervals"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="under_review"
        )

        # Create recent activity
        SessionActivity.log_activity(
            session=session,
            activity_type="status_changed",
            description="Status changed to under_review",
            user=self.user,
        )

        # Manually set cache to simulate recent activity
        cache_key = f"review_activity:{session.id}"
        cache.set(cache_key, timezone.now(), timeout=3600)

        interval = SessionActivityDetector.get_monitoring_interval(session)

        # Should get recent activity interval (5 minutes)
        self.assertEqual(interval, 300)

    def test_dormant_state_no_monitoring(self):
        """Test that dormant states (completed, archived) get no monitoring"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="completed"
        )

        interval = SessionActivityDetector.get_monitoring_interval(session)

        # Dormant states should return None (no monitoring)
        self.assertIsNone(interval)

    def test_setup_state_moderate_interval(self):
        """Test that setup states get moderate intervals"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )

        interval = SessionActivityDetector.get_monitoring_interval(session)

        # Setup states should have 5 minute interval
        self.assertEqual(interval, 300)

    def test_should_monitor_session_first_time(self):
        """Test that sessions are monitored on first check"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        should_monitor = SessionActivityDetector.should_monitor_session(session)

        self.assertTrue(should_monitor)

    def test_should_monitor_session_interval_not_elapsed(self):
        """Test that sessions are not monitored if interval hasn't elapsed"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        # Set last monitored timestamp
        cache_key = f"last_monitor:{session.id}"
        cache.set(cache_key, timezone.now(), timeout=120)

        should_monitor = SessionActivityDetector.should_monitor_session(session)

        # Should not monitor because interval (30s) hasn't elapsed
        self.assertFalse(should_monitor)

    def test_should_monitor_session_interval_elapsed(self):
        """Test that sessions are monitored once interval has elapsed"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        # Set last monitored timestamp to 60 seconds ago
        cache_key = f"last_monitor:{session.id}"
        past_time = timezone.now() - timedelta(seconds=60)
        cache.set(cache_key, past_time, timeout=120)

        should_monitor = SessionActivityDetector.should_monitor_session(session)

        # Should monitor because 60s > 30s interval
        self.assertTrue(should_monitor)

    def test_should_monitor_dormant_session(self):
        """Test that dormant sessions are never monitored"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="archived"
        )

        should_monitor = SessionActivityDetector.should_monitor_session(session)

        # Dormant sessions should never be monitored
        self.assertFalse(should_monitor)

    def test_update_last_monitored(self):
        """Test updating last monitored timestamp"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="executing"
        )

        # Update last monitored
        SessionActivityDetector.update_last_monitored(session)

        # Check that timestamp was cached
        cache_key = f"last_monitor:{session.id}"
        last_monitor = cache.get(cache_key)

        self.assertIsNotNone(last_monitor)
        self.assertIsInstance(last_monitor, timezone.datetime)

    def test_update_last_monitored_dormant_session(self):
        """Test that dormant sessions don't get cache entries"""
        session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="completed"
        )

        # Try to update last monitored
        SessionActivityDetector.update_last_monitored(session)

        # Check that no timestamp was cached
        cache_key = f"last_monitor:{session.id}"
        last_monitor = cache.get(cache_key)

        self.assertIsNone(last_monitor)

    def test_get_session_statistics(self):
        """Test retrieving session statistics"""
        stats = SessionActivityDetector.get_session_statistics()

        # Check that stats contain expected keys
        self.assertIn("total_statuses", stats)
        self.assertIn("active_monitoring_statuses", stats)
        self.assertIn("dormant_statuses", stats)
        self.assertIn("min_interval", stats)
        self.assertIn("max_interval", stats)
        self.assertIn("active_states", stats)
        self.assertIn("review_states", stats)
        self.assertIn("dormant_states", stats)

        # Check that counts make sense
        self.assertGreater(stats["total_statuses"], 0)
        self.assertEqual(
            stats["total_statuses"],
            stats["active_monitoring_statuses"] + stats["dormant_statuses"],
        )

    def test_health_check(self):
        """Test health check functionality"""
        health = SessionActivityDetector.health_check()

        # Check that health check returns expected keys
        self.assertIn("healthy", health)
        self.assertIn("cache_working", health)
        self.assertIn("total_statuses_configured", health)
        self.assertIn("adaptive_monitoring_enabled", health)

        # Check that health is True (cache should be working in tests)
        self.assertTrue(health["healthy"])
        self.assertTrue(health["cache_working"])
        self.assertTrue(health["adaptive_monitoring_enabled"])

    def test_monitoring_interval_by_status_string(self):
        """Test that monitoring intervals work with status strings"""
        # Test with status string instead of session object
        interval = SessionActivityDetector.get_monitoring_interval("executing")
        self.assertEqual(interval, 30)

        interval = SessionActivityDetector.get_monitoring_interval("under_review")
        self.assertEqual(interval, 3600)  # No activity data available

        interval = SessionActivityDetector.get_monitoring_interval("completed")
        self.assertIsNone(interval)

    def test_state_categories(self):
        """Test that state categories are correctly defined"""
        detector = SessionActivityDetector()

        # Check active states
        self.assertIn("executing", detector.ACTIVE_STATES)
        self.assertIn("processing_results", detector.ACTIVE_STATES)

        # Check review states
        self.assertIn("under_review", detector.REVIEW_STATES)
        self.assertIn("ready_for_review", detector.REVIEW_STATES)

        # Check dormant states
        self.assertIn("completed", detector.DORMANT_STATES)
        self.assertIn("archived", detector.DORMANT_STATES)

        # Check setup states
        self.assertIn("draft", detector.SETUP_STATES)
        self.assertIn("defining_search", detector.SETUP_STATES)
        self.assertIn("ready_to_execute", detector.SETUP_STATES)

    def test_backwards_compatibility_alias(self):
        """Test that SimpleSessionActivityDetector alias works"""
        from apps.core.services.session_activity_detector import (
            SimpleSessionActivityDetector,
        )

        # Should be the same class
        self.assertEqual(SimpleSessionActivityDetector, SessionActivityDetector)
