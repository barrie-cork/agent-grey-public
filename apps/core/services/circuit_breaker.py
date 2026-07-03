"""
Advanced Circuit Breaker implementation with Redis state storage

Phase 3 implementation with enhanced features:
- Dynamic configuration via Constance
- Comprehensive statistics tracking
- SSE notifications via ProgressTracker
- Emergency management controls
"""

import json
import logging
import os
from datetime import datetime

import pybreaker
import sentry_sdk

from apps.core.utils.redis_utils import get_safe_redis_connection

# Progress tracker removed - using simple status updates

logger = logging.getLogger(__name__)


def _cast_bool(value: str) -> bool:
    """Cast string value to boolean."""
    return value.lower() in ("true", "1", "yes", "on")


def _cast_int(value: str) -> int:
    """Cast string value to integer with error handling."""
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"Cannot cast '{value}' to int")


def _cast_float(value: str) -> float:
    """Cast string value to float with error handling."""
    try:
        return float(value)
    except (ValueError, TypeError):
        raise ValueError(f"Cannot cast '{value}' to float")


def _get_constance_value(key: str):
    """Try to get value from django-constance configuration."""
    try:
        from constance import config

        value = getattr(config, key, None)
        if value is not None:
            return value
    except Exception as e:
        logger.debug(f"Constance not available for {key}, using environment: {e}")
    return None


def _cast_env_value(env_value: str, value_type):
    """Cast environment value to the specified type."""
    if value_type is bool:
        return _cast_bool(env_value)
    elif value_type is int:
        try:
            return _cast_int(env_value)
        except ValueError:
            return None
    elif value_type is float:
        try:
            return _cast_float(env_value)
        except ValueError:
            return None
    return env_value


def _get_config_value(key: str, default=None, value_type=None):
    """
    Get configuration value with fallback to environment variables.

    This function provides safe access to django-constance config values
    with automatic fallback to environment variables when constance is
    not yet available (e.g., during migrations).

    Args:
        key: Configuration key name
        default: Default value if not found
        value_type: Type to cast the value to (bool, int, float)

    Returns:
        Configuration value from constance or environment, or default
    """
    # Try to get from constance first
    value = _get_constance_value(key)
    if value is not None:
        return value

    # Fall back to environment variable
    env_value = os.environ.get(key)
    if env_value is not None:
        casted_value = _cast_env_value(env_value, value_type)
        if casted_value is not None:
            return casted_value
        # If casting failed but we have a value, return the original string
        return env_value

    # Return default if nothing found
    return default


