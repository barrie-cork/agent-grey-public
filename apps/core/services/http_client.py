"""
HTTP client service for API requests.
Handles connection pooling, retries, and timeout configuration.
"""

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from apps.core.config import get_config

logger = logging.getLogger(__name__)


class HTTPClient:
    """
    Configurable HTTP client with retry logic and connection pooling.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int | None = None,
        max_retries: int | None = None,
    ):
        """
        Initialize HTTP client.

        Args:
            base_url: Base URL for API
            api_key: API authentication key
            timeout: Request timeout in seconds (uses config if None)
            max_retries: Maximum retry attempts (uses config if None)
        """
        self.base_url = base_url
        self.api_key = api_key

        # Get configuration
        config = get_config()
        self.timeout = timeout or config.api.serper_timeout
        self.max_retries = max_retries or config.api.max_retries

        # Create session
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """
        Create a requests session with retry logic and connection pooling.

        Returns:
            Configured requests Session
        """
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            backoff_factor=1,
            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy, pool_connections=10, pool_maxsize=20
        )

        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update(
            {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "ThesisGrey/1.0",
            }
        )

        return session

    def get(self, endpoint: str, params=None) -> requests.Response:
        """
        Make a GET request.

        Args:
            endpoint: API endpoint (relative to base_url)
            params: Query parameters

        Returns:
            Response object

        Raises:
            requests.RequestException: On request failure
        """
        url = f"{self.base_url}{endpoint}" if endpoint else self.base_url

        logger.debug(f"GET request to {url} with params: {params}")

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response

        except requests.exceptions.Timeout:
            logger.error(f"Request timeout after {self.timeout}s: {url}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise

    def post(self, endpoint: str, json_data=None, data=None) -> requests.Response:
        """
        Make a POST request.

        Args:
            endpoint: API endpoint (relative to base_url)
            json_data: JSON data to send
            data: Form data to send

        Returns:
            Response object

        Raises:
            requests.RequestException: On request failure
        """
        url = f"{self.base_url}{endpoint}" if endpoint else self.base_url

        logger.debug(f"POST request to {url}")

        try:
            response = self.session.post(
                url, json=json_data, data=data, timeout=self.timeout
            )
            response.raise_for_status()
            return response

        except requests.exceptions.Timeout:
            logger.error(f"Request timeout after {self.timeout}s: {url}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise

    def close(self):
        """Close the session and clean up resources."""
        self.session.close()
