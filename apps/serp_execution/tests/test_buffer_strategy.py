"""
Tests for the buffer strategy to ensure exact result counts.
Tests the off-by-one fix that addresses Issue #17.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.config import get_config
from apps.review_manager.models import SearchSession
from apps.search_strategy.models import SearchQuery, SearchStrategy
from apps.serp_execution.models import SearchExecution
from apps.serp_execution.query_executor import SerpQueryExecutor
from apps.core.tests.utils import create_test_user


class TestBufferStrategy(TestCase):
    """Test the buffer strategy for ensuring exact result counts."""

    def setUp(self):
        """Set up test data."""
        self.user = create_test_user()

        self.session = SearchSession.objects.create(
            title="Test Buffer Strategy", owner=self.user, status="ready_to_execute"
        )

        self.strategy = SearchStrategy.objects.create(
            session=self.session,
            user=self.user,
            population_terms=["test"],
            interest_terms=["buffer"],
            search_config={
                "max_results": 50,
                "domains": [],
                "include_general_search": True,
            },
        )

        self.query = SearchQuery.objects.create(
            session=self.session,
            strategy=self.strategy,
            query_text="test buffer strategy",
            query_type="general",
        )

        self.execution = SearchExecution.objects.create(
            query=self.query, initiated_by=self.user, status="pending"
        )

    def test_buffer_multiplier_applied_for_50_results(self):
        """Test that buffer multiplier is applied when requesting 50 results."""
        executor = SerpQueryExecutor()
        config = get_config()

        # Build API parameters
        api_params = executor.build_api_parameters("test query", self.strategy, config)

        # Should request 55 results (50 * 1.1)
        self.assertEqual(api_params["num"], 55)
        self.assertEqual(api_params["requested_num"], 50)

    def test_buffer_not_applied_over_100_results(self):
        """Test that buffer is not applied for requests over 100."""
        self.strategy.search_config["max_results"] = 150
        self.strategy.save()

        executor = SerpQueryExecutor()
        config = get_config()

        api_params = executor.build_api_parameters("test query", self.strategy, config)

        # Should not apply buffer for > 100
        self.assertEqual(api_params["num"], 150)
        self.assertEqual(api_params["requested_num"], 150)

    def test_results_trimmed_to_requested_amount(self):
        """Test that results are trimmed to the requested amount after buffer."""
        executor = SerpQueryExecutor()

        # Mock API response with 55 results
        mock_results = {
            "organic": [
                {"title": f"Result {i}", "link": f"http://example.com/{i}"}
                for i in range(55)
            ]
        }
        mock_metadata = {"credits": 1}

        # Mock the api_client.safe_search method (execute_with_retry calls safe_search)
        with patch.object(
            executor.api_client,
            "safe_search",
            return_value=(mock_results, mock_metadata),
        ):
            api_params = {"q": "test query", "num": 55, "requested_num": 50}

            # Execute with retry (which should trim results)
            results, metadata = executor.execute_with_retry(
                "test query", api_params, self.execution, MagicMock()
            )

            # Should be trimmed to 50 results
            self.assertEqual(len(results["organic"]), 50)
            self.assertTrue(metadata.get("buffer_applied"))
            self.assertEqual(metadata.get("pre_trim_count"), 55)
            self.assertEqual(metadata.get("post_trim_count"), 50)
