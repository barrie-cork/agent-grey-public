"""
Tests for validation functions in results_manager app.

This module tests the validation functions that were extracted
from tasks to improve code organisation.
"""

from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.tests.utils import create_test_user

from apps.results_manager.validation import (
    get_or_create_processing_record,
    validate_batch_processing_params,
    validate_session_for_processing,
    validate_session_id,
)
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution

User = get_user_model()


class TestValidateSessionForProcessing(TestCase):
    """Test the validate_session_for_processing function."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Validation Session",
            owner=self.user,
            status="processing_results",
        )
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["test"],
            context_terms=["test"],
        )
        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
        )
        self.execution = SearchExecution.objects.create(
            query=self.query,
            status="completed",
        )

    def test_valid_session(self):
        """Test validation passes for a valid session with results."""
        # Create some raw results
        for i in range(3):
            RawSearchResult.objects.create(
                execution=self.execution,
                title=f"Result {i}",
                link=f"https://example.com/{i}",
                snippet=f"Snippet {i}",
                position=i + 1,
            )

        # Should not raise any exception
        validate_session_for_processing(self.session)

    def test_invalid_status(self):
        """Test validation fails for incorrect status."""
        self.session.status = "draft"
        SearchSession.objects.filter(id=self.session.id).update(status="draft")
        self.session.refresh_from_db()

        with self.assertRaises(ValueError) as context:
            validate_session_for_processing(self.session)

        self.assertIn("Session not in valid processing status", str(context.exception))
        self.assertIn("draft", str(context.exception))

    def test_missing_search_strategy(self):
        """Test validation fails when search strategy is missing."""
        # Create a session without a strategy
        no_strategy_session = SearchSession.objects.create(
            title="No Strategy Session",
            owner=self.user,
            status="processing_results",
        )

        with self.assertRaises(ValueError) as context:
            validate_session_for_processing(no_strategy_session)

        self.assertIn("Session missing search strategy", str(context.exception))

    def test_zero_raw_results_passes(self):
        """Test validation passes with zero results (Issue #51 fix)."""
        # Session has strategy but no raw results
        # Should NOT raise - zero results is valid
        validate_session_for_processing(self.session)

    def test_ready_for_review_status_accepted(self):
        """Test validation accepts ready_for_review status."""
        SearchSession.objects.filter(id=self.session.id).update(
            status="ready_for_review"
        )
        self.session.refresh_from_db()

        # Should not raise
        validate_session_for_processing(self.session)


class TestValidateSessionId(TestCase):
    """Test the validate_session_id function."""

    def test_valid_uuid(self):
        """Test validation passes for a valid UUID."""
        valid_uuid = str(uuid4())
        # Should not raise any exception
        validate_session_id(valid_uuid)

    def test_empty_session_id(self):
        """Test validation fails for empty session ID."""
        with self.assertRaises(ValueError) as context:
            validate_session_id("")

        self.assertIn("Session ID is required", str(context.exception))

    def test_none_session_id(self):
        """Test validation fails for None session ID."""
        with self.assertRaises(ValueError) as context:
            validate_session_id(None)  # type: ignore[arg-type]

        self.assertIn("Session ID is required", str(context.exception))

    def test_invalid_uuid_format(self):
        """Test validation fails for invalid UUID format."""
        invalid_uuids = [
            "not-a-uuid",
            "12345",
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "g1234567-1234-1234-1234-123456789012",  # invalid character
            "12345678-1234-1234-1234-12345678901",  # too short
            "12345678-1234-1234-1234-1234567890123",  # too long
        ]

        for invalid_uuid in invalid_uuids:
            with self.assertRaises(ValueError) as context:
                validate_session_id(invalid_uuid)

            self.assertIn("Invalid UUID format", str(context.exception))


class TestGetOrCreateProcessingRecord(TestCase):
    """Test the get_or_create_processing_record function."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Processing Record",
            owner=self.user,
            status="processing_results",
        )

    def test_create_new_record(self):
        """Test creating a new processing record."""
        from apps.results_manager.models import ProcessingSession

        record = get_or_create_processing_record(self.session)

        self.assertIsInstance(record, ProcessingSession)
        self.assertEqual(record.search_session, self.session)
        self.assertEqual(record.status, "pending")

    def test_get_existing_record(self):
        """Test getting an existing processing record."""
        from apps.results_manager.models import ProcessingSession

        # Create an existing record
        existing = ProcessingSession.objects.create(
            search_session=self.session,
            status="in_progress",
        )

        record = get_or_create_processing_record(self.session)

        self.assertEqual(record.id, existing.id)
        self.assertEqual(record.status, "in_progress")


class TestValidateBatchProcessingParams(TestCase):
    """Test the validate_batch_processing_params function."""

    def test_valid_params(self):
        """Test validation passes for valid parameters."""
        # Should not raise any exception
        validate_batch_processing_params(
            batch_size=50, start_index=0, total_results=100
        )

        # Test with start_index in middle
        validate_batch_processing_params(
            batch_size=25, start_index=50, total_results=100
        )

    def test_invalid_batch_size(self):
        """Test validation fails for invalid batch size."""
        # Zero batch size
        with self.assertRaises(ValueError) as context:
            validate_batch_processing_params(
                batch_size=0, start_index=0, total_results=100
            )
        self.assertIn("Batch size must be positive", str(context.exception))

        # Negative batch size
        with self.assertRaises(ValueError) as context:
            validate_batch_processing_params(
                batch_size=-10, start_index=0, total_results=100
            )
        self.assertIn("Batch size must be positive", str(context.exception))

    def test_negative_start_index(self):
        """Test validation fails for negative start index."""
        with self.assertRaises(ValueError) as context:
            validate_batch_processing_params(
                batch_size=50, start_index=-1, total_results=100
            )
        self.assertIn("Start index must be non-negative", str(context.exception))

    def test_negative_total_results(self):
        """Test validation fails for negative total results."""
        with self.assertRaises(ValueError) as context:
            validate_batch_processing_params(
                batch_size=50, start_index=0, total_results=-10
            )
        self.assertIn("Total results must be non-negative", str(context.exception))

    def test_start_index_exceeds_total(self):
        """Test validation fails when start index exceeds total results."""
        with self.assertRaises(ValueError) as context:
            validate_batch_processing_params(
                batch_size=50, start_index=100, total_results=100
            )
        self.assertIn(
            "Start index (100) must be less than total results (100)",
            str(context.exception),
        )

    def test_edge_case_zero_total_results(self):
        """Test validation with zero total results."""
        # Should not raise exception when total_results is 0
        validate_batch_processing_params(batch_size=50, start_index=0, total_results=0)
