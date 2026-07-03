"""Tests for unified progress tracker."""

import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.core.progress.tracker import ProgressTracker


class ProgressTrackerTests(TestCase):
    """Test progress tracking functionality."""

    def setUp(self):
        """Set up test data."""
        self.tracker = ProgressTracker()
        self.session_id = str(uuid.uuid4())
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    def test_valid_components_defined(self):
        """Test that valid components are defined."""
        self.assertIn("executing", self.tracker.VALID_COMPONENTS)
        self.assertIn("processing_results", self.tracker.VALID_COMPONENTS)
        self.assertIn("deduplication", self.tracker.VALID_COMPONENTS)
        self.assertIn("completed", self.tracker.VALID_COMPONENTS)

    @patch("apps.core.state_machine.event_bus.event_bus.emit")
    def test_update_progress_stores_status(self, mock_emit):
        """Test that update_progress stores status in cache."""
        self.tracker.update_progress(
            session_id=self.session_id,
            component="executing",
            processed_count=5,
            total_count=10,
            current_step="Processing query 5/10",
        )

        # Check cache
        cache_key = f"progress:{self.session_id}"
        progress_data = cache.get(cache_key)

        self.assertIsNotNone(progress_data)
        self.assertIn("executing", progress_data)
        self.assertEqual(progress_data["executing"]["processed"], 5)
        self.assertEqual(progress_data["executing"]["total"], 10)
        self.assertEqual(
            progress_data["executing"]["current_step"], "Processing query 5/10"
        )

    @patch("apps.core.state_machine.event_bus.event_bus.emit")
    def test_update_progress_emits_event(self, mock_emit):
        """Test that updating progress emits an event."""
        self.tracker.update_progress(
            session_id=self.session_id,
            component="executing",
            processed_count=5,
            total_count=10,
            current_step="Processing query 5/10",
        )

        mock_emit.assert_called_once()

        event = mock_emit.call_args[0][0]
        self.assertEqual(event.session_id, self.session_id)
        self.assertEqual(event.component, "executing")
        self.assertEqual(event.processed_count, 5)
        self.assertEqual(event.total_count, 10)

    @patch("apps.core.state_machine.event_bus.event_bus.emit")
    def test_get_progress(self, mock_emit):
        """Test retrieving session progress."""
        # Update progress for multiple components
        self.tracker.update_progress(
            session_id=self.session_id,
            component="executing",
            processed_count=10,
            total_count=10,
        )

        self.tracker.update_progress(
            session_id=self.session_id,
            component="processing_results",
            processed_count=50,
            total_count=100,
        )

        progress = self.tracker.get_progress(self.session_id)

        self.assertEqual(progress["status"], "active")
        self.assertIn("executing", progress["components"])
        self.assertIn("processing_results", progress["components"])

    @patch("apps.core.state_machine.event_bus.event_bus.emit")
    def test_reset_progress(self, mock_emit):
        """Test resetting session progress."""
        self.tracker.update_progress(
            session_id=self.session_id,
            component="executing",
            processed_count=5,
            total_count=10,
        )

        progress = self.tracker.get_progress(self.session_id)
        self.assertEqual(progress["status"], "active")

        self.tracker.reset_progress(self.session_id)

        progress = self.tracker.get_progress(self.session_id)
        self.assertEqual(progress["status"], "unknown")
        self.assertEqual(progress["components"], {})

    def test_get_progress_no_data(self):
        """Test getting progress for a session with no data."""
        progress = self.tracker.get_progress(self.session_id)

        self.assertEqual(progress["status"], "unknown")
        self.assertEqual(progress["processed_count"], 0)
        self.assertEqual(progress["total_count"], 0)
        self.assertEqual(progress["components"], {})

    @patch("apps.core.state_machine.event_bus.event_bus.emit")
    def test_update_progress_with_metadata(self, mock_emit):
        """Test update_progress with metadata."""
        self.tracker.update_progress(
            session_id=self.session_id,
            component="executing",
            processed_count=3,
            total_count=10,
            metadata={"query_id": "abc123"},
        )

        event = mock_emit.call_args[0][0]
        self.assertEqual(event.metadata, {"query_id": "abc123"})

    @patch("apps.core.state_machine.event_bus.event_bus.emit")
    def test_update_progress_unknown_component_warns(self, mock_emit):
        """Test that unknown components log a warning."""
        with self.assertLogs("apps.core.progress.tracker", level="WARNING") as logs:
            self.tracker.update_progress(
                session_id=self.session_id,
                component="nonexistent_phase",
                processed_count=0,
                total_count=0,
            )

        self.assertTrue(any("Unknown component" in log for log in logs.output))
