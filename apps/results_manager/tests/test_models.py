"""
Tests for results_manager models.

Tests for ProcessedResult and ProcessingSession models
including result processing and processing tracking.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.review_manager.models import SearchSession

from ..models import ProcessedResult, ProcessingSession
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ProcessedResultModelTests(TestCase):
    """Test cases for ProcessedResult model."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )

    def test_processed_result_creation(self):
        """Test creating a processed result."""
        result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            snippet="Test snippet content",
        )

        self.assertEqual(result.title, "Test Result")
        self.assertEqual(result.url, "https://example.com/test")
        self.assertFalse(result.is_reviewed)
        self.assertEqual(result.review_priority, 0)

    def test_year_extraction_from_date(self):
        """Test automatic year extraction from publication date."""
        from datetime import date

        result = ProcessedResult.objects.create(
            session=self.session,
            title="Test Result",
            url="https://example.com/test",
            publication_date=date(2023, 6, 15),
        )

        result.save()
        self.assertEqual(result.publication_year, 2023)


class ProcessingSessionModelTests(TestCase):
    """Test cases for ProcessingSession model."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user
        )

    def test_processing_session_creation(self):
        """Test creating a processing session."""
        processing_session = ProcessingSession.objects.create(
            search_session=self.session
        )

        self.assertEqual(processing_session.status, "pending")
        self.assertEqual(processing_session.processed_count, 0)
        self.assertEqual(processing_session.error_count, 0)
        self.assertEqual(processing_session.duplicate_count, 0)
        self.assertIsNone(processing_session.started_at)

    def test_start_processing(self):
        """Test starting processing updates status and timestamps."""
        processing_session = ProcessingSession.objects.create(
            search_session=self.session
        )

        processing_session.start_processing(
            total_raw_results=100, celery_task_id="test-task-123"
        )

        self.assertEqual(processing_session.status, "in_progress")
        self.assertEqual(processing_session.total_raw_results, 100)
        self.assertEqual(processing_session.celery_task_id, "test-task-123")
        self.assertEqual(processing_session.current_stage, "initialization")
        self.assertIsNotNone(processing_session.started_at)

    def test_progress_percentage_calculation(self):
        """Test progress percentage calculation."""
        processing_session = ProcessingSession.objects.create(
            search_session=self.session, total_raw_results=100, processed_count=25
        )

        self.assertEqual(processing_session.progress_percentage, 25)

        # Test edge case with zero total
        processing_session.total_raw_results = 0
        self.assertEqual(processing_session.progress_percentage, 0)

    def test_update_progress(self):
        """Test updating progress with stage and counts."""
        processing_session = ProcessingSession.objects.create(
            search_session=self.session
        )

        processing_session.update_progress(
            stage="deduplication",
            stage_progress=50,
            processed_count=75,
            duplicate_count=10,
        )

        self.assertEqual(processing_session.current_stage, "deduplication")
        self.assertEqual(processing_session.stage_progress, 50)
        self.assertEqual(processing_session.processed_count, 75)
        self.assertEqual(processing_session.duplicate_count, 10)
        self.assertIsNotNone(processing_session.last_heartbeat)

    def test_add_error(self):
        """Test adding errors to processing session."""
        processing_session = ProcessingSession.objects.create(
            search_session=self.session
        )

        processing_session.add_error(
            error_message="Test error",
            error_details={"type": "validation_error", "field": "url"},
        )

        self.assertEqual(processing_session.error_count, 1)
        self.assertEqual(len(processing_session.error_details), 1)

        error = processing_session.error_details[0]
        self.assertEqual(error["message"], "Test error")
        self.assertEqual(error["details"]["type"], "validation_error")

    def test_complete_processing(self):
        """Test completing processing updates status and completion time."""
        processing_session = ProcessingSession.objects.create(
            search_session=self.session
        )
        processing_session.start_processing(total_raw_results=100)

        processing_session.complete_processing()

        self.assertEqual(processing_session.status, "completed")
        self.assertEqual(processing_session.current_stage, "finalization")
        self.assertEqual(processing_session.stage_progress, 100)
        self.assertIsNotNone(processing_session.completed_at)

    def test_fail_processing(self):
        """Test failing processing updates status and adds error."""
        processing_session = ProcessingSession.objects.create(
            search_session=self.session
        )

        processing_session.fail_processing(
            error_message="Critical failure",
            error_details={"exception": "DatabaseError"},
        )

        self.assertEqual(processing_session.status, "failed")
        self.assertIsNotNone(processing_session.completed_at)
        self.assertEqual(processing_session.error_count, 1)
        self.assertEqual(
            processing_session.error_details[0]["message"], "Critical failure"
        )