class RedisCircuitBreakerStorage(pybreaker.CircuitBreakerStorage):
    """
    Enhanced Redis-based storage for distributed circuit breaker state.

    Features:
    - State persistence across distributed workers
    - Comprehensive statistics tracking
    - Real-time notifications via SSE
    - Historical data for analysis
    """

    def __init__(self, name: str):
        # Add defensive check BEFORE setting self._name
        if hasattr(self, "name"):
            raise ValueError(
                "Cannot use 'name' attribute - conflicts with PyBreaker internal property. "
                "This is a known PyBreaker 1.2.0 issue."
            )

        # CRITICAL: Use self._name to avoid property conflict with PyBreaker
        self._name = name
        self._redis = None
        self._key_prefix = f"breaker:{self._name}"

    @property
    def redis(self):
        """Lazy Redis connection initialization with safe wrapper."""
        if self._redis is None:
            self._redis = get_safe_redis_connection("default")
        return self._redis

    def _get_key(self, suffix: str) -> str:
        """Generate Redis key with proper namespace."""
        return f"{self._key_prefix}:{suffix}"

    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        state = self.redis.get(self._get_key("state"))
        if isinstance(state, bytes):
            return state.decode("utf-8")
        elif isinstance(state, str):
            return state
        else:
            return pybreaker.STATE_CLOSED

    @state.setter
    def state(self, value: str) -> None:
        """Set circuit breaker state with TTL and notifications."""
        old_state = self.state
        self.redis.setex(self._get_key("state"), 3600, value)

        # Log state change
        logger.warning(
            f"Circuit breaker '{self._name}' state changed from {old_state} to {value}"
        )

        # Track state changes in history
        if _get_config_value("CB_COLLECT_STATISTICS", default=True, value_type=bool):
            self._record_state_change(old_state, value)

        # Send alerts based on configuration
        if (
            _get_config_value("CB_NOTIFY_ON_OPEN", default=True, value_type=bool)
            and value == pybreaker.STATE_OPEN
        ):
            self._notify_state_change(old_state, value)
            sentry_sdk.capture_message(
                f"Circuit breaker {self._name} OPENED after {self.counter} failures",
                level="warning",
            )
        elif value == pybreaker.STATE_CLOSED and old_state == pybreaker.STATE_OPEN:
            sentry_sdk.capture_message(
                f"Circuit breaker {self._name} recovered and CLOSED", level="info"
            )

    @property
    def counter(self) -> int:
        """Get current failure counter."""
        count = self.redis.get(self._get_key("counter"))
        if count:
            try:
                if isinstance(count, bytes):
                    return int(count.decode("utf-8"))
                else:
                    return int(count)
            except (ValueError, TypeError):
                return 0
        return 0

    @counter.setter
    def counter(self, value: int) -> None:
        """Set failure counter with TTL."""
        if value == 0:
            self.redis.delete(self._get_key("counter"))
        else:
            # Counter expires after 5 minutes of inactivity
            self.redis.setex(self._get_key("counter"), 300, str(value))

    def increment_counter(self) -> int:
        """Increment failure counter atomically."""
        new_count = self.redis.incr(self._get_key("counter"))
        # Reset TTL on each increment
        self.redis.expire(self._get_key("counter"), 300)

        # Track failure in statistics
        if _get_config_value("CB_COLLECT_STATISTICS", default=True, value_type=bool):
            self._record_failure()

        return new_count

    def reset_counter(self) -> None:
        """Reset failure counter."""
        self.redis.delete(self._get_key("counter"))

    @property
    def opened_at(self):
        """Get timestamp when circuit was opened.

        Returns:
            datetime or None: Datetime when circuit opened, None if not opened
        """
        opened = self.redis.get(self._get_key("opened_at"))
        if opened:
            try:
                if isinstance(opened, bytes):
                    timestamp = float(opened.decode("utf-8"))
                else:
                    timestamp = float(opened)
                # Convert timestamp to datetime for pybreaker compatibility
                return datetime.fromtimestamp(timestamp)
            except (ValueError, TypeError):
                return None
        return None

    @opened_at.setter
    def opened_at(self, value) -> None:
        """Set timestamp when circuit opened."""
        if value:
            # Store as timestamp for Redis persistence
            if isinstance(value, datetime):
                self.redis.setex(
                    self._get_key("opened_at"), 3600, str(value.timestamp())
                )
            elif isinstance(value, (int, float)):
                self.redis.setex(self._get_key("opened_at"), 3600, str(value))
            else:
                # Fallback - use current time
                self.redis.setex(
                    self._get_key("opened_at"), 3600, str(datetime.now().timestamp())
                )
        else:
            self.redis.delete(self._get_key("opened_at"))

    # Enhanced features for Phase 3

    def _record_state_change(self, old_state: str, new_state: str) -> None:
        """Record state change in history for analysis."""
        history_key = self._get_key("history")
        timestamp = datetime.now().isoformat()

        history_entry = json.dumps(
            {
                "timestamp": timestamp,
                "old_state": old_state,
                "new_state": new_state,
                "failures_at_change": self.counter,
            }
        )

        # Keep last 100 state changes
        self.redis.lpush(history_key, history_entry)
        self.redis.ltrim(history_key, 0, 99)
        self.redis.expire(history_key, 86400)  # Expire after 24 hours

    def _record_failure(self) -> None:
        """Record failure in statistics."""
        stats_key = self._get_key("stats:failures")
        today = datetime.now().strftime("%Y-%m-%d")

        # Increment daily failure count
        self.redis.hincrby(stats_key, today, 1)
        self.redis.expire(stats_key, 604800)  # Keep for 7 days

    def _notify_state_change(self, old_state: str, new_state: str) -> None:
        """Log state change (SSE removed)."""
        try:
            # Simple logging instead of SSE notifications
            logger.info(
                f"Circuit breaker {self._name}: {old_state} → {new_state}",
                extra={
                    "breaker": self._name,
                    "old_state": old_state,
                    "new_state": new_state,
                    "timestamp": datetime.now().isoformat(),
                    "failure_count": self.counter,
                },
            )
        except Exception as e:
            logger.error(f"Failed to log state change: {e}")

    def get_statistics(self):
        """Get comprehensive circuit breaker statistics.

        Returns:
            dict: Dictionary containing circuit breaker statistics with keys:
                - current_state, failure_count, opened_at, is_closed, is_open,
                  is_half_open, recent_state_changes, daily_failures, etc.
        """
        stats = {
            "current_state": self.state,
            "failure_count": self.counter,
            "opened_at": self.opened_at,
            "is_closed": self.state == pybreaker.STATE_CLOSED,
            "is_open": self.state == pybreaker.STATE_OPEN,
            "is_half_open": self.state == pybreaker.STATE_HALF_OPEN,
        }

        # Add historical data if statistics collection is enabled
        if _get_config_value("CB_COLLECT_STATISTICS", default=True, value_type=bool):
            # Get state change history
            history_key = self._get_key("history")
            history = self.redis.lrange(history_key, 0, 9)  # Last 10 changes
            stats["recent_state_changes"] = [
                json.loads(entry.decode("utf-8") if isinstance(entry, bytes) else entry)
                for entry in history
            ]

            # Get failure statistics
            stats_key = self._get_key("stats:failures")
            daily_failures = self.redis.hgetall(stats_key)
            stats["daily_failures"] = {
                (k.decode("utf-8") if isinstance(k, bytes) else k): int(
                    v.decode("utf-8") if isinstance(v, bytes) else v
                )
                for k, v in daily_failures.items()
            }

            # Calculate recovery time if applicable
            if self.opened_at:
                recovery_time = (datetime.now() - self.opened_at).total_seconds()
                stats["time_in_open_state"] = recovery_time

        return stats

    def reset(self) -> None:
        """Complete reset of circuit breaker state and statistics."""
        pattern = f"{self._key_prefix}:*"
        for key in self.redis.scan_iter(match=pattern):
            self.redis.delete(key)
        logger.info(f"Circuit breaker '{self._name}' has been reset")


class CircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """
    Enhanced listener for circuit breaker state changes.

    Provides:
    - Sentry integration for alerting
    - SSE notifications for real-time updates
    - Logging for audit trail
    """

    def state_change(self, cb, old_state, new_state):
        """Handle circuit breaker state changes."""
        breaker_name = getattr(cb, "name", "Unknown")

        # Log state change
        if new_state == pybreaker.STATE_OPEN:
            logger.error(f"Circuit breaker '{breaker_name}' OPENED from {old_state}")
        elif new_state == pybreaker.STATE_CLOSED:
            logger.info(f"Circuit breaker '{breaker_name}' CLOSED from {old_state}")
        else:
            logger.warning(
                f"Circuit breaker '{breaker_name}' changed from {old_state} to {new_state}"
            )

        # Send Sentry alert for significant state changes
        try:
            if new_state == pybreaker.STATE_OPEN and _get_config_value(
                "CB_NOTIFY_ON_OPEN", default=True, value_type=bool
            ):
                with sentry_sdk.new_scope() as scope:
                    scope.set_extra("old_state", old_state)
                    scope.set_extra("new_state", new_state)
                    scope.set_extra("timestamp", datetime.now().isoformat())
                    sentry_sdk.capture_message(
                        f"Circuit breaker {breaker_name} is now OPEN",
                        level="warning",
                    )
            elif (
                new_state == pybreaker.STATE_CLOSED
                and old_state == pybreaker.STATE_OPEN
            ):
                sentry_sdk.capture_message(
                    f"Circuit breaker {breaker_name} recovered and is now CLOSED",
                    level="info",
                )
        except Exception as e:
            logger.error(f"Failed to send Sentry alert: {e}")

    def failure(self, cb, exc):
        """Handle circuit breaker failure."""
        breaker_name = getattr(cb, "name", "Unknown")
        logger.debug(f"Circuit breaker '{breaker_name}' recorded failure: {exc}")

    def success(self, cb):
        """Handle circuit breaker success."""
        breaker_name = getattr(cb, "name", "Unknown")
        logger.debug(f"Circuit breaker '{breaker_name}' recorded success")


