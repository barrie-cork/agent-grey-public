"""
Staging settings for grey_lit_project.

Production-like environment for testing before deployment.
Uses separate database and stricter security settings.
"""

import logging

from django.core.exceptions import ImproperlyConfigured

from apps.core.config_builders import CacheConfigBuilder
from apps.core.env_config import get_env, get_env_bool, get_env_int, get_env_list
from apps.core.integrations import SentryInitializer

from .base import *  # noqa: F403
from .base import BASE_DIR  # Explicit import for linting clarity

# Initialize logging for staging configuration
logger = logging.getLogger(__name__)

# STAGING DEFAULTS (Local testing only - override in production)
# ------------------------------------------------------------------------------
# SECURITY WARNING: These defaults are INSECURE PLACEHOLDERS for local testing.
# Production deployments MUST override with secure randomly-generated credentials.
DEFAULT_STAGING_DB_NAME = "thesis_grey_staging_db"
DEFAULT_STAGING_DB_USER = "thesis_grey_staging_user"
DEFAULT_STAGING_DB_PASSWORD = "staging_secure_password_456"  # INSECURE - override!
DEFAULT_STAGING_DB_HOST = "db_staging"
DEFAULT_STAGING_REDIS_PASSWORD = "staging_redis_456"  # INSECURE - override!
DEFAULT_STAGING_REDIS_HOST = "redis_staging"
DEFAULT_STAGING_REDIS_URL = (
    f"redis://:{DEFAULT_STAGING_REDIS_PASSWORD}@{DEFAULT_STAGING_REDIS_HOST}:6379/0"
)
DEFAULT_STAGING_ALLOWED_HOSTS = "localhost,127.0.0.1,staging.local,0.0.0.0,web_staging"
DEFAULT_STAGING_CSRF_ORIGINS = (
    "http://localhost:8200,http://127.0.0.1:8200,"
    "http://staging.local:8200,http://0.0.0.0:8200"
)

# GENERAL
# ------------------------------------------------------------------------------
DEBUG = get_env_bool("DEBUG", False)

# Credential safety guard -- prevent deployment with default insecure credentials
if not DEBUG:
    _actual_db_password = get_env("POSTGRES_PASSWORD", DEFAULT_STAGING_DB_PASSWORD)
    _actual_redis_password = get_env("REDIS_PASSWORD", DEFAULT_STAGING_REDIS_PASSWORD)
    if _actual_db_password == DEFAULT_STAGING_DB_PASSWORD:
        raise ImproperlyConfigured(
            "Staging deployment with DEBUG=False must not use the default database password. "
            "Set the POSTGRES_PASSWORD environment variable to a secure value."
        )
    if _actual_redis_password == DEFAULT_STAGING_REDIS_PASSWORD:
        raise ImproperlyConfigured(
            "Staging deployment with DEBUG=False must not use the default Redis password. "
            "Set the REDIS_PASSWORD environment variable to a secure value."
        )
    del _actual_db_password, _actual_redis_password

SECRET_KEY = get_env("SECRET_KEY")
ALLOWED_HOSTS = get_env_list("ALLOWED_HOSTS", DEFAULT_STAGING_ALLOWED_HOSTS)

# DATABASES
# ------------------------------------------------------------------------------
# Staging uses local Docker PostgreSQL for production-like testing
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": get_env("POSTGRES_DB", DEFAULT_STAGING_DB_NAME),
        "USER": get_env("POSTGRES_USER", DEFAULT_STAGING_DB_USER),
        "PASSWORD": get_env("POSTGRES_PASSWORD", DEFAULT_STAGING_DB_PASSWORD),
        "HOST": get_env("POSTGRES_HOST", DEFAULT_STAGING_DB_HOST),
        "PORT": get_env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": get_env_int("CONN_MAX_AGE", 60),
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}

# Use DATABASE_URL if provided (for flexibility)
_database_url = get_env("DATABASE_URL", None)
if _database_url:
    import dj_database_url

    DATABASES["default"] = dj_database_url.parse(
        _database_url, conn_max_age=get_env_int("CONN_MAX_AGE", 60)
    )

# CACHES - Use centralized cache configuration builder
# ------------------------------------------------------------------------------
CACHES = CacheConfigBuilder.build(environment="staging", skip_redis=False)

