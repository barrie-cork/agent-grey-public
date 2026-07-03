"""
Serper.dev concrete provider implementation.

Wraps the existing SerperClient to implement the SerpProvider protocol.
"""

import logging

logger = logging.getLogger(__name__)

# Provider constants
PROVIDER_KEY = "serper"
DISPLAY_NAME = "Serper.dev"


class SerperProvider:
    """Serper.dev SERP provider wrapping the existing SerperClient.

    Implements the SerpProvider protocol while delegating to the
    existing client infrastructure (circuit breaker, rate limiting, etc.).
    """

    provider_key: str = PROVIDER_KEY
    display_name: str = DISPLAY_NAME

    def __init__(self, client=None):
        """Initialise with an optional pre-configured client.

        Args:
            client: SerperClient or MockSerperClient instance.
                If None, uses get_serper_client() factory.
        """
        if client is None:
            from apps.serp_execution.services.mock_serper_client import (
                get_serper_client,
            )

            client = get_serper_client()
        self._client = client

    def search(
        self, query: str, num_results: int = 10, **kwargs: object
    ) -> tuple[dict, dict]:
        """Execute search via Serper API.

        Wraps the underlying client's Dict return into the protocol's
        tuple[dict, dict] format (results, metadata).
        """
        result = self._client.search(query, num_results, **kwargs)
        metadata = {
            "total_results": result.get("searchInformation", {}).get(
                "totalResults", "0"
            ),
            "search_time": result.get("searchInformation", {}).get("searchTime", 0),
            "credits_used": result.get("credits", 0),
        }
        return result, metadata

    def safe_search(
        self, query: str, num_results: int = 10, **kwargs: object
    ) -> tuple[dict, dict]:
        """Execute search with graceful error handling."""
        return self._client.safe_search(query, num_results, **kwargs)

    def health_check(self) -> bool:
        """Check Serper API health with a lightweight query."""
        try:
            _, metadata = self._client.safe_search("test", num_results=1)
            return not metadata.get("circuit_open", False)
        except Exception:
            return False

    def get_rate_limit_key(self) -> str:
        """Return Redis key prefix for Serper rate limiting."""
        return f"rate_limit:{self.provider_key}"
