"""
Tests for the SerpQueryExecutor class in serp_execution app.

This module tests the query executor that handles SERP API calls
with retry logic and result processing.
"""

from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import TestCase

from apps.core.services.serper_client import SerperAPIError
from apps.serp_execution.query_executor import SerpQueryExecutor


class TestSerpQueryExecutor(TestCase):
    """Test the SerpQueryExecutor class."""

    def setUp(self):
        """Set up test data."""
        self.mock_api_client = Mock()
        self.mock_result_processor = Mock()
        self.executor = SerpQueryExecutor(
            api_client=self.mock_api_client, result_processor=self.mock_result_processor
        )

        # Mock execution
        self.execution = Mock()
        self.execution.id = uuid4()
        self.execution.retry_count = 0

        # Mock strategy
        self.strategy = Mock()
        self.strategy.search_config = {
            "max_results": 20,  # Fixed: was num_results, should be max_results
            "language": "en",
            "file_types": ["pdf", "docx"],  # Note: these are NOT used in API params
            "location": "United States",
        }

        # Mock config
        self.config = Mock()
        self.config.search.default_num_results = 10
        self.config.search.default_language = "en"
        self.config.search.default_file_types = ["pdf"]
        self.config.search.default_location = None
        self.config.processing.batch_size = 50

    def test_build_api_parameters_with_strategy_overrides(self):
        """Test building API parameters with strategy overrides."""
        query_text = "test query"

        params = self.executor.build_api_parameters(
            query_text, self.strategy, self.config
        )

        # Check that strategy values override defaults
        self.assertEqual(params["q"], query_text)
        self.assertEqual(params["num"], 22)  # from strategy (20 * 1.1 buffer)
        self.assertEqual(params["language"], "en")
        # NOTE: file_types are NOT in params - they're already in the query text
        self.assertNotIn(
            "file_types", params
        )  # file types are in query_text, not params
        self.assertEqual(params["location"], "United States")  # from strategy

    def test_build_api_parameters_with_defaults(self):
        """Test building API parameters with default values."""
        query_text = "test query"

        # Empty strategy config to use defaults
        self.strategy.search_config = {}

        params = self.executor.build_api_parameters(
            query_text, self.strategy, self.config
        )

        # Check that default values are used
        self.assertEqual(params["q"], query_text)
        self.assertEqual(params["num"], 11)  # from config default (10 * 1.1 buffer)
        self.assertEqual(params["language"], "en")  # from config default
        # NOTE: file_types are NOT in params - they're already in the query text
        self.assertNotIn(
            "file_types", params
        )  # file types are in query_text, not params
        self.assertNotIn("location", params)  # None means no location param

    def test_execute_with_retry_success(self):
        """Test successful query execution without retry."""
        search_query = "test query"
        api_params = {"q": search_query, "num": 10}
        retry_func = Mock()

        # Mock successful API response
        mock_results = {"organic": [{"title": "Result 1"}, {"title": "Result 2"}]}
        mock_metadata = {"credits_used": 1}
        self.mock_api_client.safe_search.return_value = (mock_results, mock_metadata)

        # Execute
        results, metadata = self.executor.execute_with_retry(
            search_query, api_params, self.execution, retry_func
        )

        # Verify
        self.assertEqual(results, mock_results)
        self.assertEqual(metadata, mock_metadata)
        self.mock_api_client.safe_search.assert_called_once()
        retry_func.assert_not_called()

    @patch("apps.serp_execution.query_executor.recovery_manager")
    def test_execute_with_retry_recoverable_error(self, mock_recovery_manager):
        """Test query execution with recoverable error that triggers retry."""
        search_query = "test query"
        api_params = {"q": search_query, "num": 10}

        # retry_func must return an exception object (it's used with `raise retry_func(...)`)
        retry_exception = Exception("Retry triggered")
        retry_func = Mock(return_value=retry_exception)

        # Mock API error
        api_error = SerperAPIError("Rate limit exceeded")
        self.mock_api_client.safe_search.side_effect = api_error

        # Mock recovery manager to allow retry
        mock_recovery_manager.should_retry.return_value = True
        mock_recovery_manager.get_retry_delay.return_value = 60

        # Execute - should raise retry
        with self.assertRaises(Exception):
            self.executor.execute_with_retry(
                search_query, api_params, self.execution, retry_func
            )

        # Verify retry was called
        retry_func.assert_called_once_with(exc=api_error, countdown=60)
        self.assertEqual(self.execution.retry_count, 1)
        self.execution.save.assert_called_with(update_fields=["retry_count"])

    @patch("apps.serp_execution.query_executor.recovery_manager")
    def test_execute_with_retry_non_recoverable_error(self, mock_recovery_manager):
        """Test query execution with non-recoverable error."""
        search_query = "test query"
        api_params = {"q": search_query, "num": 10}
        retry_func = Mock()

        # Mock API error
        api_error = SerperAPIError("Invalid API key")
        self.mock_api_client.safe_search.side_effect = api_error

        # Mock recovery manager to deny retry
        mock_recovery_manager.should_retry.return_value = False

        # Execute - should re-raise the error
        with self.assertRaises(SerperAPIError):
            self.executor.execute_with_retry(
                search_query, api_params, self.execution, retry_func
            )

        # Verify no retry was attempted
        retry_func.assert_not_called()

    def test_process_api_response_with_results(self):
        """Test processing API response with valid results."""
        results = {
            "organic": [
                {"title": "Result 1", "url": "http://example1.com"},
                {"title": "Result 2", "url": "http://example2.com"},
                {"title": "Result 3", "url": "http://example3.com"},
            ]
        }
        execution_id = str(uuid4())

        # Mock processor response
        self.mock_result_processor.process_search_results.return_value = (3, 0, [])

        # Process
        processed_count, duplicate_count, errors = self.executor.process_api_response(
            results, execution_id, self.config
        )

        # Verify
        self.assertEqual(processed_count, 3)
        self.assertEqual(duplicate_count, 0)
        self.assertEqual(errors, [])

        self.mock_result_processor.process_search_results.assert_called_once_with(
            execution_id=execution_id, raw_results=results["organic"], batch_size=50
        )

    def test_process_api_response_no_results(self):
        """Test processing API response with no results."""
        results = {"organic": []}
        execution_id = str(uuid4())

        # Process
        processed_count, duplicate_count, errors = self.executor.process_api_response(
            results, execution_id, self.config
        )

        # Verify
        self.assertEqual(processed_count, 0)
        self.assertEqual(duplicate_count, 0)
        self.assertEqual(errors, [])

        # Result processor should not be called
        self.mock_result_processor.process_search_results.assert_not_called()

    def test_process_api_response_with_errors(self):
        """Test processing API response that encounters errors."""
        results = {"organic": [{"title": "Result 1", "url": "http://example1.com"}]}
        execution_id = str(uuid4())

        # Mock processor response with errors
        error_msg = "Failed to process result"
        self.mock_result_processor.process_search_results.return_value = (
            0,
            0,
            [error_msg],
        )

        # Process
        processed_count, duplicate_count, errors = self.executor.process_api_response(
            results, execution_id, self.config
        )

        # Verify
        self.assertEqual(processed_count, 0)
        self.assertEqual(duplicate_count, 0)
        self.assertEqual(errors, [error_msg])

    @patch("apps.serp_execution.query_executor.recovery_manager")
    def test_handle_execution_error_final(self, mock_recovery_manager):
        """Test handling execution error when it's the final attempt."""
        error = SerperAPIError("API Error")
        mock_recovery_manager.get_error_category.return_value = "rate_limit"

        # Handle error
        result = self.executor.handle_execution_error(
            self.execution, error, is_final=True
        )

        # Verify execution was marked as failed
        self.assertEqual(self.execution.status, "failed")
        self.assertEqual(self.execution.error_message, str(error))
        self.assertIsNotNone(self.execution.completed_at)
        self.execution.save.assert_called_with(
            update_fields=["status", "error_message", "completed_at"]
        )

        # Verify response
        self.assertFalse(result["success"])
        self.assertEqual(result["execution_id"], str(self.execution.id))
        self.assertEqual(result["error"], str(error))
        self.assertEqual(result["error_category"], "rate_limit")

    def test_handle_execution_error_not_final(self):
        """Test handling execution error when it's not the final attempt."""
        error = Exception("Some error")

        # Handle error
        result = self.executor.handle_execution_error(
            self.execution, error, is_final=False
        )

        # Verify execution was NOT marked as failed
        self.assertNotEqual(self.execution.status, "failed")
        self.execution.save.assert_not_called()

        # Verify response
        self.assertFalse(result["success"])
        self.assertEqual(result["error_category"], "unknown")

    def test_mark_execution_complete(self):
        """Test marking execution as complete."""
        processed_count = 10

        # Mark complete
        self.executor.mark_execution_complete(self.execution, processed_count)

        # Verify
        self.assertEqual(self.execution.status, "completed")
        self.assertEqual(self.execution.results_count, processed_count)
        self.assertIsNotNone(self.execution.completed_at)
        self.execution.save.assert_called_with(
            update_fields=["status", "results_count", "completed_at"]
        )

    def test_init_with_default_services(self):
        """Test initialization without providing services."""
        # Create executor without services
        executor = SerpQueryExecutor()

        # Verify default services are created
        self.assertIsNotNone(executor.api_client)
        self.assertIsNotNone(executor.result_processor)

        # Check that api_client implements the expected interface
        # (may be SerperClient or MockSerperClient depending on settings)
        self.assertTrue(
            hasattr(executor.api_client, "safe_search"),
            "api_client must implement safe_search",
        )
        self.assertTrue(
            hasattr(executor.api_client, "search"),
            "api_client must implement search",
        )

        from apps.serp_execution.services.result_processor import ResultProcessor

        self.assertIsInstance(executor.result_processor, ResultProcessor)
