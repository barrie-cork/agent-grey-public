"""
Tests for workflow validators.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.results_manager.models import ProcessedResult, ProcessingSession
from apps.review_manager.models import SearchSession
from apps.review_manager.validators import WorkflowValidator
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution
from apps.core.tests.utils import create_test_user

User = get_user_model()


class WorkflowValidatorTests(TestCase):
    """Test workflow validation rules."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="draft"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["Test population"],
            interest_terms=["Test interest"],
            context_terms=["Test context"],
        )

        self.validator = WorkflowValidator()

    def test_can_execute_with_no_queries(self):
        """Test execution validation fails without queries."""
        can_execute, reason = self.validator.can_execute(self.session)

        self.assertFalse(can_execute)
        self.assertIn("No active queries", reason)

    def test_can_execute_with_active_queries(self):
        """Test execution validation passes with active queries."""
        # Add active query
        SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            is_active=True,
        )

        can_execute, reason = self.validator.can_execute(self.session)

        self.assertTrue(can_execute)
        self.assertIsNone(reason)

    def test_can_execute_with_existing_executions(self):
        """Test execution validation fails with pending executions."""
        # Add query and execution
        query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            is_active=True,
        )

        SearchExecution.objects.create(
            query=query, initiated_by=self.user, status="pending"
        )

        can_execute, reason = self.validator.can_execute(self.session)

        self.assertFalse(can_execute)
        self.assertIn("executions already in progress", reason)

    def test_can_process_results_without_executions(self):
        """Test processing validation fails without completed executions."""
        can_process, reason = self.validator.can_process_results(self.session)

        self.assertFalse(can_process)
        self.assertIn("No completed executions", reason)

    def test_can_process_results_with_completed_executions(self):
        """Test processing validation passes with completed executions."""
        # Add completed execution
        query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            is_active=True,
        )

        SearchExecution.objects.create(
            query=query, initiated_by=self.user, status="completed", results_count=10
        )

        can_process, reason = self.validator.can_process_results(self.session)

        self.assertTrue(can_process)
        self.assertIsNone(reason)

    def test_can_process_results_with_active_processing(self):
        """Test processing validation fails with active ProcessingSession."""
        # Add completed execution
        query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            is_active=True,
        )

        SearchExecution.objects.create(
            query=query, initiated_by=self.user, status="completed", results_count=10
        )

        # Add active processing session
        ProcessingSession.objects.create(
            search_session=self.session, status="in_progress"
        )

        can_process, reason = self.validator.can_process_results(self.session)

        self.assertFalse(can_process)
        self.assertIn("already in progress", reason)

    def test_can_review_without_processing(self):
        """Test review validation without processing."""
        can_review, reason = self.validator.can_review(self.session)

        self.assertFalse(can_review)
        self.assertIn("No processed results", reason)

    def test_can_review_with_processed_results(self):
        """Test review validation with processed results."""
        # Create complete chain: query -> execution -> raw result -> processed result
        query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            is_active=True,
        )

        execution = SearchExecution.objects.create(
            query=query, initiated_by=self.user, status="completed"
        )

        raw_result = RawSearchResult.objects.create(
            execution=execution,
            position=1,
            title="Test Result",
            link="https://example.com",
            raw_data={},
        )

        ProcessedResult.objects.create(
            session=self.session,
            raw_result=raw_result,
            title="Test Result",
            url="https://example.com",
        )

        can_review, reason = self.validator.can_review(self.session)

        self.assertTrue(can_review)
        self.assertIsNone(reason)

    def test_can_complete_with_no_results(self):
        """Test completion validation with no results."""
        can_complete, reason = self.validator.can_complete(self.session)

        self.assertTrue(can_complete)
        self.assertIsNone(reason)

    def test_can_complete_with_unreviewed_results(self):
        """Test completion validation with unreviewed results."""
        self.session.total_results = 10
        self.session.reviewed_results = 5
        self.session.save()

        can_complete, reason = self.validator.can_complete(self.session)

        self.assertFalse(can_complete)
        self.assertIn("5 of 10 results still need review", reason)

    def test_can_complete_with_all_reviewed(self):
        """Test completion validation with all results reviewed."""
        self.session.total_results = 10
        self.session.reviewed_results = 10
        self.session.save()

        can_complete, reason = self.validator.can_complete(self.session)

        self.assertTrue(can_complete)
        self.assertIsNone(reason)

    def test_can_archive(self):
        """Test archive validation - always allowed."""
        can_archive, reason = self.validator.can_archive(self.session)

        self.assertTrue(can_archive)
        self.assertIsNone(reason)

    def test_validate_session_data_integrity_no_strategy(self):
        """Test data integrity check with no strategy."""
        # Delete the strategy
        self.strategy.delete()

        is_valid, report = self.validator.validate_session_data_integrity(self.session)

        self.assertFalse(is_valid)
        # After deleting, it detects no search strategy
        self.assertIn("No search strategy defined", report)

    def test_validate_session_data_integrity_valid(self):
        """Test data integrity check with valid data."""
        # Add complete valid data chain
        query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
            is_active=True,
        )

        execution = SearchExecution.objects.create(
            query=query, initiated_by=self.user, status="completed"
        )

        raw_result = RawSearchResult.objects.create(
            execution=execution,
            position=1,
            title="Test",
            link="https://example.com",
            raw_data={},
        )

        ProcessedResult.objects.create(
            session=self.session,
            raw_result=raw_result,
            title="Test",
            url="https://example.com",
        )

        is_valid, report = self.validator.validate_session_data_integrity(self.session)

        self.assertTrue(is_valid)
        self.assertIn("Data integrity check passed", report)
        self.assertIn("Queries: 1", report)
        self.assertIn("Raw results: 1", report)
        self.assertIn("Processed: 1", report)
