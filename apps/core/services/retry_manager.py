"""
Simple Retry Manager Service

Simple error categorization and retry delay calculation.
Replaces complex retry orchestration with straightforward patterns.
"""

import logging
from typing import Dict, TypedDict

from .base import BaseService

logger = logging.getLogger(__name__)


class RetryManagerConfig(TypedDict):
    retry_delays: Dict[str, int]
    max_retries: int
    cache_timeout: int
    exponential_backoff: bool


class SimpleRetryManager(BaseService[RetryManagerConfig]):
    """
    Simple error categorization and retry delay calculation.
    Replaces complex retry orchestration with straightforward patterns.
    """

    SERVICE_NAME = "SimpleRetryManager"
    SERVICE_VERSION = "2.0.0"

    def get_default_config(self) -> RetryManagerConfig:
        """Get default retry manager configuration."""
        return {
            "retry_delays": {
                "rate_limit": 300,  # 5 minutes
                "network": 60,  # 1 minute
                "api": 120,  # 2 minutes
                "timeout": 30,  # 30 seconds
                "unknown": 180,  # 3 minutes (conservative)
            },
            "max_retries": 3,
            "cache_timeout": 300,
            "exponential_backoff": True,
        }

    def _initialize(self) -> None:
        """Initialize retry manager resources."""
        pass  # No special initialization needed

    def health_check(self) -> bool:
        """Check if retry manager is healthy."""
        try:
            # Test error categorization with a sample error
            test_error = Exception("rate limit exceeded")
            category = self.categorize_error(test_error)
            return category == "rate_limit"
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def categorize_error(self, error: Exception) -> str:
        """
        Categorize error for appropriate retry delay.

        Args:
            error: Exception instance

        Returns:
            Error category string
        """
        error_name = error.__class__.__name__
        error_str = str(error).lower()

        # Rate limiting errors
        if (
            "rate" in error_str
            or "limit" in error_str
            or error_name == "SerperRateLimitError"
        ):
            return "rate_limit"

        # Network errors
        if (
            "connection" in error_str
            or "network" in error_str
            or error_name
            in ["ConnectionError", "ConnectTimeout", "SerperConnectionError"]
        ):
            return "network"

        # Timeout errors
        if "timeout" in error_str or error_name in [
            "TimeoutError",
            "SerperTimeoutError",
        ]:
            return "timeout"

        # API errors
        if "api" in error_str or error_name.startswith("Serper"):
            return "api"

        # Default to unknown
        return "unknown"

    def get_retry_delay(self, error: Exception, attempt: int = 1) -> int:
        """
        Calculate retry delay based on error category and attempt.

        Args:
            error: Exception that occurred
            attempt: Retry attempt number (1-based)

        Returns:
            Delay in seconds before retry
        """
        with self._measure_performance("get_retry_delay"):
            category = self.categorize_error(error)
            base_delay = self.config["retry_delays"].get(category, 180)

            # Simple exponential backoff for attempts > 1 if enabled
            if self.config["exponential_backoff"] and attempt > 1:
                backoff_multiplier = min(2 ** (attempt - 1), 4)  # Cap at 4x
                base_delay = int(base_delay * backoff_multiplier)

            self.logger.info(
                f"Retry delay for {category} error (attempt {attempt}): {base_delay}s"
            )
            return base_delay