class DynamicCircuitBreaker:
    """
    Factory for creating circuit breakers with dynamic Constance configuration.

    This allows runtime adjustment of circuit breaker parameters without
    restarting the application.
    """

    @staticmethod
    def create_serper_breaker():
        """Create Serper API circuit breaker with dynamic configuration."""
        use_breakers = _get_config_value(
            "USE_CIRCUIT_BREAKERS", default=True, value_type=bool
        )

        if not use_breakers:
            # Return a dummy breaker that never opens
            return pybreaker.CircuitBreaker(
                fail_max=float("inf"), reset_timeout=0, name="SerperAPI_Disabled"
            )

        fail_max = _get_config_value(
            "CB_SERPER_API_FAIL_MAX", default=5, value_type=int
        )
        reset_timeout = _get_config_value(
            "CB_SERPER_API_RESET_TIMEOUT", default=60, value_type=int
        )

        breaker = pybreaker.CircuitBreaker(
            fail_max=fail_max,
            reset_timeout=reset_timeout,
            state_storage=RedisCircuitBreakerStorage("serper_api"),
            name="SerperAPI",
        )

        # Add listener for monitoring
        breaker.add_listeners(CircuitBreakerListener())

        return breaker

    @staticmethod
    def create_database_breaker():
        """Create database circuit breaker with dynamic configuration."""
        use_breakers = _get_config_value(
            "USE_CIRCUIT_BREAKERS", default=True, value_type=bool
        )

        if not use_breakers:
            return pybreaker.CircuitBreaker(
                fail_max=float("inf"), reset_timeout=0, name="Database_Disabled"
            )

        fail_max = _get_config_value("CB_DATABASE_FAIL_MAX", default=3, value_type=int)
        reset_timeout = _get_config_value(
            "CB_DATABASE_RESET_TIMEOUT", default=120, value_type=int
        )

        breaker = pybreaker.CircuitBreaker(
            fail_max=fail_max,
            reset_timeout=reset_timeout,
            state_storage=RedisCircuitBreakerStorage("database"),
            name="Database",
        )

        breaker.add_listeners(CircuitBreakerListener())

        return breaker

    @staticmethod
    def get_breaker_status(breaker_name: str):
        """Get status of a specific circuit breaker.

        Returns:
            dict: Circuit breaker statistics dictionary
        """
        storage = RedisCircuitBreakerStorage(breaker_name)
        return storage.get_statistics()

    @staticmethod
    def reset_breaker(breaker_name: str) -> None:
        """Reset a specific circuit breaker."""
        storage = RedisCircuitBreakerStorage(breaker_name)
        storage.reset()
        logger.info(f"Circuit breaker '{breaker_name}' has been manually reset")

    @staticmethod
    def get_all_breakers_status():
        """Get status of all configured circuit breakers.

        Returns:
            dict: Dictionary mapping breaker names to their statistics dictionaries
        """
        breakers = ["serper_api", "database"]
        status = {}

        for breaker_name in breakers:
            try:
                storage = RedisCircuitBreakerStorage(breaker_name)
                status[breaker_name] = storage.get_statistics()
            except Exception as e:
                logger.error(f"Failed to get status for breaker '{breaker_name}': {e}")
                status[breaker_name] = {"error": str(e)}

        return status


# Lazy initialization for circuit breakers to avoid import-time Redis connections
_serper_circuit_breaker = None
_database_circuit_breaker = None


def get_serper_circuit_breaker():
    """Get or create the Serper API circuit breaker with lazy initialization."""
    global _serper_circuit_breaker
    if _serper_circuit_breaker is None:
        _serper_circuit_breaker = DynamicCircuitBreaker.create_serper_breaker()
    return _serper_circuit_breaker


def get_database_circuit_breaker():
    """Get or create the database circuit breaker with lazy initialization."""
    global _database_circuit_breaker
    if _database_circuit_breaker is None:
        _database_circuit_breaker = DynamicCircuitBreaker.create_database_breaker()
    return _database_circuit_breaker


# Create lazy proxy objects for backward compatibility
class LazyCircuitBreaker:
    """Lazy proxy for circuit breaker that initializes on first access."""

    def __init__(self, getter_func):
        self._getter = getter_func

    def __getattr__(self, name):
        return getattr(self._getter(), name)

    def __call__(self, *args, **kwargs):
        return self._getter()(*args, **kwargs)


# Maintain backward compatibility with existing imports
serper_circuit_breaker = LazyCircuitBreaker(get_serper_circuit_breaker)
database_circuit_breaker = LazyCircuitBreaker(get_database_circuit_breaker)


# Utility functions for circuit breaker management
def get_circuit_breaker_status():
    """Get comprehensive status of all circuit breakers.

    Returns:
        dict: Dictionary with keys 'enabled', 'breakers', 'configuration'
    """
    return {
        "enabled": _get_config_value(
            "USE_CIRCUIT_BREAKERS", default=True, value_type=bool
        ),
        "breakers": DynamicCircuitBreaker.get_all_breakers_status(),
        "configuration": {
            "serper_api": {
                "fail_max": _get_config_value(
                    "CB_SERPER_API_FAIL_MAX", default=5, value_type=int
                ),
                "reset_timeout": _get_config_value(
                    "CB_SERPER_API_RESET_TIMEOUT", default=60, value_type=int
                ),
            },
            "database": {
                "fail_max": _get_config_value(
                    "CB_DATABASE_FAIL_MAX", default=3, value_type=int
                ),
                "reset_timeout": _get_config_value(
                    "CB_DATABASE_RESET_TIMEOUT", default=120, value_type=int
                ),
            },
        },
    }


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers to closed state."""
    for breaker_name in ["serper_api", "database"]:
        DynamicCircuitBreaker.reset_breaker(breaker_name)
    logger.info("All circuit breakers have been reset")