# SECURITY
# ------------------------------------------------------------------------------
# SECURITY: Trust X-Forwarded-Proto from reverse proxy for HTTPS detection.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# SECURITY: SSL redirect disabled by default -- reverse proxy handles HTTP->HTTPS.
SECURE_SSL_REDIRECT = get_env_bool("SECURE_SSL_REDIRECT", False)
# SECURITY: Cookie Secure flag defaults to False for local Docker staging (HTTP).
# Set to True via env var when staging runs behind HTTPS.
SESSION_COOKIE_SECURE = get_env_bool("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = get_env_bool("CSRF_COOKIE_SECURE", False)
# SECURITY: HttpOnly prevents JavaScript access to session/CSRF cookies.
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
# SECURITY: SameSite=Lax prevents CSRF via cross-origin navigation.
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# SECURITY: HSTS with 1-hour max-age for staging (shorter than production's 1 year
# to allow easier rollback during testing).
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = get_env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = get_env_bool("SECURE_HSTS_PRELOAD", True)
# SECURITY: Prevents MIME-sniffing attacks.
SECURE_CONTENT_TYPE_NOSNIFF = True
# NOTE: X-XSS-Protection is deprecated and ignored by modern browsers.
# Retained for legacy browser coverage; CSP is the real XSS mitigation.
SECURE_BROWSER_XSS_FILTER = True
# SECURITY: Prevents clickjacking by denying framing entirely.
X_FRAME_OPTIONS = "DENY"

# CSRF
# ------------------------------------------------------------------------------
CSRF_TRUSTED_ORIGINS = get_env_list(
    "CSRF_TRUSTED_ORIGINS", DEFAULT_STAGING_CSRF_ORIGINS
)

# STATIC & MEDIA
# ------------------------------------------------------------------------------
STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATIC_URL = "/static/"

MEDIA_ROOT = str(BASE_DIR / "media")
MEDIA_URL = "/media/"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# CELERY
# ------------------------------------------------------------------------------
CELERY_BROKER_URL = get_env("CELERY_BROKER_URL", DEFAULT_STAGING_REDIS_URL)
CELERY_RESULT_BACKEND = get_env("CELERY_RESULT_BACKEND", DEFAULT_STAGING_REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TIME_LIMIT = 5 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 4 * 60
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# EMAIL
# ------------------------------------------------------------------------------
# SECURITY: default to SMTP like production. The console backend writes emails
# (including invitation magic-link tokens) straight to stdout, bypassing
# SensitiveDataFilter log redaction entirely -- console must be an explicit
# opt-in via EMAIL_BACKEND, never a staging default.
EMAIL_BACKEND = get_env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = get_env("EMAIL_HOST", default="")
EMAIL_PORT = get_env_int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = get_env_bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = get_env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = get_env("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = 5

# ADMIN
# ------------------------------------------------------------------------------
ADMIN_URL = get_env("ADMIN_URL", "admin/")

# LOGGING
# ------------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "sensitive_data_filter": {
            "()": "grey_lit_project.logging_filters.SensitiveDataFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false", "sensitive_data_filter"],
            "class": "django.utils.log.AdminEmailHandler",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["sensitive_data_filter"],
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/app/logs/staging.log",
            "maxBytes": 1024 * 1024 * 15,  # 15MB
            "backupCount": 10,
            "formatter": "verbose",
            "filters": ["sensitive_data_filter"],
        },
    },
    "root": {"level": "INFO", "handlers": ["console", "file"]},
    "loggers": {
        "django.request": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
        "django.security.DisallowedHost": {
            "level": "ERROR",
            "handlers": ["console", "mail_admins"],
            "propagate": True,
        },
        "django.db.backends": {
            "level": "WARNING",
            "handlers": ["console"],
            "propagate": False,
        },
        "apps": {
            "level": "INFO",
            "handlers": ["console", "file"],
            "propagate": False,
        },
    },
}

# Sentry - Use centralized Sentry initialization
# ------------------------------------------------------------------------------
SentryInitializer.initialize(
    environment="staging",
    traces_sample_rate=float(get_env("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
    profiles_sample_rate=float(get_env("SENTRY_PROFILES_SAMPLE_RATE", "0.05")),
)

# Your stuff...
# ------------------------------------------------------------------------------
# Environment-specific settings
ENVIRONMENT = "staging"
DEPLOYMENT_TYPE = get_env("DEPLOYMENT_TYPE", "docker")

# Staging-specific rate limits
SERPER_RATE_LIMIT = 30  # requests per minute
SERPER_BURST_LIMIT = 5  # burst allowance

# Feature flags for staging
ENABLE_SSE = get_env_bool("ENABLE_SSE", True)
ENABLE_CACHING = get_env_bool("ENABLE_CACHING", True)

# Performance settings
CONN_MAX_AGE = 60
DATABASE_POOL_SIZE = 10

logger.info(
    f"Staging settings loaded: DATABASE={DATABASES['default'].get('NAME', 'Unknown')}"
)
