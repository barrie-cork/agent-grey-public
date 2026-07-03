"""
Serper API Client Service

Core API integration service for Serper.dev. The single SerperClient: handles
authentication, query/response validation, request building, circuit-breaker
protection, Prometheus metrics, response processing and pagination.

Phase 4 of ponytail-cleanup folded the former serp_execution facade in here, so
this is now the one and only Serper client.
"""

import json
import logging
import math
import time
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, TypedDict

import pybreaker
import requests
from django.conf import settings

from .base import BaseService
from .circuit_breaker import serper_circuit_breaker
from .exceptions import (
    SerperAuthError,
    SerperConnectionError,
    SerperError,
    SerperQuotaError,
    SerperRateLimitError,
    SerperTimeoutError,
)
from .http_client import HTTPClient
from .interfaces import CacheProvider
from .interfaces import RateLimiter as RateLimiterInterface
from .serper_config import SerperConfig
from .serper_processor import SerperProcessor
from .serper_validator import SerperValidator

# Prometheus metrics integration (kept in Phase 3's partial removal).
try:
    from apps.core.metrics.search_metrics import track_search_execution

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

# Backward-compatibility error aliases (formerly defined in the serp_execution facade).
SerperAPIError = SerperError
SerperResponseError = SerperError

logger = logging.getLogger(__name__)


class SerperClientConfig(TypedDict):
    api_key: str
    timeout: int
    base_url: str
    cache_timeout: int
    enable_caching: bool


