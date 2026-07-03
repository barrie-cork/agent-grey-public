"""
SearchAPI.io Bing concrete provider implementation.

Uses SearchAPI.io's Bing engine endpoint for web search results.
Docs: https://www.searchapi.io/docs/bing
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

PROVIDER_KEY = "searchapi_bing"
DISPLAY_NAME = "SearchAPI.io (Bing)"


class SearchAPIProvider:
    """SearchAPI.io Bing SERP provider.

    Implements the SerpProvider protocol. Calls the SearchAPI.io REST API
    with engine=bing and normalises results into the common format expected
    by the execution pipeline.
    """

    provider_key: str = PROVIDER_KEY
    display_name: str = DISPLAY_NAME

    # Mapping from SearchAPI.io response fields to common format
    RESULT_FIELD_MAPPING: dict[str, tuple[str, str | None]] = {
        "title": ("title", ""),
        "link": ("link", ""),
        "snippet": ("snippet", ""),
        "position": ("position", None),
        "displayedLink": ("displayed_link", ""),
        "source": ("source", ""),
        "date": ("date", None),
    }

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 30,
    ):
        self._api_key = api_key or getattr(settings, "SEARCHAPI_API_KEY", "")
        self._base_url = base_url or getattr(
            settings,
            "SEARCHAPI_BASE_URL",
            "https://www.searchapi.io/api/v1/search",
        )
        self._timeout = timeout

    # ------------------------------------------------------------------
    # SerpProvider protocol
    # ------------------------------------------------------------------

    # Bing returns ~10 results per page; cap pagination to avoid runaway requests
    _MAX_PAGES = 10

    def search(
        self, query: str, num_results: int = 10, **kwargs: object
    ) -> tuple[dict, dict]:
        """Execute a Bing search via SearchAPI.io with automatic pagination.

        Bing ignores the ``num`` parameter, so we paginate until we have
        collected enough results or there are no more pages.
        """
        all_organic: list[dict] = []
        total_credits = 0
        total_time = 0.0
        last_request_id = ""
        pages_fetched = 0

        for page in range(1, self._MAX_PAGES + 1):
            if len(all_organic) >= num_results:
                break

            params = self._build_params(query, num_results, **kwargs)
            params["page"] = page

            response = requests.get(
                self._base_url, params=params, timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()

            page_organic = data.get("organic_results", [])
            if not page_organic:
                break

            all_organic.extend(page_organic)
            pages_fetched = page

            search_meta = data.get("search_metadata", {})
            total_credits += 1
            total_time += search_meta.get("total_time_taken", 0)
            last_request_id = search_meta.get("id", "")

            if "next" not in data.get("pagination", {}):
                break

        # Trim to requested count and normalise
        all_organic = all_organic[:num_results]
        results = {"organic": self._normalise_organic(all_organic)}
        metadata = {
            "total_results": str(len(results["organic"])),
            "time_taken": total_time,
            "request_id": last_request_id,
            "credits_used": total_credits,
            "pages_fetched": pages_fetched,
            "response_warnings": [],
            "provider": self.provider_key,
        }
        return results, metadata

    def safe_search(
        self, query: str, num_results: int = 10, **kwargs: object
    ) -> tuple[dict, dict]:
        """Execute search with graceful error handling."""
        try:
            return self.search(query, num_results, **kwargs)
        except requests.exceptions.Timeout:
            logger.error("SearchAPI.io request timed out for query: %s", query)
            return self._error_response("Request timed out")
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            logger.error("SearchAPI.io HTTP %s for query: %s", status, query)
            return self._error_response(f"HTTP error {status}")
        except Exception as exc:
            logger.exception("SearchAPI.io unexpected error for query: %s", query)
            return self._error_response(str(exc))

    def health_check(self) -> bool:
        """Lightweight health probe (1-result query)."""
        try:
            results, meta = self.safe_search("test", num_results=1)
            return "error" not in results
        except Exception:
            return False

    def get_rate_limit_key(self) -> str:
        return f"rate_limit:{self.provider_key}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_params(self, query: str, num_results: int, **kwargs: object) -> dict:
        params: dict = {
            "engine": "bing",
            "q": query,
            "api_key": self._api_key,
        }
        if "location" in kwargs and kwargs["location"]:
            params["location"] = kwargs["location"]
        if "language" in kwargs and kwargs["language"]:
            params["language"] = kwargs["language"]
        return params

    def _normalise_organic(self, items: list[dict]) -> list[dict]:
        """Map raw SearchAPI.io result items to the common field format."""
        return [
            {
                key: item.get(source_key, default)
                for key, (source_key, default) in self.RESULT_FIELD_MAPPING.items()
            }
            for item in items
        ]

    @staticmethod
    def _error_response(message: str) -> tuple[dict, dict]:
        return (
            {"organic": [], "error": message},
            {
                "total_results": "0",
                "credits_used": 0,
                "provider": PROVIDER_KEY,
            },
        )
