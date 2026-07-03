"""
Tests for Serper API pagination functionality.

Tests the new pagination feature that fetches multiple pages of results
to maximise coverage for systematic literature reviews.
"""

from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from apps.core.services.serper_client import SerperClient
from apps.core.tests.utils import create_test_user


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class SerperPaginationTests(TestCase):
    """Test pagination functionality in SerperClient."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = SerperClient(
            config={"enable_caching": False},  # type: ignore[arg-type]
            rate_limiter=None,
        )
        # Ensure no rate limiter blocks requests
        self.client._rate_limiter = None

    def _create_mock_response(self, page_num, results_per_page=10):
        """Create a mock Serper API response for a given page."""
        organic_results = [
            {
                "title": f"Result {(page_num - 1) * results_per_page + i + 1}",
                "link": f"https://example.com/result-{(page_num - 1) * results_per_page + i + 1}",
                "snippet": f"This is result {(page_num - 1) * results_per_page + i + 1}",
            }
            for i in range(results_per_page)
        ]

        return {
            "organic": organic_results,
            "searchInformation": {"totalResults": "1000"},
        }

    @patch("apps.core.services.serper_client.requests.post")
    def test_pagination_disabled_single_page(self, mock_post):
        """Test that pagination can be disabled to fetch only one page."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self._create_mock_response(1, 10)
        mock_post.return_value = mock_response

        # Execute search with pagination disabled
        pagination_config = {"enabled": False, "results_per_page": 10, "max_pages": 10}

        result = self.client.search(
            "test query", num_results=10, pagination_config=pagination_config
        )

        # Verify only one API call was made
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(len(result["organic"]), 10)

    @patch("apps.core.services.serper_client.requests.post")
    @patch("time.sleep")  # Mock sleep to speed up tests
    def test_pagination_fetches_multiple_pages(self, mock_sleep, mock_post):
        """Test that pagination fetches multiple pages correctly."""
        # Mock API responses for 3 pages
        mock_responses = []
        for page in range(1, 4):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = self._create_mock_response(page, 10)
            mock_responses.append(mock_response)

        mock_post.side_effect = mock_responses

        # Execute search requesting 30 results (3 pages)
        pagination_config = {
            "enabled": True,
            "results_per_page": 10,
            "max_pages": 10,
            "delay_between_pages": 0.5,
        }

        result = self.client.search(
            "test query", num_results=30, pagination_config=pagination_config
        )

        # Verify 3 API calls were made
        self.assertEqual(mock_post.call_count, 3)

        # Verify we got 30 results
        self.assertEqual(len(result["organic"]), 30)

        # Verify pagination metadata
        pagination_info = result.get("pagination", {})
        self.assertEqual(pagination_info["pages_fetched"], 3)
        self.assertEqual(pagination_info["pages_requested"], 3)
        self.assertEqual(pagination_info["requested_results"], 30)
        self.assertEqual(pagination_info["results_returned"], 30)
        self.assertEqual(pagination_info["per_page_counts"], [10, 10, 10])
        self.assertAlmostEqual(pagination_info["delay_between_pages"], 0.5)
        self.assertEqual(pagination_info["stopped_reason"], "limit_reached")

        # Verify delay was called between pages (2 times for 3 pages)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("apps.core.services.serper_client.requests.post")
    def test_pagination_stops_at_max_pages(self, mock_post):
        """Test that pagination respects max_pages limit."""

        # Mock API responses for many pages
        def create_response(*args, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = self._create_mock_response(1, 10)
            return mock_response

        mock_post.side_effect = create_response

        # Execute search with max_pages=5 but requesting 100 results
        pagination_config = {
            "enabled": True,
            "results_per_page": 10,
            "max_pages": 5,
            "delay_between_pages": 0,
        }

        result = self.client.search(
            "test query", num_results=100, pagination_config=pagination_config
        )

        # Verify only 5 pages were fetched
        self.assertEqual(mock_post.call_count, 5)
        self.assertEqual(len(result["organic"]), 50)  # 5 pages * 10 results

        pagination_info = result.get("pagination", {})
        self.assertEqual(pagination_info["pages_fetched"], 5)
        self.assertEqual(pagination_info["pages_requested"], 5)
        self.assertEqual(pagination_info["stopped_reason"], "limit_reached")
        self.assertEqual(pagination_info["results_returned"], 50)
        self.assertEqual(pagination_info["per_page_counts"], [10, 10, 10, 10, 10])
        self.assertEqual(pagination_info["delay_between_pages"], 0)

    @patch("apps.core.services.serper_client.requests.post")
    def test_pagination_stops_on_empty_page(self, mock_post):
        """Test that pagination stops when encountering an empty page."""
        # Mock: 2 pages with results, then empty page
        mock_responses = [
            Mock(status_code=200, json=lambda: self._create_mock_response(1, 10)),
            Mock(status_code=200, json=lambda: self._create_mock_response(2, 10)),
            Mock(
                status_code=200,
                json=lambda: {
                    "organic": [],
                    "searchInformation": {"totalResults": "20"},
                },
            ),
        ]
        mock_post.side_effect = mock_responses

        pagination_config = {
            "enabled": True,
            "results_per_page": 10,
            "max_pages": 10,
            "delay_between_pages": 0,
        }

        result = self.client.search(
            "test query", num_results=100, pagination_config=pagination_config
        )

        # Verify pagination stopped after empty page
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(len(result["organic"]), 20)  # Only 2 pages

        pagination_info = result.get("pagination", {})
        self.assertEqual(pagination_info["stopped_reason"], "no_more_results")
        self.assertEqual(pagination_info["per_page_counts"], [10, 10, 0])
        self.assertEqual(pagination_info["results_returned"], 20)

    @patch("apps.core.services.serper_client.requests.post")
    def test_pagination_handles_rate_limit_gracefully(self, mock_post):
        """Test that pagination handles rate limits gracefully."""
        # Mock: 2 successful pages, then rate limit
        mock_responses = [
            Mock(status_code=200, json=lambda: self._create_mock_response(1, 10)),
            Mock(status_code=200, json=lambda: self._create_mock_response(2, 10)),
            Mock(status_code=429, headers={"Retry-After": "60"}),
        ]
        mock_post.side_effect = mock_responses

        pagination_config = {
            "enabled": True,
            "results_per_page": 10,
            "max_pages": 10,
            "delay_between_pages": 0,
        }

        result = self.client.search(
            "test query", num_results=100, pagination_config=pagination_config
        )

        # Verify we got results from first 2 pages despite rate limit
        self.assertEqual(len(result["organic"]), 20)

        pagination_info = result.get("pagination", {})
        self.assertEqual(pagination_info["pages_fetched"], 2)
        self.assertEqual(pagination_info["stopped_reason"], "rate_limit")
        self.assertEqual(pagination_info["pages_requested"], 10)
        self.assertEqual(pagination_info["results_returned"], 20)

    @patch("apps.core.services.serper_client.requests.post")
    def test_pagination_respects_api_limit_100_results(self, mock_post):
        """Test that pagination stops at ~100 results (Serper API limit)."""

        # Mock unlimited pages
        def create_response(*args, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = self._create_mock_response(1, 10)
            return mock_response

        mock_post.side_effect = create_response

        pagination_config = {
            "enabled": True,
            "results_per_page": 10,
            "max_pages": 20,  # Ask for more than API allows
            "delay_between_pages": 0,
        }

        result = self.client.search(
            "test query",
            num_results=200,  # Request more than API allows
            pagination_config=pagination_config,
        )

        # Verify pagination stopped at 100 results (10 pages)
        self.assertEqual(mock_post.call_count, 10)
        self.assertEqual(len(result["organic"]), 100)

        pagination_info = result.get("pagination", {})
        self.assertEqual(pagination_info["stopped_reason"], "api_limit")
        self.assertEqual(pagination_info["pages_requested"], 10)
        self.assertEqual(pagination_info["pages_fetched"], 10)
        self.assertEqual(pagination_info["results_returned"], 100)
        self.assertEqual(pagination_info["per_page_counts"], [10] * 10)

    @patch("apps.core.services.serper_client.requests.post")
    def test_adaptive_pagination_limits_by_total_results_metadata(self, mock_post):
        """Total results metadata should cap the number of requested pages."""
        responses = []
        for page in range(1, 4):
            mock_response = Mock()
            mock_response.status_code = 200
            data = self._create_mock_response(page, 10)
            if page == 1:
                data["searchInformation"]["totalResults"] = "20"
            mock_response.json.return_value = data
            responses.append(mock_response)

        # Provide an extra response that should not be used if adaptive cap works
        extra_response = Mock()
        extra_response.status_code = 200
        extra_response.json.return_value = self._create_mock_response(4, 10)
        responses.append(extra_response)

        mock_post.side_effect = responses

        pagination_config = {
            "enabled": True,
            "results_per_page": 10,
            "max_pages": 10,
            "delay_between_pages": 0,
        }

        result = self.client.search(
            "test query", num_results=80, pagination_config=pagination_config
        )

        # Only 2 pages should be fetched (matching total results metadata)
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(len(result["organic"]), 20)
        pagination_info = result.get("pagination", {})
        self.assertEqual(pagination_info["pages_requested"], 2)
        self.assertEqual(pagination_info["pages_fetched"], 2)
        self.assertEqual(pagination_info["results_returned"], 20)
        # Stop reason is 'no_more_results' because 20 results < 80 desired
        self.assertEqual(pagination_info["stopped_reason"], "no_more_results")
        self.assertEqual(pagination_info["per_page_counts"], [10, 10])

    @patch("apps.core.services.serper_client.requests.post")
    def test_early_stop_on_short_page(self, mock_post):
        """Pagination should stop early when a page returns fewer results than expected."""
        first_response = Mock()
        first_response.status_code = 200
        first_payload = self._create_mock_response(1, 10)
        first_payload["searchInformation"]["totalResults"] = "100"
        first_response.json.return_value = first_payload

        second_response = Mock()
        second_response.status_code = 200
        second_payload = self._create_mock_response(2, 10)
        second_payload["organic"] = second_payload["organic"][:3]
        second_response.json.return_value = second_payload

        # Third response is empty - production fetches one more page after short page
        third_response = Mock()
        third_response.status_code = 200
        third_response.json.return_value = {
            "organic": [],
            "searchInformation": {"totalResults": "100"},
        }

        mock_post.side_effect = [first_response, second_response, third_response]

        pagination_config = {
            "enabled": True,
            "results_per_page": 10,
            "max_pages": 10,
            "delay_between_pages": 0,
        }

        result = self.client.search(
            "test query", num_results=50, pagination_config=pagination_config
        )

        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(len(result["organic"]), 13)
        pagination_info = result.get("pagination", {})
        self.assertEqual(pagination_info["stopped_reason"], "no_more_results")
        self.assertEqual(pagination_info["pages_fetched"], 3)
        self.assertEqual(pagination_info["results_returned"], 13)
        self.assertEqual(pagination_info["per_page_counts"], [10, 3, 0])

    @patch("apps.core.services.serper_client.requests.post")
    def test_page_parameter_sent_correctly(self, mock_post):
        """Test that page parameter is sent correctly to API."""
        mock_responses = []
        for page in range(1, 4):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = self._create_mock_response(page, 10)
            mock_responses.append(mock_response)

        mock_post.side_effect = mock_responses

        pagination_config = {
            "enabled": True,
            "results_per_page": 10,
            "max_pages": 3,
            "delay_between_pages": 0,
        }

        self.client.search(
            "test query", num_results=30, pagination_config=pagination_config
        )

        # Verify page parameter was sent correctly
        # First call should not have page parameter (page 1 is default)
        first_call_payload = mock_post.call_args_list[0][1]["json"]
        self.assertNotIn("page", first_call_payload)

        # Second and third calls should have page parameter
        second_call_payload = mock_post.call_args_list[1][1]["json"]
        self.assertEqual(second_call_payload["page"], 2)

        third_call_payload = mock_post.call_args_list[2][1]["json"]
        self.assertEqual(third_call_payload["page"], 3)

    def test_parse_total_available_handles_different_formats(self):
        """Test parsing of total available results in different formats."""
        # Test integer format
        result = self.client._parse_total_available(1000)
        self.assertEqual(result, 1000)

        # Test string format with commas
        result = self.client._parse_total_available("1,000,000")
        self.assertEqual(result, 1000000)

        # Test string format without commas
        result = self.client._parse_total_available("1000")
        self.assertEqual(result, 1000)

        # Test None
        result = self.client._parse_total_available(None)
        self.assertEqual(result, 0)

        # Test invalid format
        result = self.client._parse_total_available("invalid")
        self.assertEqual(result, 0)


class PaginationIntegrationTests(TestCase):
    """Integration tests for pagination with the task layer."""

    @patch("apps.core.services.serper_client.requests.post")
    def test_pagination_config_from_search_strategy(self, mock_post):
        """Test that pagination config is correctly passed from SearchStrategy."""
        from apps.review_manager.models import SearchSession
        from apps.search_strategy.models import SearchStrategy

        # Create test user and session
        user = create_test_user()

        session = SearchSession.objects.create(
            owner=user, title="Test Session", status="draft"
        )

        # Create strategy with pagination config
        strategy = SearchStrategy.objects.create(
            session=session,
            user=user,
            population_terms=["obesity"],
            interest_terms=["intervention"],
            search_config={
                "domains": [],
                "include_general_search": True,
                "file_types": [],
                "max_results": 100,
                "pagination": {
                    "enabled": True,
                    "results_per_page": 10,
                    "max_pages": 10,
                    "delay_between_pages": 0.5,
                },
            },
        )

        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "organic": [
                {
                    "title": "Test",
                    "link": "https://example.com",
                    "snippet": "Test snippet",
                }
            ],
            "searchInformation": {"totalResults": "100"},
        }
        mock_post.return_value = mock_response

        # Execute search through client
        client = SerperClient()
        result = client.search(
            "obesity AND intervention",
            num_results=100,
            pagination_config=strategy.search_config["pagination"],
        )

        # Verify pagination was used
        self.assertIn("pagination", result)
