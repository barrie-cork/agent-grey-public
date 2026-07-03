"""
Tests for diagnostic management commands.

Tests the following commands:
- diagnose_zero_results
- investigate_session_data
- fix_false_duplicates
"""

from io import StringIO
from unittest.mock import patch, MagicMock

from django.core.management import call_command
from django.test import TestCase

from apps.results_manager.models import ProcessedResult

# ProcessingStatus values are: "success", "filtered", "error"
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import RawSearchResult, SearchExecution
from apps.core.tests.utils import create_test_user


class DiagnoseZeroResultsCommandTest(TestCase):
    """Test diagnose_zero_results management command."""

    def setUp(self):
        """Create test user and session."""
        self.user = create_test_user(first_name="Test", last_name="User")

        self.session = SearchSession.objects.create(
            owner=self.user,
            title="Test Session",
            status="ready_for_review",
        )

        # Create search strategy and query
        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["research"],
            context_terms=["study"],
        )

        self.query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="test research study",
            query_type="general",
        )

    def test_diagnose_nonexistent_session(self):
        """Test diagnostic on non-existent session."""
        out = StringIO()
        call_command(
            "diagnose_zero_results",
            "00000000-0000-0000-0000-000000000000",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("not found", output.lower())

    def test_diagnose_healthy_session(self):
        """Test diagnostic on session with no issues."""
        # Create execution and results
        execution = SearchExecution.objects.create(
            query=self.query,
            status="completed",
        )

        RawSearchResult.objects.create(
            execution=execution,
            position=1,
            title="Test Result",
            link="https://example.com/1",
            snippet="Test snippet",
            is_processed=True,
        )

        ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/1",
            title="Test Result",
            snippet="Test snippet",
            processing_status="success",
        )

        out = StringIO()
        call_command(
            "diagnose_zero_results",
            str(self.session.id),
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("No issues detected", output)

    def test_diagnose_zero_results_bug(self):
        """Test diagnostic detects zero results bug (all results FILTERED)."""
        # Create execution and raw result
        execution = SearchExecution.objects.create(
            query=self.query,
            status="completed",
        )

        RawSearchResult.objects.create(
            execution=execution,
            position=1,
            title="Test Result",
            link="https://example.com/1",
            snippet="Test snippet",
            is_processed=True,
        )

        # Create FILTERED result (bug scenario)
        ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/1",
            title="Test Result",
            snippet="Test snippet",
            processing_status="filtered",
        )

        out = StringIO()
        call_command(
            "diagnose_zero_results",
            str(self.session.id),
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("ISSUES DETECTED", output)
        self.assertIn("ZERO RESULTS BUG", output)
        self.assertIn("FILTERED", output)

    def test_diagnose_unprocessed_raw_results(self):
        """Test diagnostic detects unprocessed raw results."""
        execution = SearchExecution.objects.create(
            query=self.query,
            status="completed",
        )

        # Create unprocessed raw result
        RawSearchResult.objects.create(
            execution=execution,
            position=1,
            title="Test Result",
            link="https://example.com/1",
            snippet="Test snippet",
            is_processed=False,  # Not processed
        )

        out = StringIO()
        call_command(
            "diagnose_zero_results",
            str(self.session.id),
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("ISSUES DETECTED", output)
        self.assertIn("unprocessed raw results", output.lower())

    @patch("apps.results_manager.tasks.process_session_results_task")
    def test_fix_flag_triggers_reprocessing(self, mock_task):
        """Test --fix flag triggers reprocessing task."""
        mock_task.apply_async = MagicMock(return_value=MagicMock(id="test-task-id"))

        execution = SearchExecution.objects.create(
            query=self.query,
            status="completed",
        )

        # Create unprocessed raw result
        RawSearchResult.objects.create(
            execution=execution,
            position=1,
            title="Test Result",
            link="https://example.com/1",
            snippet="Test snippet",
            is_processed=False,
        )

        out = StringIO()
        call_command(
            "diagnose_zero_results",
            str(self.session.id),
            "--fix",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Attempting fixes", output)
        mock_task.apply_async.assert_called_once()

    def test_fix_flag_corrects_false_duplicates(self):
        """Test --fix flag corrects falsely marked FILTERED results."""
        # Create result incorrectly marked as FILTERED
        result = ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/unique",
            title="Unique Result",
            snippet="Test snippet",
            processing_status="filtered",
        )

        out = StringIO()
        call_command(
            "diagnose_zero_results",
            str(self.session.id),
            "--fix",
            stdout=out,
        )

        # Refresh from database
        result.refresh_from_db()

        # Should be corrected to SUCCESS
        self.assertEqual(result.processing_status, "success")

        output = out.getvalue()
        self.assertIn("Corrected", output)
        self.assertIn("SUCCESS", output)

    def test_diagnose_all_recent_sessions(self):
        """Test --all flag diagnoses multiple sessions."""
        # Create another session
        _session2 = SearchSession.objects.create(
            owner=self.user,
            title="Another Session",
            status="ready_for_review",
        )

        out = StringIO()
        call_command(
            "diagnose_zero_results",
            "--all",
            "--recent",
            "7",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Checking", output)
        self.assertIn("sessions", output.lower())


class InvestigateSessionDataCommandTest(TestCase):
    """Test investigate_session_data management command."""

    def setUp(self):
        """Create test user and session."""
        self.user = create_test_user(first_name="Test", last_name="User")

        self.session = SearchSession.objects.create(
            owner=self.user,
            title="Investigation Test",
            status="ready_for_review",
        )

    def test_investigate_nonexistent_session(self):
        """Test investigation of non-existent session."""
        out = StringIO()
        call_command(
            "investigate_session_data",
            "00000000-0000-0000-0000-000000000000",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("not found", output.lower())

    def test_investigate_shows_status_breakdown(self):
        """Test investigation shows ProcessedResult status breakdown."""
        # Create results with different statuses
        ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/success",
            title="Success Result",
            processing_status="success",
        )

        ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/filtered",
            title="Filtered Result",
            processing_status="filtered",
        )

        ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/error",
            title="Error Result",
            processing_status="error",
        )

        out = StringIO()
        call_command(
            "investigate_session_data",
            str(self.session.id),
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Status Breakdown", output)
        self.assertIn("SUCCESS", output)
        self.assertIn("FILTERED", output)
        self.assertIn("ERROR", output)

    def test_investigate_detects_duplicate_urls(self):
        """Test investigation detects actual duplicate URLs."""
        # Create duplicate URLs
        ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/duplicate",
            title="First Instance",
            processing_status="success",
        )

        ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/duplicate",
            title="Second Instance",
            processing_status="filtered",
        )

        out = StringIO()
        call_command(
            "investigate_session_data",
            str(self.session.id),
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Duplicate URL Analysis", output)
        self.assertIn("multiple times", output.lower())

    def test_investigate_recommends_fix_for_false_duplicates(self):
        """Test investigation recommends fix when false duplicates detected."""
        # Create FILTERED result without actual duplicate
        ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/unique",
            title="Unique Result",
            processing_status="filtered",
        )

        out = StringIO()
        call_command(
            "investigate_session_data",
            str(self.session.id),
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("CRITICAL BUG DETECTED", output)
        self.assertIn("FALSE DUPLICATE", output)
        self.assertIn("RECOMMENDED FIX", output)


class FixFalseDuplicatesCommandTest(TestCase):
    """Test fix_false_duplicates management command."""

    def setUp(self):
        """Create test user and session."""
        self.user = create_test_user(first_name="Test", last_name="User")

        self.session = SearchSession.objects.create(
            owner=self.user,
            title="Fix Test",
            status="ready_for_review",
        )

    def test_fix_nonexistent_session(self):
        """Test fix on non-existent session."""
        out = StringIO()
        call_command(
            "fix_false_duplicates",
            "00000000-0000-0000-0000-000000000000",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("not found", output.lower())

    def test_fix_no_results(self):
        """Test fix when session has no results."""
        out = StringIO()
        call_command(
            "fix_false_duplicates",
            str(self.session.id),
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("No processed results", output)

    def test_fix_dry_run_no_changes(self):
        """Test --dry-run doesn't modify database."""
        result = ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/unique",
            title="Unique Result",
            processing_status="filtered",
        )

        out = StringIO()
        call_command(
            "fix_false_duplicates",
            str(self.session.id),
            "--dry-run",
            stdout=out,
        )

        # Refresh and verify no change
        result.refresh_from_db()
        self.assertEqual(result.processing_status, "filtered")

        output = out.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("Would fix", output)

    def test_fix_corrects_false_duplicates(self):
        """Test fix corrects falsely marked FILTERED results."""
        result = ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/unique",
            title="Unique Result",
            processing_status="filtered",
        )

        out = StringIO()
        call_command(
            "fix_false_duplicates",
            str(self.session.id),
            stdout=out,
        )

        # Refresh and verify correction
        result.refresh_from_db()
        self.assertEqual(result.processing_status, "success")

        output = out.getvalue()
        self.assertIn("SUCCESS", output)
        self.assertIn("Fixed", output)

    def test_fix_preserves_true_duplicates(self):
        """Test fix preserves results that are actual duplicates."""
        # Create first instance (SUCCESS)
        _result1 = ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/duplicate",
            title="First Instance",
            processing_status="success",
        )

        # Create second instance (FILTERED - true duplicate)
        result2 = ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/duplicate",
            title="Second Instance",
            processing_status="filtered",
        )

        out = StringIO()
        call_command(
            "fix_false_duplicates",
            str(self.session.id),
            stdout=out,
        )

        # Refresh and verify true duplicate stays FILTERED
        result2.refresh_from_db()
        self.assertEqual(result2.processing_status, "filtered")

        output = out.getvalue()
        self.assertIn("True duplicates", output)

    def test_fix_mixed_scenario(self):
        """Test fix handles mix of true and false duplicates."""
        # False duplicate
        false_dup = ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/unique",
            title="Unique Result",
            processing_status="filtered",
        )

        # True duplicate pair
        _true_dup1 = ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/duplicate",
            title="First Instance",
            processing_status="success",
        )

        true_dup2 = ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/duplicate",
            title="Second Instance",
            processing_status="filtered",
        )

        out = StringIO()
        call_command(
            "fix_false_duplicates",
            str(self.session.id),
            stdout=out,
        )

        # Verify corrections
        false_dup.refresh_from_db()
        true_dup2.refresh_from_db()

        self.assertEqual(false_dup.processing_status, "success")
        self.assertEqual(true_dup2.processing_status, "filtered")

    def test_fix_shows_status_breakdown(self):
        """Test fix shows before/after status breakdown."""
        ProcessedResult.objects.create(
            session=self.session,
            url="https://example.com/unique",
            title="Unique Result",
            processing_status="filtered",
        )

        out = StringIO()
        call_command(
            "fix_false_duplicates",
            str(self.session.id),
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Current Status Breakdown", output)
        self.assertIn("Updated Status Breakdown", output)
