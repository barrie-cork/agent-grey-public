"""Third-party integrations configuration.

This module provides centralized initialization for external services
to eliminate duplicate integration code across settings files.

Created: 2025-10-17
Purpose: Phase 2 of Post-Deployment Refactoring Plan
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PostHogClient:
    """Thin wrapper around the PostHog Python SDK.

    Initialises lazily on first use and gates all calls behind
    POSTHOG_ENABLED so callers never need to check the flag themselves.
    """

    _client: Any = None
    _initialised: bool = False

    @classmethod
    def _ensure_initialised(cls) -> bool:
        """Initialise the PostHog client once, return True if ready."""
        if cls._initialised:
            return cls._client is not None

        cls._initialised = True

        try:
            from django.conf import settings

            if not getattr(settings, "POSTHOG_ENABLED", False):
                logger.debug("PostHog disabled via settings")
                return False

            api_key = getattr(settings, "POSTHOG_API_KEY", "")
            host = getattr(settings, "POSTHOG_HOST", "https://eu.i.posthog.com")

            if not api_key:
                logger.info("PostHog disabled: POSTHOG_API_KEY not set")
                return False

            import posthog

            posthog.project_api_key = api_key
            posthog.host = host
            cls._client = posthog

            # Flush pending events on interpreter shutdown
            atexit.register(posthog.shutdown)

            logger.info("PostHog SDK initialised (host=%s)", host)
            return True

        except ImportError:
            logger.warning("posthog package not installed")
            return False
        except Exception as exc:
            logger.error("Failed to initialise PostHog: %s", exc)
            return False

    @classmethod
    def capture(
        cls,
        user: Any,
        event: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Send an event to PostHog."""
        if not cls._ensure_initialised():
            return
        try:
            distinct_id = str(user.pk) if hasattr(user, "pk") else str(user)
            cls._client.capture(distinct_id, event, properties=properties or {})
        except Exception as exc:
            logger.warning("PostHog capture failed: %s", exc)

    @classmethod
    def identify(
        cls,
        user: Any,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Identify a user in PostHog."""
        if not cls._ensure_initialised():
            return
        try:
            distinct_id = str(user.pk) if hasattr(user, "pk") else str(user)
            cls._client.identify(distinct_id, properties=properties or {})
        except Exception as exc:
            logger.warning("PostHog identify failed: %s", exc)

    @classmethod
    def reset(cls) -> None:
        """Reset client state (useful for testing)."""
        cls._client = None
        cls._initialised = False


class SentryInitializer:
    """Initialize Sentry with consistent configuration.

    Consolidates 200+ lines of Sentry initialization from production.py,
    staging.py, and local.py into a single reusable utility.
    """

    @staticmethod
    def initialize(
        environment: str,
        dsn: Optional[str] = None,
        traces_sample_rate: float = 0.02,
        profiles_sample_rate: float = 0.0,
        **kwargs: Any,
    ) -> bool:
        """Initialize Sentry SDK.

        Args:
            environment: Environment name (production, staging, local_development)
            dsn: Sentry DSN (defaults to SENTRY_DSN env var)
            traces_sample_rate: Percentage of transactions to trace (0.0-1.0)
            profiles_sample_rate: Percentage of transactions to profile (0.0-1.0)
            **kwargs: Additional sentry_sdk.init() arguments

        Returns:
            True if Sentry initialized successfully, False otherwise
        """
        # Get DSN from environment if not provided
        dsn = dsn or os.environ.get("SENTRY_DSN", "")

        # Validate DSN format
        if not dsn or not dsn.strip():
            logger.info("Sentry disabled: SENTRY_DSN not configured")
            return False

        if not dsn.startswith(("http://", "https://")):
            logger.warning(
                "Sentry disabled: Invalid DSN format (must start with http:// or https://)"
            )
            return False

        try:
            import sentry_sdk

            integrations = SentryInitializer._build_integrations()
            SentryInitializer._apply_defaults(kwargs)

            sentry_sdk.init(
                dsn=dsn,
                environment=environment,
                traces_sample_rate=traces_sample_rate,
                profiles_sample_rate=profiles_sample_rate,
                integrations=integrations,
                **kwargs,
            )

            logger.info(
                f"Sentry SDK initialized successfully for {environment} environment"
            )
            return True

        except ImportError as e:
            logger.warning(f"Sentry libraries not available: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Sentry: {e}")
            return False

    @staticmethod
    def _build_integrations() -> list:
        """Build the list of Sentry SDK integrations."""
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        return [
            DjangoIntegration(
                transaction_style="url",
                middleware_spans=True,
                signals_spans=True,
                cache_spans=True,
            ),
            CeleryIntegration(
                monitor_beat_tasks=True,
                propagate_traces=True,
            ),
            RedisIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ]

    @staticmethod
    def _apply_defaults(kwargs: dict[str, Any]) -> None:
        """Apply production-safe defaults for parameters not provided by caller.

        Callers can override these (e.g., local.py can set send_default_pii=True).
        """
        kwargs.setdefault("send_default_pii", False)
        kwargs.setdefault("max_breadcrumbs", 20)
        kwargs.setdefault("attach_stacktrace", True)
        kwargs.setdefault("auto_session_tracking", False)
        kwargs.setdefault(
            "ignore_errors",
            [
                "Http404",
                "KeyboardInterrupt",
                "SystemExit",
                "DisallowedHost",
                "redis.exceptions.NoScriptError",
            ],
        )
