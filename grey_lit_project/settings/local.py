import logging
import socket

from decouple import config
from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import (
    INSTALLED_APPS,
    LOGGING,
    MIDDLEWARE,
    get_env,
    get_env_int,
)
from .logging import get_logging_config

# Initialize logging for local configuration
logger = logging.getLogger(__name__)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config("DEBUG", default=True, cast=bool)

# Environment identification -- required for system checks in apps/core/checks.py
ENVIRONMENT = "local"

if not DEBUG:
    raise ImproperlyConfigured(
        "local.py settings file requires DEBUG=True. "
        "For non-debug deployments, use production.py or staging.py instead."
    )

# Development CSP Configuration for SSE support
CSP_ENABLED = False  # Disable strict CSP in development for easier debugging
# If you need to test CSP in development, set CSP_ENABLED = True and use:
CSP_CONNECT_SRC = [
    "'self'",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# SECURITY: This default key contains "django-insecure" so Django's deployment
# checks (manage.py check --deploy) will flag it. Never use this in production.
SECRET_KEY = config(
    "SECRET_KEY", default="django-insecure-development-key-not-for-production-use-only"
)

# Add Windows proxy autodiscovery hosts
WINDOWS_PROXY_HOSTS = ["wpad.home", "wpad", "wpad.localdomain"]

# Add Docker internal hostname for E2E testing
DOCKER_INTERNAL_HOSTS = ["host.docker.internal"]

ALLOWED_HOSTS = (
    config(
        "ALLOWED_HOSTS",
        default="localhost,127.0.0.1,0.0.0.0,testserver",
        cast=lambda v: [s.strip() for s in v.split(",")],
    )
    + WINDOWS_PROXY_HOSTS
    + DOCKER_INTERNAL_HOSTS
)

# Development-only apps
INSTALLED_APPS += [
    # "django_extensions",  # Temporarily disabled for Sentry testing
]

# Django Debug Toolbar
INSTALLED_APPS += [
    "debug_toolbar",
]

MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
] + MIDDLEWARE

# For Docker compatibility
hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
INTERNAL_IPS = [
    "127.0.0.1",
    "localhost",
] + [ip[:-1] + "1" for ip in ips]

# Debug toolbar config
# Disabled for E2E testing - the toolbar interferes with Vue SPA rendering
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: False,  # Disabled
    "SHOW_TEMPLATE_CONTEXT": True,
    "ENABLE_STACKTRACES": True,
}

# Development logging - more verbose
LOGGING["loggers"]["apps"]["level"] = "DEBUG"
# SQL query logging - controlled by environment variable
# Set DB_LOG_LEVEL=DEBUG in environment to enable SQL query logging
# Default: WARNING (SQL queries hidden) to reduce log noise
DB_LOG_LEVEL = config("DB_LOG_LEVEL", default="WARNING")
LOGGING["loggers"]["django.db.backends"]["level"] = DB_LOG_LEVEL

# Email backend configuration
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

# SMTP Configuration (when using SMTP backend)
if EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
    EMAIL_HOST = config("EMAIL_HOST", default="")
    EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
    EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
    EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
    EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")

DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL", default="Agent Grey <noreply@localhost>"
)

# Admin configuration for development
ADMINS = [
    ("Developer", config("ADMIN_EMAIL", default="admin@localhost")),
]

# Site domain for development
SITE_DOMAIN = config("SITE_DOMAIN", default="localhost:8000")

# SECURITY: CORS_ALLOW_ALL_ORIGINS=True is acceptable ONLY in local development.
# This must NEVER be set in production or staging -- it would allow any website to
# make authenticated cross-origin requests (combined with CORS_ALLOW_CREDENTIALS
# from base.py). Production uses an explicit CORS_ALLOWED_ORIGINS list.
CORS_ALLOW_ALL_ORIGINS = True

# Celery - Use eager mode for development/testing
CELERY_TASK_ALWAYS_EAGER = config("CELERY_TASK_ALWAYS_EAGER", default=False, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True

# Static files
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Redis Cache Configuration for Development
# Use Redis to match production behavior
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379/0"),
        "OPTIONS": {
            "CONNECTION_POOL_KWARGS": {
                "max_connections": 50,
                "retry_on_timeout": True,
            },
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            "IGNORE_EXCEPTIONS": True,  # Fallback gracefully if Redis is down
        },
        "KEY_PREFIX": "greylit_dev",
        "TIMEOUT": 300,  # Default cache timeout (5 minutes)
    }
}

# Sentry configuration for development - Use centralized Sentry initialization
from apps.core.integrations import SentryInitializer

# Initialize Sentry with development-specific settings
sentry_enabled = SentryInitializer.initialize(
    environment="local_development",
    traces_sample_rate=config("SENTRY_TRACES_SAMPLE_RATE", default=0.05, cast=float),
    profiles_sample_rate=config(
        "SENTRY_PROFILES_SAMPLE_RATE", default=0.01, cast=float
    ),
    send_default_pii=True,  # OK to send PII in development
    release=config("SENTRY_RELEASE", default="dev-local"),
    max_breadcrumbs=100,  # More breadcrumbs in development
)

if sentry_enabled:
    logger.info("Sentry configured for local development")
else:
    logger.info("Sentry not configured - set SENTRY_DSN environment variable to enable")

# Enhanced Logging Configuration for Local Development
# Override the base LOGGING configuration with enhanced local logging
LOGGING = get_logging_config(debug=True)

# Additional local logging settings
LOG_LEVEL = config("LOG_LEVEL", default="DEBUG")

# SQL query logging configuration
LOG_SQL_QUERIES = config("LOG_SQL_QUERIES", default=False, cast=bool)

# Enable SQL query logging in development
if LOG_SQL_QUERIES:
    LOGGING["loggers"]["django.db.backends"]["level"] = "DEBUG"
    LOGGING["loggers"]["django.db.backends"]["handlers"] = ["console", "db_file"]

    # Additional SQL logging configuration
    SLOW_QUERY_THRESHOLD = config(
        "SLOW_QUERY_THRESHOLD", default=0.1, cast=float
    )  # 100ms

    # Add SQL logging middleware
    # MIDDLEWARE.insert(0, 'grey_lit_project.sql_logging.SQLLoggingMiddleware')  # Temporarily disabled
    # MIDDLEWARE.insert(0, 'grey_lit_project.sql_logging.QueryCountDebugMiddleware')  # Temporarily disabled

# Add request logging middleware
# MIDDLEWARE.insert(0, 'grey_lit_project.logging_utils.setup_request_logging')  # Temporarily disabled

# Redis Configuration for Local Development
# Ensure these are set for local development
REDIS_HOST = get_env("REDIS_HOST", default="redis")
REDIS_PORT = get_env_int("REDIS_PORT", default=6379)

# For local development, allow SSE origins (development only!)
if DEBUG:
    SSE_ALLOWED_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]

# Test-specific overrides -- prevent Celery retry storms, Redis errors, and speed up tests
import sys

if "test" in sys.argv:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
    CELERY_BEAT_SCHEDULE = {}
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-cache",
        }
    }
    CACHALOT_ENABLED = False
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    POSTHOG_ENABLED = False
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
            },
        },
        "root": {"handlers": ["console"], "level": "WARNING"},
    }
