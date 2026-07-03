"""
Test settings - Uses PostgreSQL when DATABASE_URL is available (GitHub Actions),
falls back to SQLite for quick local tests.

Note: SearchStrategy model uses ArrayField which requires PostgreSQL.
SQLite tests will fail on migrations - use DATABASE_URL env var for full compatibility.
"""

import logging
import os

# Configure minimal logging BEFORE importing base to reduce noise
logging.basicConfig(
    level=logging.WARNING,
    format="[%(levelname)s] %(message)s",
)

# Silence noisy loggers before they get initialized
for logger_name in [
    "urllib3",
    "PIL",
]:
    logging.getLogger(logger_name).setLevel(logging.ERROR)

from .base import *

# Disable django-vite manifest lookup for tests (no frontend build in CI)
DJANGO_VITE_DEV_MODE = True

# Provide a dummy API key so SerperConfig doesn't raise in tests
SERPER_API_KEY = "test-api-key-for-ci"

# Use PostgreSQL if DATABASE_URL is set (GitHub Actions, production-like tests)
# Otherwise fall back to SQLite for quick local tests (will fail on ArrayField migrations)
if "DATABASE_URL" in os.environ:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            os.environ["DATABASE_URL"],
            conn_max_age=0,
            conn_health_checks=False,
        )
    }
else:
    # SQLite fallback for local quick tests
    # WARNING: Will fail on SearchStrategy migrations due to ArrayField
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test_db.sqlite3",  # noqa: F405
        }
    }


# NOTE: Migrations MUST be enabled for tests to work correctly
# Signal registration in apps.review_manager requires django_content_type table
# which is only created by running migrations. Disabling migrations causes:
# "sqlite3.OperationalError: no such table: django_content_type"
#
# Django automatically optimizes test migrations, and --keepdb flag in CI
# provides additional speed benefits. If test speed becomes an issue, consider
# using --parallel flag or test database fixtures instead of disabling migrations.

# Use faster password hasher for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Use in-memory cache for tests (required for cache-dependent tests)
# LocMemCache provides functional caching without external dependencies
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}

# Disable django-cachalot in tests (avoid caching interference with test isolation)
CACHALOT_ENABLED = False

# Disable Celery for tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable Celery Beat schedule for tests (prevents Redis lookup errors)
CELERY_BEAT_SCHEDULE = {}

# Use in-memory broker for tests (no Redis dependency)
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# Test-specific logging - only warnings and errors
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "WARNING",  # Only show warnings and errors
        },
    },
    "loggers": {
        # Silence noisy third-party loggers
        "urllib3": {
            "level": "ERROR",
        },
        "PIL": {
            "level": "ERROR",
        },
        # Keep Django loggers at WARNING
        "django": {
            "level": "WARNING",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# Override Constance backend to use memory instead of database
# This prevents "relation constance_constance does not exist" errors during test setup
# when app initialization code tries to access constance.config before migrations run
CONSTANCE_BACKEND = "constance.backends.memory.MemoryBackend"

# Disable Vite manifest lookup in tests (manifest is not built in CI)
# DEV_MODE outputs dev-server URLs without reading manifest.json
DJANGO_VITE_DEV_MODE = True
