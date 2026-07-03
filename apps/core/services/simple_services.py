"""
Ultra-Simple Architecture Services - Refactored with BaseService Framework

DEPRECATION NOTICE:
This module has been decomposed into focused modules for better maintainability.
All classes are now imported from their new locations for backward compatibility.

New Module Structure:
- exceptions.py: All exception classes
- serper_client.py: SerperClient
- rate_limiter.py: TokenBucketRateLimiter
- result_processor.py: SearchResultProcessor
- url_deduplication.py: URLDeduplicationService
- database_state.py: DatabaseStateManager
- cache_manager.py: RedisCacheManager
- retry_manager.py: SimpleRetryManager

For new code, import from the specific modules or from apps.core.services.
This file will be removed in a future version.
"""

# Re-export all classes from their new locations for backward compatibility
from .cache_manager import CacheManagerConfig, RedisCacheManager
from .database_state import DatabaseStateManager, StateManagerConfig
from .exceptions import (
    SerperAuthError,
    SerperConnectionError,
    SerperError,
    SerperQuotaError,
    SerperRateLimitError,
    SerperTimeoutError,
)
from .rate_limiter import RateLimiterConfig, TokenBucketRateLimiter
from .result_processor import ResultProcessorConfig, SearchResultProcessor
from .retry_manager import RetryManagerConfig, SimpleRetryManager
from .url_deduplication import DeduplicationConfig, URLDeduplicationService

# Preserve all exports for backward compatibility
__all__ = [
    # Exception classes
    "SerperError",
    "SerperRateLimitError",
    "SerperAuthError",
    "SerperQuotaError",
    "SerperTimeoutError",
    "SerperConnectionError",
    # Service classes
    "TokenBucketRateLimiter",
    "SearchResultProcessor",
    "URLDeduplicationService",
    "DatabaseStateManager",
    "RedisCacheManager",
    "SimpleRetryManager",
    # Configuration TypedDict classes
    "RateLimiterConfig",
    "ResultProcessorConfig",
    "DeduplicationConfig",
    "StateManagerConfig",
    "CacheManagerConfig",
    "RetryManagerConfig",
]
