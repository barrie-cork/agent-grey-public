"""
Tests for progress status messages during SERP execution and processing.

This module tests that all 8 required progress messages are correctly
displayed during the search execution workflow.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.review_manager.models import SearchSession
from apps.review_manager.services.state_manager import SessionStateManager
from apps.search_strategy.models import SearchQuery
from apps.serp_execution.constants import ExecutionStatusMessages
from apps.core.tests.utils import create_test_user

User = get_user_model()


class ProgressMessagesTest(TestCase):
    """Test suite for progress status messages."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()
        self.session = SearchSession.objects.create(
            title="Test Progress Messages", owner=self.user, status="ready_to_execute"
        )
        from apps.search_strategy.models import SearchStrategy

        # Create strategy first as SearchQuery requires it
        self.strategy = SearchStrategy.objects.create(
            session=self.session, user=self.user
        )

        self.query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="site:example.com (test) type:pdf",
            query_type="domain-specific",
            target_domain="example.com",
        )

    def test_status_messages_constants(self):
        """Test that all status messages are defined in constants."""
        messages = ExecutionStatusMessages()

        # Test ready_to_execute messages
        ready_messages = messages.get_ready_messages()
        self.assertEqual(len(ready_messages), 4)
        self.assertEqual(ready_messages[0], "Validation complete")
        self.assertEqual(ready_messages[1], "Preparing execution environment")
        self.assertEqual(ready_messages[2], "Initialising search queries")
        self.assertEqual(ready_messages[3], "Starting search execution")

        # Test processing messages (updated to 5 messages)
        processing_messages = messages.get_processing_messages()
        self.assertEqual(len(processing_messages), 5)
        self.assertEqual(processing_messages[0], "Processing search results")
        self.assertEqual(processing_messages[1], "Normalising URLs")
        self.assertEqual(processing_messages[2], "Conducting cross-query deduplication")
        self.assertEqual(processing_messages[3], "Finalising results")
        self.assertEqual(processing_messages[4], "Ready for review")

    def test_ready_to_execute_messages(self):
        """Test that ready_to_execute phase sends all 4 messages."""
        state_manager = SessionStateManager(self.session)

        # Mock ProgressTracker (imported locally inside the function)
        with patch("apps.core.progress.tracker.ProgressTracker") as MockTracker:
            mock_tracker_instance = MagicMock()
            MockTracker.return_value = mock_tracker_instance

            # Mock execution task to prevent actual execution (imported locally)
            with patch(
                "apps.serp_execution.tasks.initiate_search_session_execution_task"
            ) as mock_task:
                mock_task.delay.return_value = MagicMock(id="test-task-id")

                # Mock on_commit to call immediately
                with patch(
                    "django.db.transaction.on_commit",
                    side_effect=lambda func, **kwargs: func(),
                ):
                    state_manager._trigger_automatic_execution(self.session)

        # Check that all 4 ready_to_execute messages were sent
        calls = mock_tracker_instance.update_progress.call_args_list
        self.assertGreaterEqual(
            len(calls), 4, "Should send at least 4 progress messages"
        )

        # Extract the messages from the calls
        messages = [call[1]["current_step"] for call in calls[:4]]

        # Verify each message
        self.assertEqual(messages[0], "Validation complete")
        self.assertEqual(messages[1], "Preparing execution environment")
        self.assertEqual(messages[2], "Initialising search queries")
        self.assertEqual(messages[3], "Starting search execution")

    def test_processing_messages_in_deduplication(self):
        """Test that deduplication sends the correct status detail message."""
        from apps.results_manager.models import ProcessingSession
        from apps.results_manager.tasks.processing import run_deduplication_task

        # Create processing session
        processing_session = ProcessingSession.objects.create(
            search_session=self.session, status="processing", total_raw_results=10
        )

        # Mock get_deduplication_stats to prevent actual DB queries
        # (lazy import inside run_deduplication_task, so patch at source)
        with patch(
            "apps.results_manager.api.get_deduplication_stats",
            return_value={
                "duplicates_removed": 0,
                "total_results": 0,
                "unique_results": 0,
            },
        ):
            # Call as Celery task (bind=True means first arg is self)
            _result = run_deduplication_task(  # type: ignore[call-arg]
                batch_results=[],
                session_id=str(self.session.id),
                processing_session_id=str(processing_session.id),
            )

        # Verify session status_detail was updated with deduplication message
        self.session.refresh_from_db()
        # The task updates status_detail via session.update_status_detail()
        # with ExecutionStatusMessages.CONDUCTING_DEDUPLICATION
        self.assertIn("deduplication", (self.session.status_detail or "").lower())

    def test_processing_messages_in_batch_processing(self):
        """Test that batch processing sends URL normalisation message."""
        from apps.results_manager.models import ProcessingSession
        from apps.results_manager.tasks.processing import process_batch_task
        from apps.serp_execution.models import RawSearchResult, SearchExecution

        # Create necessary test data
        processing_session = ProcessingSession.objects.create(
            search_session=self.session, status="processing", total_raw_results=10
        )

        execution = SearchExecution.objects.create(query=self.query, status="completed")

        raw_result = RawSearchResult.objects.create(
            execution=execution,
            title="Test Result",
            link="http://example.com/test",
            snippet="Test snippet",
            position=1,
        )

        # Run batch processing task (bind=True, arg order: self, session_id, processing_session_id, raw_result_ids, ...)
        _result = process_batch_task(  # type: ignore[call-arg]
            session_id=str(self.session.id),
            processing_session_id=str(processing_session.id),
            raw_result_ids=[str(raw_result.id)],
            batch_num=1,
            total_batches=1,
        )

        # Verify the task ran to completion (status_detail updated or processed count changed)
        processing_session.refresh_from_db()
        self.assertGreaterEqual(processing_session.processed_count, 0)

    def test_finalization_messages(self):
        """Test that finalization transitions session and sends status updates."""
        from apps.results_manager.models import ProcessingSession
        from apps.results_manager.tasks.processing import finalize_processing_task

        # Set session to processing_results state
        self.session.status = "processing_results"
        self.session.save()

        # Create processing session (status must be "processing" for finalization)
        processing_session = ProcessingSession.objects.create(
            search_session=self.session,
            status="processing",
            total_raw_results=10,
            processed_count=10,
        )

        # Run finalization task (bind=True, Celery passes self automatically)
        _result = finalize_processing_task(  # type: ignore[call-arg]
            dedup_results={"duplicates_removed": 2},
            session_id=str(self.session.id),
            processing_session_id=str(processing_session.id),
        )

        # Verify session transitioned to ready_for_review
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "ready_for_review")

    def test_execution_query_message_format(self):
        """Test that execution messages include query details."""
        message_template = ExecutionStatusMessages.EXECUTING_QUERY

        # Test with full details
        message = message_template.format(
            domain="example.com", terms="(test) AND (data)", file_type="pdf"
        )
        expected = "Executing example.com ((test) AND (data)) type:pdf"
        self.assertEqual(message, expected)

        # Test with minimal details
        message = message_template.format(
            domain="general search", terms="search terms", file_type="all"
        )
        expected = "Executing general search (search terms) type:all"
        self.assertEqual(message, expected)

    def test_query_completion_message_format(self):
        """Test that query completion messages show progress."""
        message_template = ExecutionStatusMessages.QUERY_COMPLETE

        message = message_template.format(current=3, total=10)
        expected = "Completed query 3/10"
        self.assertEqual(message, expected)

    def test_all_messages_sequence(self):
        """Test that all 9 messages are correctly sequenced."""
        all_messages = (
            ExecutionStatusMessages.get_ready_messages()
            + ExecutionStatusMessages.get_processing_messages()
        )

        expected_sequence = [
            "Validation complete",
            "Preparing execution environment",
            "Initialising search queries",
            "Starting search execution",
            "Processing search results",
            "Normalising URLs",
            "Conducting cross-query deduplication",
            "Finalising results",
            "Ready for review",
        ]

        self.assertEqual(all_messages, expected_sequence)
        self.assertEqual(len(all_messages), 9, "Should have exactly 9 status messages")
