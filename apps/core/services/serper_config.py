"""
SerperClient configuration management.
Extracted from SerperClient to follow single responsibility principle.
"""

import logging

from django.conf import settings

from apps.core.config import get_config

logger = logging.getLogger(__name__)


class SerperConfig:
    """Manages configuration for Serper API client."""

    BASE_URL = "https://google.serper.dev/search"
    DEFAULT_TIMEOUT = 30
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_LANGUAGE = "en"
    DEFAULT_LOCATION = "United States"
    DEFAULT_COUNTRY_CODE = "us"
    MAX_RESULTS_LIMIT = 100  # Serper API supports up to 100 results per query
    DEFAULT_RESULTS_PER_PAGE = 10  # Serper API pagination size

    def __init__(self):
        """Initialize configuration from settings and core config."""
        self.api_key = self._get_api_key()
        self.core_config = get_config()
        self._validate_config()

    def _get_api_key(self) -> str:
        """Get API key from settings."""
        api_key = getattr(settings, "SERPER_API_KEY", None)
        if not api_key:
            raise ValueError("SERPER_API_KEY not configured in settings")
        return api_key

    def _validate_config(self):
        """Validate configuration values."""
        if not self.api_key:
            raise ValueError("Invalid SERPER_API_KEY")

        # Check if key looks valid (basic format check)
        if len(self.api_key) < 10 or not isinstance(self.api_key, str):
            raise ValueError("SERPER_API_KEY appears to be invalid")

    @property
    def timeout(self) -> int:
        """Get API timeout from config."""
        if hasattr(self.core_config, "api") and hasattr(
            self.core_config.api, "serper_timeout"
        ):
            return self.core_config.api.serper_timeout
        return self.DEFAULT_TIMEOUT

    @property
    def max_retries(self) -> int:
        """Get max retries from config."""
        if hasattr(self.core_config, "api") and hasattr(
            self.core_config.api, "max_retries"
        ):
            return self.core_config.api.max_retries
        return self.DEFAULT_MAX_RETRIES

    @property
    def default_language(self) -> str:
        """Get default language from config."""
        if hasattr(self.core_config, "search") and hasattr(
            self.core_config.search, "default_language"
        ):
            return self.core_config.search.default_language
        return self.DEFAULT_LANGUAGE

    @property
    def default_location(self) -> str | None:
        """Get default location from config.

        Returns ``None`` when no location is configured. Downstream consumers
        treat ``None`` as "no location filter" (see ``SerpQueryExecutor`` and
        ``SerperProcessor.build_request_params``), so the optional type is
        intentional and matches ``SearchConfig.default_location``.
        """
        if hasattr(self.core_config, "search") and hasattr(
            self.core_config.search, "default_location"
        ):
            return self.core_config.search.default_location
        return self.DEFAULT_LOCATION

    @property
    def default_country_code(self) -> str:
        """Get default country code from config."""
        if hasattr(self.core_config, "search") and hasattr(
            self.core_config.search, "default_country_code"
        ):
            return self.core_config.search.default_country_code
        return self.DEFAULT_COUNTRY_CODE

    def get_http_client_config(self) -> dict:
        """Get configuration for HTTP client."""
        return {
            "base_url": self.BASE_URL,
            "api_key": self.api_key,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }

    def get_search_defaults(self) -> dict:
        """Get default search parameters."""
        return {
            "language": self.default_language,
            "location": self.default_location,
            "country_code": self.default_country_code,
            "max_results": self.MAX_RESULTS_LIMIT,
        }
