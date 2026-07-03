"""
Tests for the orchestration module, specifically zero results handling.
"""

import uuid
from unittest.mock import patch

from django.test import TestCase

from apps.results_manager.models import ProcessingSession
from apps.results_manager.tasks.orchestration import _handle_no_results
from apps.review_manager.models import SearchSession
from apps.core.tests.utils import create_test_user


class HandleNoResultsTestCase(TestCase):
    """Test cases for the _handle_no_results function."""

    def setUp(self) -> None:
        """Set up test data."""
        self.user = create_test_user(username_prefix="test@example.com")
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="processing_results"
        )
        self.processing_session = ProcessingSession.objects.create(
            search_session=self.session, status="running"
        )

    def test_handle_no_results_success(self) -> None:
        """Test successful handling of zero results."""
        result = _handle_no_results(self.processing_session, str(self.session.id))

        # _handle_no_results returns a TypedDict (dict), not a Pydantic model
        self.assertIsInstance(result, dict)
        # Verify return value - NoResultsResponse TypedDict
        self.assertEqual(str(result["session_id"]), str(self.session.id))

        # Verify processing session updated
        self.processing_session.refresh_from_db()
        self.assertEqual(self.processing_session.status, "completed")

        # Verify search session updated
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "completed")
        self.assertEqual(self.session.total_results, 0)
        self.assertIsNotNone(self.session.completed_at)

        # The function updates session directly, activity logging may be handled
        # by signals or may not be present. Just verify the session state.
        self.assertEqual(self.session.status, "completed")
        self.assertEqual(self.session.total_results, 0)

    def test_handle_no_results_session_not_found(self) -> None:
        """Test handling when session doesn't exist."""
        fake_session_id = str(uuid.uuid4())

        result = _handle_no_results(self.processing_session, fake_session_id)

        # _handle_no_results returns a TypedDict (dict), not a Pydantic model
        self.assertIsInstance(result, dict)
        # Verify error response - ProcessingError TypedDict
        self.assertEqual(str(result["session_id"]), fake_session_id)
        self.assertEqual(result["error"], "Session not found")  # type: ignore[reportIndexIssue]

        # Verify processing session still updated
        self.processing_session.refresh_from_db()
        self.assertEqual(self.processing_session.status, "completed")

    @patch("apps.results_manager.tasks.orchestration.logger")
    def test_handle_no_results_logging(self, mock_logger) -> None:
        """Test that appropriate logging occurs."""
        # Test successful case
        _result_obj = _handle_no_results(self.processing_session, str(self.session.id))
        mock_logger.warning.assert_called_with(
            f"No raw results found for session {self.session.id}"
        )

        # Test error case
        fake_session_id = str(uuid.uuid4())
        _result_obj = _handle_no_results(self.processing_session, fake_session_id)
        mock_logger.error.assert_called_with(
            f"SearchSession {fake_session_id} not found in _handle_no_results"
        )


class GetRawResultsCountTestCase(TestCase):
    """Test cases for the _get_raw_results_count function - prevent regression of false zero detection."""

    def setUp(self) -> None:
        """Set up test data."""
        from apps.search_strategy.models import SearchQuery, SearchStrategy
        from apps.serp_execution.models import SearchExecution

        self.user = create_test_user(username_prefix="test@example.com")

        # Create session with strategy and query
        self.session = SearchSession.objects.create(
            title="Test Session", owner=self.user, status="processing_results"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test", "population"],
            interest_terms=["test", "intervention"],
            context_terms=["test", "context"],
        )

        self.query = SearchQuery.objects.create(
            strategy=self.strategy,
            session=self.session,
            query_text="test query",
            query_type="general",
        )

        self.execution = SearchExecution.objects.create(
            query=self.query, status="completed", initiated_by=self.user
        )

    def test_get_raw_results_count_with_processed_results(self) -> None:
        """Test that _get_raw_results_count counts all results, not just unprocessed ones."""
        from apps.results_manager.tasks.orchestration import _get_raw_results_count
        from apps.serp_execution.models import RawSearchResult

        # Create 3 raw results, all processed (is_processed=True)
        for i in range(3):
            RawSearchResult.objects.create(
                execution=self.execution,
                position=i + 1,
                title=f"Test Result {i + 1}",
                link=f"https://example.com/{i + 1}",
                snippet=f"Test snippet {i + 1}",
                is_processed=True,  # All results are processed
            )

        # The function should count ALL results (3), not just unprocessed ones (0)
        count = _get_raw_results_count(self.session)
        self.assertEqual(
            count, 3, "Should count all results, not just unprocessed ones"
        )

    def test_get_raw_results_count_with_mixed_processed_status(self) -> None:
        """Test _get_raw_results_count with mix of processed and unprocessed results."""
        from apps.results_manager.tasks.orchestration import _get_raw_results_count
        from apps.serp_execution.models import RawSearchResult

        # Create 2 processed results and 2 unprocessed results
        for i in range(2):
            RawSearchResult.objects.create(
                execution=self.execution,
                position=i + 1,
                title=f"Processed Result {i + 1}",
                link=f"https://example.com/processed/{i + 1}",
                snippet=f"Processed snippet {i + 1}",
                is_processed=True,
            )

        for i in range(2):
            RawSearchResult.objects.create(
                execution=self.execution,
                position=i + 3,
                title=f"Unprocessed Result {i + 1}",
                link=f"https://example.com/unprocessed/{i + 1}",
                snippet=f"Unprocessed snippet {i + 1}",
                is_processed=False,
            )

        # The function should count ALL 4 results
        count = _get_raw_results_count(self.session)
        self.assertEqual(
            count, 4, "Should count all results regardless of processed status"
        )

    def test_get_raw_results_count_zero_results(self) -> None:
        """Test _get_raw_results_count returns 0 when truly no results exist."""
        from apps.results_manager.tasks.orchestration import _get_raw_results_count

        # No raw results created
        count = _get_raw_results_count(self.session)
        self.assertEqual(count, 0, "Should return 0 when no results exist")

    def test_get_raw_results_count_correct_session_filtering(self) -> None:
        """Test that _get_raw_results_count only counts results for the specified session."""
        from apps.results_manager.tasks.orchestration import _get_raw_results_count
        from apps.search_strategy.models import SearchQuery, SearchStrategy
        from apps.serp_execution.models import RawSearchResult

        # Create results for our test session
        RawSearchResult.objects.create(
            execution=self.execution,
            position=1,
            title="Test Result 1",
            link="https://example.com/1",
            snippet="Test snippet 1",
            is_processed=True,
        )

        # Create another session with results that shouldn't be counted
        other_session = SearchSession.objects.create(
            title="Other Session", owner=self.user, status="processing_results"
        )

        other_strategy = SearchStrategy.objects.create(
            session=other_session,
            user=self.user,
            population_terms=["other", "population"],
            interest_terms=["other", "intervention"],
            context_terms=["other", "context"],
        )

        other_query = SearchQuery.objects.create(
            strategy=other_strategy,
            session=other_session,
            query_text="other query",
            query_type="general",
        )

        from apps.serp_execution.models import SearchExecution

        other_execution = SearchExecution.objects.create(
            query=other_query, status="completed", initiated_by=self.user
        )

        RawSearchResult.objects.create(
            execution=other_execution,
            position=1,
            title="Other Result 1",
            link="https://example.com/other/1",
            snippet="Other snippet 1",
            is_processed=True,
        )

        # Should only count results for our specific session
        count = _get_raw_results_count(self.session)
        self.assertEqual(
            count, 1, "Should only count results for the specified session"
        )
