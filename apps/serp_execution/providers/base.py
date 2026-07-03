"""
Base protocol for SERP API providers.

Defines the interface that all SERP providers must implement.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class SerpProvider(Protocol):
    """Protocol for SERP API providers.

    All concrete providers (Serper.dev, SerpAPI, etc.) must implement
    this interface. The provider_key and display_name are used for
    tracking and reporting.
    """

    provider_key: str
    display_name: str

    def search(
        self, query: str, num_results: int = 10, **kwargs: object
    ) -> tuple[dict, dict]:
        """Execute a search query.

        Args:
            query: Search query string.
            num_results: Number of results to return.
            **kwargs: Provider-specific parameters.

        Returns:
            Tuple of (results, metadata) where results contains
            organic search results and metadata contains API response info.
        """
        ...

    def safe_search(
        self, query: str, num_results: int = 10, **kwargs: object
    ) -> tuple[dict, dict]:
        """Execute search with graceful error handling.

        Same as search() but returns an error response dict instead
        of raising exceptions on failure.

        Args:
            query: Search query string.
            num_results: Number of results to return.
            **kwargs: Provider-specific parameters.

        Returns:
            Tuple of (results, metadata).
        """
        ...

    def health_check(self) -> bool:
        """Check if the provider API is reachable and healthy.

        Returns:
            True if the provider is healthy, False otherwise.
        """
        ...

    def get_rate_limit_key(self) -> str:
        """Return the Redis key prefix for this provider's rate limiter.

        Returns:
            String key prefix, e.g. 'rate_limit:serper'.
        """
        ...
