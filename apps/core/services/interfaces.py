"""
Service interfaces for dependency injection within core/services.

Only protocols actively used by services in this package are defined here.
For cross-app protocols, see apps/core/interfaces.py.
"""

from typing import Any, Dict, Optional, Protocol


class CacheProvider(Protocol):
    """Interface for caching services."""

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from cache."""
        ...

    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        """Set a value in cache with optional timeout."""
        ...

    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        ...

    def clear(self) -> None:
        """Clear all cache entries."""
        ...

    def health_check(self) -> bool:
        """Perform health check on cache."""
        ...

    def get_search_results(self, query_params: Dict[str, Any]) -> Optional[Any]:
        """Get cached search results for query parameters."""
        ...

    def set_search_results(self, query_params: Dict[str, Any], result: Any) -> None:
        """Cache search results for query parameters."""
        ...


class RateLimiter(Protocol):
    """Interface for rate limiting services."""

    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed for identifier."""
        ...

    def record_request(self, identifier: str) -> None:
        """Record a request for rate limiting."""
        ...

    def get_remaining_quota(self, identifier: str) -> int:
        """Get remaining requests for identifier."""
        ...

    def reset_quota(self, identifier: str) -> None:
        """Reset quota for identifier."""
        ...

    def can_proceed(self) -> bool:
        """Check if operation can proceed (rate limiter not exhausted)."""
        ...

    def health_check(self) -> bool:
        """Perform health check on rate limiter."""
        ...
