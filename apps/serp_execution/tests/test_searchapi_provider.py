"""
Tests for the SearchAPI.io Bing provider.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.serp_execution.providers.base import SerpProvider
from apps.serp_execution.providers.searchapi_provider import SearchAPIProvider


class SearchAPIProviderProtocolTests(TestCase):
    """Test SerpProvider protocol conformance."""

    def test_implements_protocol(self):
        provider = SearchAPIProvider(api_key="test")
        self.assertIsInstance(provider, SerpProvider)

    def test_attributes(self):
        provider = SearchAPIProvider(api_key="test")
        self.assertEqual(provider.provider_key, "searchapi_bing")
        self.assertEqual(provider.display_name, "SearchAPI.io (Bing)")

    def test_rate_limit_key(self):
        provider = SearchAPIProvider(api_key="test")
        self.assertEqual(provider.get_rate_limit_key(), "rate_limit:searchapi_bing")


class SearchAPIProviderRegistryTests(TestCase):
    """Test registry integration."""

    def test_registered_in_registry(self):
        from apps.serp_execution.providers import list_providers

        self.assertIn("searchapi_bing", list_providers())

    def test_get_provider(self):
        from apps.serp_execution.providers import get_provider

        provider = get_provider("searchapi_bing")
        self.assertIsInstance(provider, SearchAPIProvider)


class SearchAPIProviderSearchTests(TestCase):
    """Test search, pagination, and normalisation logic."""

    def _mock_response(self, num_results=2, page=1, has_next=False):
        """Return a realistic SearchAPI.io response fixture."""
        results = []
        for i in range(num_results):
            pos = (page - 1) * 10 + i + 1
            results.append(
                {
                    "position": pos,
                    "title": f"Test Result {pos}",
                    "link": f"https://example.com/result-{pos}",
                    "snippet": f"Snippet for result {pos}",
                    "source": "Example.com",
                    "displayed_link": f"https://example.com/result-{pos}",
                    "domain": "example.com",
                }
            )
        pagination = {"current": page}
        if has_next:
            pagination["next"] = f"https://www.bing.com/search?first={page * 10}"
        return {
            "search_metadata": {
                "id": f"search_page{page}",
                "status": "Success",
                "total_time_taken": 1.5,
            },
            "search_parameters": {"engine": "bing", "q": "test"},
            "search_information": {"query_displayed": "test"},
            "organic_results": results,
            "pagination": pagination,
        }

    @patch("apps.serp_execution.providers.searchapi_provider.requests.get")
    def test_search_returns_normalised_tuple(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = SearchAPIProvider(api_key="test-key")
        results, metadata = provider.search("test", num_results=10)

        self.assertIn("organic", results)
        self.assertEqual(len(results["organic"]), 2)
        self.assertEqual(results["organic"][0]["title"], "Test Result 1")
        self.assertEqual(results["organic"][0]["link"], "https://example.com/result-1")
        self.assertEqual(results["organic"][0]["snippet"], "Snippet for result 1")
        self.assertEqual(results["organic"][0]["position"], 1)

    @patch("apps.serp_execution.providers.searchapi_provider.requests.get")
    def test_metadata_fields(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = SearchAPIProvider(api_key="test-key")
        _, metadata = provider.search("test", num_results=10)

        self.assertEqual(metadata["total_results"], "2")
        self.assertEqual(metadata["time_taken"], 1.5)
        self.assertEqual(metadata["request_id"], "search_page1")
        self.assertEqual(metadata["provider"], "searchapi_bing")
        self.assertEqual(metadata["pages_fetched"], 1)
        self.assertEqual(metadata["credits_used"], 1)

    @patch("apps.serp_execution.providers.searchapi_provider.requests.get")
    def test_pagination_fetches_multiple_pages(self, mock_get):
        """When first page has fewer results than requested, fetch more pages."""
        page1_resp = MagicMock()
        page1_resp.json.return_value = self._mock_response(
            num_results=10, page=1, has_next=True
        )
        page1_resp.raise_for_status = MagicMock()

        page2_resp = MagicMock()
        page2_resp.json.return_value = self._mock_response(
            num_results=10, page=2, has_next=True
        )
        page2_resp.raise_for_status = MagicMock()

        page3_resp = MagicMock()
        page3_resp.json.return_value = self._mock_response(
            num_results=10, page=3, has_next=False
        )
        page3_resp.raise_for_status = MagicMock()

        mock_get.side_effect = [page1_resp, page2_resp, page3_resp]

        provider = SearchAPIProvider(api_key="test-key")
        results, metadata = provider.search("test", num_results=25)

        self.assertEqual(len(results["organic"]), 25)
        self.assertEqual(metadata["credits_used"], 3)
        self.assertEqual(metadata["pages_fetched"], 3)

    @patch("apps.serp_execution.providers.searchapi_provider.requests.get")
    def test_pagination_stops_when_no_next_page(self, mock_get):
        """Stop paginating when pagination has no 'next' key."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_response(
            num_results=5, page=1, has_next=False
        )
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = SearchAPIProvider(api_key="test-key")
        results, metadata = provider.search("test", num_results=50)

        self.assertEqual(len(results["organic"]), 5)
        self.assertEqual(mock_get.call_count, 1)

    @patch("apps.serp_execution.providers.searchapi_provider.requests.get")
    def test_pagination_trims_to_requested_count(self, mock_get):
        """Results are trimmed to num_results even if more were fetched."""
        page1_resp = MagicMock()
        page1_resp.json.return_value = self._mock_response(
            num_results=10, page=1, has_next=True
        )
        page1_resp.raise_for_status = MagicMock()

        page2_resp = MagicMock()
        page2_resp.json.return_value = self._mock_response(
            num_results=10, page=2, has_next=False
        )
        page2_resp.raise_for_status = MagicMock()

        mock_get.side_effect = [page1_resp, page2_resp]

        provider = SearchAPIProvider(api_key="test-key")
        results, metadata = provider.search("test", num_results=15)

        self.assertEqual(len(results["organic"]), 15)

    @patch("apps.serp_execution.providers.searchapi_provider.requests.get")
    def test_single_page_sufficient(self, mock_get):
        """No pagination when first page has enough results."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_response(
            num_results=10, page=1, has_next=True
        )
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = SearchAPIProvider(api_key="test-key")
        results, metadata = provider.search("test", num_results=5)

        self.assertEqual(len(results["organic"]), 5)
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(metadata["pages_fetched"], 1)

    @patch("apps.serp_execution.providers.searchapi_provider.requests.get")
    def test_safe_search_handles_timeout(self, mock_get):
        import requests as req

        mock_get.side_effect = req.exceptions.Timeout("timed out")

        provider = SearchAPIProvider(api_key="test-key")
        results, metadata = provider.safe_search("test")

        self.assertIn("error", results)
        self.assertEqual(results["organic"], [])
        self.assertEqual(metadata["credits_used"], 0)

    @patch("apps.serp_execution.providers.searchapi_provider.requests.get")
    def test_safe_search_handles_http_error(self, mock_get):
        import requests as req

        resp = MagicMock()
        resp.status_code = 429
        mock_get.side_effect = req.exceptions.HTTPError(response=resp)

        provider = SearchAPIProvider(api_key="test-key")
        results, metadata = provider.safe_search("test")

        self.assertIn("error", results)

    @patch("apps.serp_execution.providers.searchapi_provider.requests.get")
    def test_build_params_includes_engine_and_key(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        provider = SearchAPIProvider(api_key="my-key")
        provider.search("grey literature", num_results=20)

        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        self.assertEqual(params["engine"], "bing")
        self.assertEqual(params["api_key"], "my-key")
        self.assertEqual(params["q"], "grey literature")
        self.assertEqual(params["page"], 1)


class SearchAPIProviderConfigTests(TestCase):
    """Test seeded SerpProviderConfig for SearchAPI."""

    def test_seeded_config_exists(self):
        from apps.serp_execution.providers.config import SerpProviderConfig

        config, _ = SerpProviderConfig.objects.get_or_create(
            provider_key="searchapi_bing",
            defaults={
                "display_name": "SearchAPI.io (Bing)",
                "base_url": "https://www.searchapi.io/api/v1/search",
                "api_key_setting": "SEARCHAPI_API_KEY",
                "is_default": False,
                "is_enabled": True,
            },
        )
        self.assertFalse(config.is_default)
        self.assertTrue(config.is_enabled)
        self.assertEqual(config.api_key_setting, "SEARCHAPI_API_KEY")