class SerperClient(BaseService[SerperClientConfig]):
    """
    Core API integration service for Serper.dev.
    Handles authentication, request building, and response processing.
    """

    SERVICE_NAME = "SerperClient"
    SERVICE_VERSION = "2.0.0"

    def __init__(
        self,
        config: Optional[SerperClientConfig] = None,
        rate_limiter: Optional[RateLimiterInterface] = None,
        cache_manager: Optional[CacheProvider] = None,
    ):
        """Initialize Serper client with configuration and dependencies."""
        # Store dependencies
        self._rate_limiter = rate_limiter
        self._cache_manager = cache_manager

        # Folded-in collaborators (Phase 4). SerperConfig() raises on a missing
        # SERPER_API_KEY, preserving the old facade's fail-fast ValueError contract.
        self.serper_config = SerperConfig()
        self.http_client = HTTPClient(**self.serper_config.get_http_client_config())
        self.validator = SerperValidator()
        self.processor = SerperProcessor()

        # Initialize base service
        super().__init__(config)

    def get_default_config(self) -> SerperClientConfig:
        """Get default configuration for Serper client."""
        return {
            "api_key": getattr(settings, "SERPER_API_KEY", ""),
            "timeout": 30,
            "base_url": "https://google.serper.dev/search",
            "cache_timeout": 3600,
            "enable_caching": True,
        }

    def _initialize(self) -> None:
        """Initialize Serper client-specific resources."""
        # Lazy initialization of dependencies
        if not self._rate_limiter:
            try:
                # Import here to avoid circular imports
                from .rate_limiter import TokenBucketRateLimiter

                self._rate_limiter = TokenBucketRateLimiter()
            except (ImportError, ConnectionError, OSError) as e:
                self.logger.warning(f"Failed to initialize rate limiter: {e}")
                self._rate_limiter = None

        if not self._cache_manager and self.config["enable_caching"]:
            try:
                # Import here to avoid circular imports
                from .cache_manager import RedisCacheManager

                self._cache_manager = RedisCacheManager()
            except (ImportError, ConnectionError, OSError) as e:
                self.logger.warning(f"Failed to initialize cache manager: {e}")
                self._cache_manager = None

        if not self.config["api_key"]:
            self.logger.warning("SERPER_API_KEY not configured")

    # Backward compatibility properties
    @property
    def api_key(self) -> str:
        """Backward compatibility property for API key."""
        return self.config["api_key"]

    @property
    def timeout(self) -> int:
        """Backward compatibility property for timeout."""
        return self.config["timeout"]

    @property
    def base_url(self) -> str:
        """Backward compatibility property for base URL."""
        return self.config["base_url"]

    @property
    def rate_limiter(self):
        """Backward compatibility property for rate limiter."""
        return self._rate_limiter

    @rate_limiter.setter
    def rate_limiter(self, value) -> None:
        """Allow overriding the rate limiter (for legacy compatibility)."""
        self._rate_limiter = value

    @property
    def cache_manager(self):
        """Backward compatibility property for cache manager."""
        return self._cache_manager

    def health_check(self) -> bool:
        """Check if Serper client is healthy and operational."""
        try:
            # Check API key configuration
            if not self.config["api_key"]:
                return False

            # Check rate limiter health
            if self._rate_limiter and hasattr(self._rate_limiter, "health_check"):
                if not self._rate_limiter.health_check():
                    return False

            # Check cache manager health
            if self._cache_manager and hasattr(self._cache_manager, "health_check"):
                if not self._cache_manager.health_check():
                    return False

            return True

        except (
            Exception
        ) as e:  # Intentional broad catch: health check tests service availability
            self._handle_error(e, operation="health_check")
            return False

    def sanitize_query(self, query: str) -> str:
        """
        Sanitize and validate query string before sending to API.

        Prevents API abuse, quota exhaustion, and malformed queries.

        Args:
            query: Raw query string from user input

        Returns:
            Sanitised query string

        Raises:
            SerperError: If query is invalid or exceeds limits
        """
        if not query:
            raise SerperError("Query cannot be empty")

        # Remove control characters (keep only printable characters)
        sanitised = "".join(char for char in query if ord(char) >= 32)

        # Strip whitespace
        sanitised = sanitised.strip()

        # Validate not empty after sanitisation
        if not sanitised:
            raise SerperError("Query cannot be empty after sanitisation")

        # Limit length to prevent API abuse (500 chars is reasonable for search)
        max_length = 500
        if len(sanitised) > max_length:
            self.logger.warning(
                f"Query length {len(sanitised)} exceeds maximum {max_length}, truncating"
            )
            sanitised = sanitised[:max_length]

        return sanitised

    def validate_query(self, query: str):
        """Validate a search query before execution (delegates to the validator)."""
        return self.validator.validate_query(query)

    def _build_request_params(
        self, query: str, num_results: int = 10, **kwargs
    ) -> dict:
        """Build Serper API request parameters via the processor."""
        defaults = self.serper_config.get_search_defaults()
        language = kwargs.pop("language", defaults["language"])
        location = kwargs.pop("location", defaults["location"])
        search_type = kwargs.pop("search_type", "search")

        return self.processor.build_request_params(
            query,
            num_results,
            search_type=search_type,
            language=language,
            location=location,
            country_code=defaults["country_code"],
            max_results_limit=defaults["max_results"],
            **kwargs,
        )

    @serper_circuit_breaker
    def search(  # noqa: C901 - validation + metrics + circuit-breaker wrapper
        self,
        query: str,
        num_results: int = 10,
        session=None,
        search_query=None,
        **kwargs,
    ) -> Dict:
        """
        Execute a search with query/response validation, Prometheus metrics and
        circuit-breaker protection, delegating the HTTP/pagination work to
        ``_execute_search``.

        Args:
            query: Search query string
            num_results: Maximum results to return (will paginate if > 10)
            session: SearchSession for status updates (backward compatibility)
            search_query: Optional SearchQuery instance for metrics tracking
            **kwargs: pagination_config / search params forwarded downstream

        Returns:
            Dictionary with search results and metadata

        Raises:
            SerperError: For various API failures
        """
        is_valid, error_msg = self.validator.validate_query(query)
        if not is_valid:
            raise SerperAPIError(f"Query validation failed: {error_msg}")

        # Metrics wrap the whole operation so the context manager sees exceptions
        # for proper error categorisation.
        metrics_context = (
            track_search_execution(search_query)
            if (METRICS_AVAILABLE and search_query)
            else nullcontext()
        )

        with metrics_context as metrics_tracker:
            try:
                logger.info(f"Executing search: {query[:50]}...")

                # Build + validate request params (kept for parity; the engine
                # builds its own payload, so these feed validation only).
                defaults = self.serper_config.get_search_defaults()
                language = kwargs.pop("language", defaults["language"])
                location = kwargs.pop("location", defaults["location"])
                params = self.processor.build_request_params(
                    query,
                    num_results,
                    language=language,
                    location=location,
                    country_code=defaults["country_code"],
                    max_results_limit=defaults["max_results"],
                    **kwargs,
                )
                api_params = {
                    k: v for k, v in params.items() if not k.startswith("_internal_")
                }
                is_valid, error_msg = self.validator.validate_request_params(api_params)
                if not is_valid:
                    raise SerperAPIError(
                        f"Request parameters validation failed: {error_msg}"
                    )

                result = self._execute_search(query, num_results, session, **kwargs)

                # Post-validation (warnings only unless structurally invalid).
                if isinstance(result, dict) and "organic" in result:
                    is_valid, error_msg, warnings = (
                        self.validator.validate_response_structure(result)
                    )
                    if not is_valid:
                        logger.error(f"Invalid response structure: {error_msg}")
                        raise SerperResponseError(
                            f"Invalid API response structure: {error_msg}"
                        )
                    for warning in warnings:
                        logger.warning(f"Response validation warning: {warning}")

                if metrics_tracker and isinstance(result, dict):
                    result_count = len(result.get("organic", []))
                    status = "success" if result_count > 0 else "empty"
                    metrics_tracker.record_results(result_count, status=status)  # type: ignore[arg-type]

                return result

            except (
                SerperRateLimitError,
                SerperAuthError,
                SerperQuotaError,
                SerperTimeoutError,
                SerperConnectionError,
            ):
                raise
            except SerperError:
                raise
            except Exception as e:
                self._handle_error(
                    e,
                    context={"query": query[:80], "num_results": num_results},
                    operation="search",
                )
                raise SerperAPIError(f"Unexpected error: {str(e)}") from e

    def safe_search(
        self, query: str, num_results: int = 10, **kwargs
    ) -> tuple[dict, dict]:
        """
        Search with graceful fallback when the circuit is open or a timeout hits.

        Returns:
            Tuple of (results_dict, metadata_dict)
        """
        try:
            result = self.search(query, num_results, **kwargs)
            metadata = {
                "total_results": result.get("searchInformation", {}).get(
                    "totalResults", "0"
                ),
                "search_time": result.get("searchInformation", {}).get("searchTime", 0),
                "credits_used": result.get("credits", 0),
            }
            return result, metadata
        except pybreaker.CircuitBreakerError:
            logger.warning(
                f"Circuit breaker open for Serper API. Query skipped: {query[:80]}"
            )
            error_dict, error_metadata = self.processor.create_error_response(
                "circuit_breaker_open", "Search service temporarily unavailable"
            )
            error_metadata["circuit_open"] = True
            return error_dict, error_metadata
        except requests.exceptions.Timeout:
            logger.error(f"Timeout searching for: {query[:80]}")
            error_dict, error_metadata = self.processor.create_error_response(
                "timeout", "Search request timed out"
            )
            error_metadata["timeout"] = True
            return error_dict, error_metadata
        except Exception as e:
            logger.error(f"Search error for '{query[:80]}': {e}")
            raise

    def check_rate_limits(self) -> dict:
        """Check current rate limit status."""
        if self.rate_limiter and hasattr(self.rate_limiter, "get_status"):
            return self.rate_limiter.get_status()  # type: ignore[attr-defined]
        return {"requests_in_window": 0, "rate_limit": 0, "remaining": 0}

    def _execute_search(
        self, query: str, num_results: int = 10, session=None, **kwargs
    ) -> Dict:
        """
        Engine: execute the search with pagination, rate limiting and caching.

        Args:
            query: Search query string
            num_results: Maximum results to return (will paginate if > 10)
            session: SearchSession for status updates (backward compatibility)
            **kwargs: pagination_config dict with pagination settings

        Returns:
            Dictionary with search results and metadata, including pagination info

        Raises:
            SerperError: For various API failures
        """
        with self._measure_performance("search"):
            # Sanitise and validate query first (prevents API abuse)
            query = self.sanitize_query(query)

            # Optional compatibility parameters (ignored in simplified client)
            # NOTE: Keep pop logic minimal to avoid leaking unexpected kwargs downstream.
            kwargs.pop("search_query", None)
            kwargs.pop("search_query_id", None)

            # Extract pagination configuration
            pagination_config = kwargs.pop("pagination_config", None) or {
                "enabled": True,
                "results_per_page": 10,
                "max_pages": min(10, (num_results + 9) // 10),  # Calculate needed pages
                "delay_between_pages": 0.5,
            }

            # Update status if provided (backward compatibility)
            if session:
                if hasattr(session, "update_status_detail"):
                    session.update_status_detail(f"Executing query: {query}")
                else:
                    self.logger.debug(
                        "Session provided but no update_status_detail method"
                    )

            # Determine if pagination is needed
            use_pagination = pagination_config.get(
                "enabled", True
            ) and num_results > pagination_config.get("results_per_page", 10)

            if use_pagination:
                return self._search_with_pagination(
                    query, num_results, session, pagination_config, **kwargs
                )
            else:
                return self._search_single_page(
                    query, num_results, session, page=1, **kwargs
                )

    def _search_with_pagination(  # noqa: C901 - Complex pagination logic with adaptive stopping and error handling
        self, query: str, num_results: int, session, pagination_config: Dict, **kwargs
    ) -> Dict:
        """
        Execute paginated search to retrieve more results with adaptive stopping.

        Args:
            query: Search query string
            num_results: Total number of results desired
            session: SearchSession for status updates
            pagination_config: Pagination configuration dict
            **kwargs: Additional parameters

        Returns:
            Merged results from all pages with pagination metadata
        """
        # Normalise pagination configuration
        try:
            results_per_page = int(pagination_config.get("results_per_page", 10) or 10)
        except (TypeError, ValueError):
            results_per_page = 10
        results_per_page = max(1, min(results_per_page, 100))

        try:
            max_pages = int(pagination_config.get("max_pages", 10) or 1)
        except (TypeError, ValueError):
            max_pages = 1
        max_pages = max(1, max_pages)

        try:
            delay_between_pages = float(
                pagination_config.get("delay_between_pages", 0.5) or 0
            )
        except (TypeError, ValueError):
            delay_between_pages = 0.0
        delay_between_pages = max(0.0, delay_between_pages)

        desired_results = max(1, num_results)
        max_results_user = min(desired_results, results_per_page * max_pages)
        max_results_allowed = min(max_results_user, 100)
        if max_results_allowed <= 0:
            max_results_allowed = results_per_page

        pages_target = max(1, math.ceil(max_results_allowed / results_per_page))
        pages_requested = pages_target

        self.logger.info(
            f"Starting paginated search: query='{query[:50]}...', desired={desired_results}, "
            f"per_page={results_per_page}, initial_pages={pages_target}, max_pages={max_pages}"
        )

        all_organic_results: List[Dict] = []
        pages_fetched = 0
        total_available = 0
        stop_reason: Optional[str] = None
        per_page_counts: List[int] = []

        page_num = 1
        while page_num <= pages_target:
            try:
                if self._rate_limiter and not self._rate_limiter.can_proceed():
                    self.logger.warning(
                        f"Local rate limit reached before page {page_num}, stopping pagination"
                    )
                    stop_reason = "local_rate_limit"
                    break

                if session and hasattr(session, "update_status_detail"):
                    session.update_status_detail(
                        f"Fetching page {page_num}/{pages_target} for: {query}"
                    )

                page_result = self._search_single_page(
                    query, results_per_page, session=None, page=page_num, **kwargs
                )

            except (SerperRateLimitError, SerperQuotaError) as exc:
                self.logger.warning(
                    f"Rate/quota error on page {page_num}: {exc}. Returning {len(all_organic_results)} results "
                    f"from {pages_fetched} pages."
                )
                stop_reason = "rate_limit"
                break
            except (
                SerperError,
                requests.exceptions.RequestException,
                ConnectionError,
                TimeoutError,
            ) as exc:
                self.logger.error(
                    f"Error fetching page {page_num}: {exc}. Returning {len(all_organic_results)} results "
                    f"from {pages_fetched} pages."
                )
                stop_reason = "error"
                break

            page_organic = page_result.get("organic", []) or []
            pages_fetched = page_num
            per_page_counts.append(len(page_organic))

            if page_num == 1:
                search_info = page_result.get("searchInformation", {}) or {}
                raw_total = self._parse_total_available(
                    search_info.get("totalResults", 0)
                )

                # Only set total_available if API provides it
                if raw_total > 0:
                    total_available = raw_total
                    self.logger.info(
                        f"API reported {raw_total} total results available"
                    )
                else:
                    # API didn't provide total - we'll track what we fetch
                    total_available = 0
                    self.logger.warning(
                        "API did not provide searchInformation.totalResults"
                    )

                if raw_total:
                    pages_from_total = max(1, math.ceil(raw_total / results_per_page))
                    new_target = min(pages_target, pages_from_total)
                    if new_target != pages_target:
                        self.logger.debug(
                            f"Adjusting planned pages based on total results "
                            f"{raw_total}: {pages_target} -> {new_target}"
                        )
                    pages_target = max(1, new_target)
                    pages_requested = pages_target

            if not page_organic:
                self.logger.info(f"No results on page {page_num}, stopping pagination")
                stop_reason = "no_more_results"
                break

            all_organic_results.extend(page_organic)

            # Only update total_available if API didn't provide it
            if total_available == 0:
                total_available = len(all_organic_results)

            self.logger.info(
                f"Page {page_num}: retrieved {len(page_organic)} results (total so far: {len(all_organic_results)})"
            )

            # Only stop if we get significantly fewer results AND we're below the desired count
            # A short page doesn't necessarily mean no more results exist
            if (
                len(page_organic) < results_per_page
                and len(all_organic_results) >= desired_results
            ):
                stop_reason = "limit_reached"
                self.logger.info(
                    f"Limit reached: page {page_num} returned {len(page_organic)} results, "
                    f"total {len(all_organic_results)} >= desired {desired_results}"
                )
                break

            if len(all_organic_results) >= desired_results:
                stop_reason = "limit_reached"
                self.logger.info(
                    f"Reached desired result count: {len(all_organic_results)}"
                )
                break

            if len(all_organic_results) >= 100:
                stop_reason = "api_limit"
                self.logger.info("Reached Serper API limit (~100 results)")
                break

            if (
                len(all_organic_results) >= max_results_allowed
                and desired_results > max_results_allowed
            ):
                stop_reason = "limit_reached"
                self.logger.info(
                    f"Reached configured result cap ({max_results_allowed}) before desired count {desired_results}"
                )
                break

            page_num += 1

            if page_num <= pages_target and delay_between_pages > 0:
                # Adaptive delay: increase delay for later queries to spread API calls
                query_index = kwargs.get("query_index", 1)
                adaptive_delay = delay_between_pages + ((query_index - 1) * 0.3)
                time.sleep(adaptive_delay)

        if stop_reason is None:
            # Determine most accurate stop reason based on what actually happened
            if len(all_organic_results) >= desired_results:
                stop_reason = "limit_reached"
            elif pages_fetched >= pages_requested:
                # Check if we got fewer results than expected - indicates API ran out
                if len(all_organic_results) < desired_results:
                    stop_reason = "no_more_results"
                else:
                    stop_reason = "limit_reached"
            elif not all_organic_results:
                stop_reason = "no_more_results"
            else:
                stop_reason = "limit_reached"

        trimmed_results = all_organic_results[:desired_results]

        pagination_info = {
            "pages_requested": pages_requested,
            "pages_fetched": pages_fetched,
            "total_available": total_available,
            "stopped_reason": stop_reason,
            "results_per_page": results_per_page,
            "requested_results": desired_results,
            "delay_between_pages": delay_between_pages,
            "results_returned": len(trimmed_results),
            "per_page_counts": per_page_counts,
        }

        merged_result = {
            "organic": trimmed_results,
            "searchInformation": {
                "totalResults": str(total_available),
                "organicResultsRetrieved": len(all_organic_results),
            },
            "pagination": pagination_info,
        }

        self.logger.info(
            f"Pagination complete: {len(all_organic_results)} results from "
            f"{pages_fetched} pages (reason: {stop_reason})"
        )

        return merged_result

    def _search_single_page(  # noqa: C901 - Complex API request handling with multiple error conditions
        self, query: str, num_results: int, session, page: int = 1, **kwargs
    ) -> Dict:
        """
        Execute single-page search query.

        Args:
            query: Search query string
            num_results: Number of results for this page (max 100)
            session: SearchSession for status updates (optional)
            page: Page number (1-indexed)
            **kwargs: Additional parameters

        Returns:
            Dictionary with search results and metadata

        Raises:
            SerperError: For various API failures
        """
        # Check rate limiting (local rate limiter, not API rate limit)
        if self._rate_limiter and not self._rate_limiter.can_proceed():
            error = SerperRateLimitError(
                "Local rate limit exceeded (client-side throttling)"
            )
            self._handle_error(error, {"query": query[:50], "page": page}, "search")
            raise error

        # Determine API URL based on search_type (google vs scholar)
        search_type = kwargs.get("search_type", "search")
        if search_type == "scholar":
            api_url = self.config["base_url"].replace("/search", "/scholar")
        else:
            api_url = self.config["base_url"]

        # Check cache first (only for page 1)
        query_params = {
            "q": query,
            "num": num_results,
            "page": page,
            "type": search_type,
        }
        if page == 1 and self._cache_manager and self.config["enable_caching"]:
            cached_result = self._cache_manager.get_search_results(query_params)
            if cached_result:
                self.logger.debug(f"Cache hit for query: {query[:30]}...")
                return cached_result

        # Build request
        headers = {
            "X-API-KEY": self.config["api_key"],
            "Content-Type": "application/json",
        }

        payload = {
            "q": query,
            "num": min(num_results, 100),  # Serper API limit
            "hl": "en",
            "gl": "uk",  # UK-based search as per requirements
        }

        # Add page parameter if not first page
        if page > 1:
            payload["page"] = page

        # Log payload structure without raw query (Issue #68842568, PR #60)
        redacted_payload = {
            k: (f"{v[:30]}…" if k == "q" and isinstance(v, str) else v)
            for k, v in payload.items()
        }
        self.logger.debug(f"API payload keys: {redacted_payload} -> {api_url}")

        try:
            response = requests.post(  # nosec B113 - Timeout via self.config["timeout"]
                api_url,
                json=payload,
                headers=headers,
                timeout=self.config["timeout"],
            )

            # Log full response details for 400 errors (Issue #68842568)
            if response.status_code == 400:
                try:
                    error_detail = response.json()
                except json.JSONDecodeError:
                    error_detail = response.text
                self.logger.error(
                    f"Serper API 400 Bad Request - Query length: {len(query)}, "
                    f"Num: {payload.get('num')}, Page: {payload.get('page', 1)}, "
                    f"Response: {error_detail}"
                )

                # Detect quota/credit errors returned as 400
                error_text = str(error_detail).lower()
                if "not enough credits" in error_text or "quota" in error_text:
                    error = SerperQuotaError(f"API quota exceeded: {error_detail}")
                    self._handle_error(
                        error, {"query": query[:50], "page": page}, "search"
                    )
                    raise error

            # Handle response
            if response.status_code == 429:
                delay = self._parse_retry_delay(response.headers)  # type: ignore[arg-type]
                error = SerperRateLimitError(f"Rate limited. Retry in {delay}s")
                self._handle_error(
                    error, {"query": query[:50], "delay": delay, "page": page}, "search"
                )
                raise error

            if response.status_code == 401:
                error = SerperAuthError("Invalid API key")
                self._handle_error(error, {"query": query[:50], "page": page}, "search")
                raise error

            if response.status_code == 402:
                error = SerperQuotaError("API quota exceeded")
                self._handle_error(error, {"query": query[:50], "page": page}, "search")
                raise error

            if response.status_code == 403:
                try:
                    error_detail = response.json()
                except json.JSONDecodeError:
                    error_detail = response.text
                self.logger.error(
                    f"Serper API 403 Forbidden - "
                    f"Page: {page}, Query length: {len(query)}, "
                    f"Response: {error_detail}"
                )
                error = SerperAuthError(
                    f"403 Forbidden from Serper API (page {page}): {error_detail}"
                )
                self._handle_error(error, {"query": query[:50], "page": page}, "search")
                raise error

            response.raise_for_status()
            result = response.json()

            # Cache successful result (only page 1)
            if page == 1 and self._cache_manager and self.config["enable_caching"]:
                self._cache_manager.set_search_results(query_params, result)

            page_info = f" (page {page})" if page > 1 else ""
            self.logger.info(
                f"Successfully executed query{page_info}: {query[:30]}... "
                f"({len(result.get('organic', []))} results)"
            )
            return result

        except requests.exceptions.Timeout as e:
            error = SerperTimeoutError(
                f"Request timeout after {self.config['timeout']}s"
            )
            self._handle_error(error, {"query": query[:50], "page": page}, "search")
            raise error from e
        except requests.exceptions.ConnectionError as e:
            error = SerperConnectionError("Failed to connect to Serper API")
            self._handle_error(error, {"query": query[:50], "page": page}, "search")
            raise error from e
        except requests.exceptions.RequestException as e:
            error = SerperError(f"API request failed: {str(e)}")
            self._handle_error(
                error,
                {"query_length": len(query), "page": page},
                "search",
            )
            raise error from e

    def _parse_total_available(self, total_results) -> int:
        """
        Parse total available results from API response.

        Args:
            total_results: Total results value from searchInformation

        Returns:
            Integer count of total available results
        """
        try:
            if isinstance(total_results, int):
                return total_results
            elif isinstance(total_results, str):
                # Remove commas and convert to int
                return int(total_results.replace(",", ""))
            else:
                return 0
        except (ValueError, AttributeError):
            return 0

    def _parse_retry_delay(self, headers: Dict[str, Any]) -> int:
        """Parse retry delay from response headers."""
        retry_after = headers.get("Retry-After", "60")
        try:
            return int(retry_after)
        except ValueError:
            return 60  # Default 1 minute delay
