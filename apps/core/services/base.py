"""
Base service class providing common patterns and functionality.

This module implements the BaseService abstract framework as specified in the
PRP refactoring plan, providing consistent patterns for service initialization,
error handling, health checks, and metrics tracking.
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, Generic, Mapping, Optional, TypeVar, cast

from django.conf import settings
from django.utils import timezone

# Generic type for service configuration
ServiceConfigType = TypeVar("ServiceConfigType", bound=Mapping[str, Any])


class ServiceMetrics:
    """Service metrics tracking for monitoring and observability."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.total_processing_time = 0.0
        self.created_at = timezone.now()
        self.last_reset = timezone.now()

    def record_request(self, duration_ms: float, success: bool) -> None:
        """Record a service request with timing and success status."""
        self.request_count += 1
        self.total_processing_time += duration_ms

        if success:
            self.success_count += 1
        else:
            self.error_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get current service statistics."""
        uptime = timezone.now() - self.created_at

        return {
            "service_name": self.service_name,
            "request_count": self.request_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": (self.success_count / max(self.request_count, 1)) * 100,
            "avg_response_time_ms": self.total_processing_time
            / max(self.request_count, 1),
            "uptime_seconds": uptime.total_seconds(),
            "last_reset": self.last_reset.isoformat(),
        }

    def reset(self) -> None:
        """Reset all metrics counters."""
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.total_processing_time = 0.0
        self.last_reset = timezone.now()


class BaseService(ABC, Generic[ServiceConfigType]):
    """
    Abstract base class for all services with common patterns.

    Provides:
    - Consistent initialization and configuration loading
    - Error handling and logging
    - Health checks and service status
    - Metrics tracking and monitoring
    - Caching capabilities
    """

    SERVICE_NAME: str = "BaseService"
    SERVICE_VERSION: str = "1.0.0"

    def __init__(self, config: Optional[ServiceConfigType] = None):
        """
        Initialize the service with configuration.

        Args:
            config: Optional service-specific configuration
        """
        # Load configuration from multiple sources
        self.config = self._load_configuration(config)

        # Initialize logging
        self.logger = logging.getLogger(self.__class__.__name__)

        # Initialize metrics tracking
        self.metrics = ServiceMetrics(self.SERVICE_NAME)

        # Cache for service-level data
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._cache_timeouts: Dict[str, timedelta] = {}
        self._cache_timeout = timedelta(
            seconds=self.config.get("cache_timeout", 300)
        )  # 5 minutes default

        # Service state
        self._initialized = False
        self._last_health_check: Optional[datetime] = None
        self._last_health_status: bool = True

        # Initialize service-specific resources
        try:
            self._initialize()
            self._initialized = True
            self.logger.info(
                f"{self.SERVICE_NAME} v{self.SERVICE_VERSION} initialized successfully"
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize {self.SERVICE_NAME}: {e}")
            raise

    @abstractmethod
    def _initialize(self) -> None:
        """Initialize service-specific resources. Must be implemented by subclasses."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if service is healthy and operational.

        Returns:
            True if service is healthy, False otherwise
        """
        pass

    def get_default_config(self) -> ServiceConfigType:
        """
        Get default configuration for this service.
        Override in subclasses to provide service-specific defaults.

        Returns:
            Default configuration dictionary
        """
        return {}  # type: ignore[reportReturnType]

    def _load_configuration(
        self, provided_config: Optional[ServiceConfigType]
    ) -> ServiceConfigType:
        """
        Load configuration from multiple sources with precedence:
        1. Provided config (highest priority)
        2. Django settings (SERVICE_NAME_CONFIG)
        3. Default config (lowest priority)
        """
        # Build as a mutable dict so we can call .update(); cast back to ServiceConfigType
        # on return (TypedDicts are plain dicts at runtime so the cast is safe).
        config: Dict[str, Any] = dict(self.get_default_config())

        # Update with Django settings if available
        settings_key = f"{self.SERVICE_NAME.upper()}_CONFIG"
        if hasattr(settings, settings_key):
            django_config = getattr(settings, settings_key)
            if isinstance(django_config, dict):
                config.update(django_config)

        # Update with provided config (highest priority)
        if provided_config:
            config.update(provided_config)

        return cast(ServiceConfigType, config)

    def _handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        operation: str = "unknown",
    ) -> None:
        """
        Common error handling with logging and metrics.

        Args:
            error: The exception that occurred
            context: Additional context for debugging
            operation: Name of the operation that failed
        """
        error_context = {
            "service": self.SERVICE_NAME,
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }

        if context:
            error_context.update(context)

        self.logger.error(
            f"Service error in {self.SERVICE_NAME}.{operation}: "
            f"{type(error).__name__}: {error}",
            extra=error_context,
            exc_info=True,
        )

        # Update metrics
        self.metrics.error_count += 1

    def _measure_performance(self, operation_name: str):
        """
        Context manager for measuring operation performance.

        Usage:
            with self._measure_performance("my_operation"):
                # Your operation here
                pass
        """
        return PerformanceMeasurer(self.metrics, operation_name)

    def get_cached_value(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the service cache.

        Args:
            key: Cache key
            default: Default value if key not found or expired

        Returns:
            Cached value or default
        """
        if key not in self._cache or key not in self._cache_timestamps:
            return default

        # Check if cache entry has expired (per-key timeout overrides default)
        entry_timeout = self._cache_timeouts.get(key, self._cache_timeout)
        if timezone.now() - self._cache_timestamps[key] > entry_timeout:
            self.invalidate_cache(key)
            return default

        return self._cache.get(key, default)

    def set_cached_value(
        self, key: str, value: Any, timeout: int | None = None
    ) -> None:
        """
        Set a value in the service cache.

        Args:
            key: Cache key
            value: Value to cache
            timeout: Cache timeout in seconds (overrides default if provided)
        """
        self._cache[key] = value
        self._cache_timestamps[key] = timezone.now()
        if timeout is not None:
            self._cache_timeouts[key] = timedelta(seconds=timeout)
        else:
            self._cache_timeouts.pop(key, None)

    def invalidate_cache(self, key: Optional[str] = None) -> None:
        """
        Invalidate cache entries.

        Args:
            key: Specific key to invalidate, or None to clear all
        """
        if key:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
            self._cache_timeouts.pop(key, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
            self._cache_timeouts.clear()


class PerformanceMeasurer:
    """Context manager for measuring operation performance."""

    def __init__(self, metrics: ServiceMetrics, operation_name: str):
        self.metrics = metrics
        self.operation_name = operation_name
        self.start_time: float = 0
        self.success = True
        self.logger = logging.getLogger(f"Performance.{operation_name}")

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        self.success = exc_type is None

        # Record metrics
        self.metrics.record_request(duration_ms, self.success)

        # Log performance if it's slow
        if duration_ms > 1000:  # Log operations slower than 1 second
            self.logger.warning(
                f"Slow operation: {self.operation_name} took {duration_ms:.2f}ms"
            )
        elif duration_ms > 100:  # Debug log for operations slower than 100ms
            self.logger.debug(
                f"Operation timing: {self.operation_name} took {duration_ms:.2f}ms"
            )
