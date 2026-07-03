"""
PostgreSQL test settings - for integration tests that require full database compatibility.
Resolves SQLite/JSONField compatibility issues mentioned in the development infrastructure PRP.
"""

import os
import sys

import dj_database_url
from decouple import config

from .base import *  # noqa: F403

# Disable django-vite manifest lookup for tests (no frontend build in CI)
DJANGO_VITE_DEV_MODE = True

# Use PostgreSQL for integration tests (resolves JSONField issues)
# Support DATABASE_URL for CI environments
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "test_thesis_grey_db",
            "USER": config("POSTGRES_USER", default="thesis_grey_user"),
            "PASSWORD": config("POSTGRES_PASSWORD", default="secure_password"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
            "TEST": {
                "NAME": "test_thesis_grey_db",
            },
        }
    }

# Keep all migrations enabled for PostgreSQL tests to ensure schema compatibility
# This is important for testing JSONField and other PostgreSQL-specific features

# Use faster password hasher for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable cache for tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Disable django-cachalot in tests (DummyCache not supported, avoid test interference)
CACHALOT_ENABLED = False

# Disable Celery for tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable Celery Beat schedule for tests (prevents Redis lookup errors)
CELERY_BEAT_SCHEDULE = {}

# Use in-memory broker for tests (no Redis dependency)
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# Test-specific logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "ERROR",  # Only show errors in tests
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "ERROR",
    },
}

# Test database optimization
if "test" in sys.argv:
    # Close connections immediately to prevent pool exhaustion
    DATABASES["default"]["CONN_MAX_AGE"] = 0

    # Prevent deadlocks in parallel execution
    TEST_NON_SERIALIZED_APPS = []  # Force serialization for all apps

# Test runner configuration for better isolation
TEST_RUNNER = "django.test.runner.DiscoverRunner"
TEST_RUNNER_OPTIONS = {
    "shuffle": False,  # Consistent test order
    "debug_mode": True,  # Better error messages
}
