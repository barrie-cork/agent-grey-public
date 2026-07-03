"""
Clock synchronization utilities for monitoring.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


def check_clock_health() -> Dict[str, Any]:
    """
    Quick clock health check for monitoring tasks.

    Returns:
        Dict with clock health status
    """
    try:
        # Check if broker URL is configured
        broker_url = getattr(settings, "CELERY_BROKER_URL", None)
        if not broker_url:
            return {
                "status": "unconfigured",
                "drift_seconds": 0,
                "measurement_age_seconds": None,
                "last_check": None,
                "note": "CELERY_BROKER_URL not configured",
            }

        # Skip if using Django database backend
        if broker_url == "django://":
            return {
                "status": "skipped",
                "drift_seconds": 0,
                "measurement_age_seconds": None,
                "last_check": None,
                "note": "Using Django database broker",
            }

        # Get Redis connection
        redis_client = redis.from_url(broker_url)

        # Check if we have recent clock drift data
        key = f"celery:clock_drift:{datetime.now(timezone.utc).strftime('%Y%m%d')}"

        # Get the most recent drift measurement
        latest_data = redis_client.zrange(key, -1, -1, withscores=True)

        if latest_data:
            # Parse the stored data
            import ast

            data_str, timestamp = latest_data[0]
            data = ast.literal_eval(data_str.decode())

            # Check how recent the measurement is
            measurement_age = datetime.now(timezone.utc).timestamp() - timestamp

            if measurement_age < 600:  # Less than 10 minutes old
                return {
                    "status": data.get("status", "unknown"),
                    "drift_seconds": data.get("drift", 0),
                    "measurement_age_seconds": measurement_age,
                    "last_check": datetime.fromtimestamp(
                        timestamp, timezone.utc
                    ).isoformat(),
                }

        # No recent data available
        return {
            "status": "unknown",
            "drift_seconds": 0,
            "measurement_age_seconds": None,
            "last_check": None,
        }

    except Exception as e:
        logger.debug(f"Clock health check failed: {e}")
        return {"status": "error", "drift_seconds": 0, "error": str(e)}


def log_clock_drift_event(drift_seconds: float, worker_name: str | None = None):
    """
    Log a clock drift event for tracking.

    Args:
        drift_seconds: The amount of drift detected
        worker_name: Optional worker name where drift was detected
    """
    try:
        # Check if broker URL is configured
        broker_url = getattr(settings, "CELERY_BROKER_URL", None)
        if not broker_url or broker_url == "django://":
            # Skip logging if not using Redis
            return

        redis_client = redis.from_url(broker_url)

        # Store event
        event_key = "celery:clock_drift:events"
        event_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "drift_seconds": drift_seconds,
            "worker": worker_name or "unknown",
        }

        # Add to list (keep last 100 events)
        redis_client.lpush(event_key, str(event_data))
        redis_client.ltrim(event_key, 0, 99)

        # Set expiry
        redis_client.expire(event_key, 7 * 24 * 3600)  # 7 days

    except Exception as e:
        logger.error(f"Failed to log clock drift event: {e}")
