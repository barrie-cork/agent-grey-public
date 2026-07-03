import logging
import mimetypes
import ssl

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from apps.core.env_config import get_env, get_env_bool, get_env_float, get_env_int

from .base import *
from .base import BASE_DIR, DATABASES, INSTALLED_APPS, MIDDLEWARE

# Import Redis classes for proper SSL connection configuration
try:
    import redis
    import redis.connection
except ImportError:
    redis = None

# Initialize logging for production configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = get_env_bool("DEBUG", default=False)

# SECRET_KEY guard -- production must have an explicitly set, strong key
_production_secret_key = get_env("SECRET_KEY")
if not _production_secret_key or len(_production_secret_key) < 32:
    raise ImproperlyConfigured(
        "Production requires SECRET_KEY environment variable with at least 32 characters. "
        "Generate one with: python -c "
        "'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'"
    )
SECRET_KEY = _production_secret_key
del _production_secret_key

# Host Configuration - Use centralized host configuration utility
from apps.core.host_config import HostConfiguration

host_config = HostConfiguration.get_production_config()
ALLOWED_HOSTS = host_config["ALLOWED_HOSTS"]
ALLOWED_CIDR_NETS = host_config["ALLOWED_CIDR_NETS"]
CSRF_TRUSTED_ORIGINS = host_config["CSRF_TRUSTED_ORIGINS"]

# =============================================================================
# PRODUCTION SECURITY HARDENING
# =============================================================================

# SECURITY: Trust the X-Forwarded-Proto header from the reverse proxy so Django
# knows the original request was HTTPS. Required when SSL terminates at the
# load balancer (DigitalOcean App Platform / Cloudflare).
SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

# SECURITY: SSL redirect is handled at the load balancer level. Enabling it in
# Django causes infinite redirect loops behind a reverse proxy that terminates SSL.
SECURE_SSL_REDIRECT = get_env_bool("SECURE_SSL_REDIRECT", default=False)

# SECURITY: Secure cookies -- ensures session and CSRF cookies are only sent
# over HTTPS, preventing interception over plaintext HTTP.
SESSION_COOKIE_SECURE = get_env_bool("SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = get_env_bool("CSRF_COOKIE_SECURE", default=True)

# NOTE: SECURE_BROWSER_XSS_FILTER sets the X-XSS-Protection header, which is
# deprecated and ignored by modern browsers. Retained for legacy browser coverage
# but CSP (configured below) is the real XSS mitigation.
SECURE_BROWSER_XSS_FILTER = True

# SECURITY: Prevents MIME-sniffing attacks.
SECURE_CONTENT_TYPE_NOSNIFF = True

# SECURITY: Prevents clickjacking by denying framing entirely.
X_FRAME_OPTIONS = get_env("X_FRAME_OPTIONS", default="DENY")

# SECURITY: HSTS tells browsers to only connect via HTTPS for the specified
# duration. 1 year + includeSubDomains + preload is the recommended production
# configuration. WARNING: enabling preload submits the domain to browser preload
# lists -- this is difficult to undo.
SECURE_HSTS_SECONDS = get_env_int("SECURE_HSTS_SECONDS", default=31536000)  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = get_env_bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True
)
SECURE_HSTS_PRELOAD = get_env_bool("SECURE_HSTS_PRELOAD", default=True)

# SECURITY: Session cookie hardening.
# HttpOnly=True prevents JavaScript access (mitigates XSS session theft).
# SameSite=Lax prevents CSRF via cross-origin navigation.
SESSION_COOKIE_HTTPONLY = get_env_bool("SESSION_COOKIE_HTTPONLY", default=True)
SESSION_COOKIE_SAMESITE = get_env("SESSION_COOKIE_SAMESITE", default="Lax")

# SECURITY: CSRF cookie hardening.
# HttpOnly=True is safe here because Django's CSRF middleware reads the cookie
# server-side; the Vue SPA gets its CSRF token from the DOM ({% csrf_token %}).
CSRF_COOKIE_HTTPONLY = get_env_bool("CSRF_COOKIE_HTTPONLY", default=True)
CSRF_COOKIE_SAMESITE = get_env("CSRF_COOKIE_SAMESITE", default="Lax")

# SECURITY: Expire sessions when the browser closes (defence in depth on shared
# machines). SESSION_COOKIE_AGE caps the absolute lifetime.
SESSION_EXPIRE_AT_BROWSER_CLOSE = get_env_bool(
    "SESSION_EXPIRE_AT_BROWSER_CLOSE", default=True
)
SESSION_COOKIE_AGE = get_env_int("SESSION_COOKIE_AGE", default=86400)  # 24 hours

# Production apps
INSTALLED_APPS += [
    "gunicorn",
    "django_celery_results",  # For database-backed Celery results
]

# Health Check Configuration - For DigitalOcean Kubernetes health probes
HEALTH_CHECK_PATHS = ["/health/", "/healthz", "/health"]
HEALTH_CHECK_POD_NETWORK_PREFIX = "10.244."
HEALTH_CHECK_APP_DOMAIN = get_env(
    "HEALTH_CHECK_APP_DOMAIN", default="grey-lit-app-ifa37.ondigitalocean.app"
)

# Copy so the inserts below don't mutate the shared base MIDDLEWARE list.
# `from .base import *` binds the same list object; importing this module (e.g.
# from a test) would otherwise poison MIDDLEWARE for settings.test, which pulls
# in csp.middleware (django-csp not installed outside production).
MIDDLEWARE = list(MIDDLEWARE)

# Add health check bypass middleware BEFORE CommonMiddleware
# This allows Kubernetes health probes from pod IPs to bypass ALLOWED_HOSTS validation
MIDDLEWARE.insert(
    0, "apps.core.middleware.health_check_bypass.HealthCheckBypassMiddleware"
)

# Add CSP middleware after SecurityMiddleware
# Note: django-csp doesn't need to be in INSTALLED_APPS
MIDDLEWARE.insert(2, "csp.middleware.CSPMiddleware")

# Content Security Policy Configuration - Use centralized CSP builder
from apps.core.security_config import CSPConfigBuilder

globals().update(CSPConfigBuilder.build())

# Database configuration using DATABASE_URL
# Persistent connections (conn_max_age=600) avoid 15-25ms reconnect overhead per request

# Validate DATABASE_URL is set before attempting database configuration
# This prevents cryptic dj_database_url errors when the variable is missing
# CRITICAL: Must check for both None and empty string ("")
# See: docs/fixes/DIGITALOCEAN-HEALTH-CHECK-FIX-RCA.md (2025-10-17 addendum)
database_url = get_env("DATABASE_URL")
if not database_url or not database_url.strip():
    error_msg = (
        "DATABASE_URL environment variable is required for production deployment. "
        "Configure it in DigitalOcean App Platform console (Settings → Environment Variables). "
        "Expected format: postgresql://user:pass@host:port/db?sslmode=require"
    )
    logger.error(error_msg)
    raise ImproperlyConfigured(error_msg)

DATABASES = {
    "default": dj_database_url.config(
        default=database_url,
        conn_max_age=600,  # Reuse connections for 10 minutes
        conn_health_checks=True,  # Check connection health on each request
    )
}

# Add PostgreSQL-specific options separately (only for PostgreSQL, not SQLite)
# These help manage connection lifecycle and prevent connection exhaustion
# Optimised for DigitalOcean Managed PostgreSQL 1GB/1vCPU plan
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    # Use environment variables for timeout configuration with sensible defaults
    # 1GB plan has 22 max connections (without pgBouncer) or 97 (with pgBouncer)
    DATABASES["default"]["OPTIONS"] = {
        "connect_timeout": int(
            get_env("DB_CONNECT_TIMEOUT", default=5)
        ),  # Connection timeout in seconds
        # Increased statement timeout for 1GB plan (reduced CPU)
        "options": f"-c statement_timeout={get_env('DB_STATEMENT_TIMEOUT', default=30000)} "
        f"-c idle_in_transaction_session_timeout={get_env('DB_IDLE_TIMEOUT', default=20000)}",
        "keepalives": 1,
        # Increased keepalive intervals to reduce overhead on 1GB plan
        "keepalives_idle": int(
            get_env("DB_KEEPALIVE_IDLE", default=30)
        ),  # Seconds before sending keepalive
        "keepalives_interval": int(
            get_env("DB_KEEPALIVE_INTERVAL", default=10)
        ),  # Seconds between keepalives
        "keepalives_count": int(
            get_env("DB_KEEPALIVE_COUNT", default=3)
        ),  # Number of keepalive attempts
    }

# Cache Configuration - Use centralized cache configuration builder
from apps.core.config_builders import CacheConfigBuilder

skip_redis = get_env_bool("SKIP_REDIS_CONFIG", False)
CACHES = CacheConfigBuilder.build(environment="production", skip_redis=skip_redis)

# Log the cache backend being used
try:
    cache_backend = CACHES["default"]["BACKEND"]
    logger.info(f"Cache backend: {cache_backend}")
except Exception as e:
    logger.error(f"Error determining cache backend: {e}")

# Session engine inherited from base.py (cached_db) - ASGI-compatible.
# Do NOT override to "db" here; it causes SynchronousOnlyOperation under Uvicorn workers.

# Email configuration
EMAIL_BACKEND = get_env(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = get_env("EMAIL_HOST", default="")
EMAIL_PORT = get_env_int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = get_env_bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = get_env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = get_env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = get_env("DEFAULT_FROM_EMAIL", default="noreply@agentgrey.app")

# Admin configuration for notifications
ADMINS = [
    ("Admin", get_env("ADMIN_EMAIL", default="admin@agentgrey.app")),
]

# Static files configuration - Use DigitalOcean Spaces if available, fallback to WhiteNoise
try:
    from apps.core.spaces_config import check_spaces_connection, get_spaces_config

    spaces_config = get_spaces_config()
    if spaces_config:
        # Check if Spaces is accessible
        is_connected, message = check_spaces_connection()
        if is_connected:
            # Use DigitalOcean Spaces for static and media files
            for key, value in spaces_config.items():
                if key in ["STATICFILES_STORAGE", "DEFAULT_FILE_STORAGE"]:
                    # These need special handling
                    continue
                globals()[key] = value

            # Set storage backends
            STATICFILES_STORAGE = "apps.core.spaces_config.StaticStorage"
            DEFAULT_FILE_STORAGE = "apps.core.spaces_config.MediaStorage"

            # Update URLs
            STATIC_URL = f"https://{spaces_config['AWS_S3_CUSTOM_DOMAIN']}/static/"
            MEDIA_URL = f"https://{spaces_config['AWS_S3_CUSTOM_DOMAIN']}/media/"

            logger.info(f"DigitalOcean Spaces configured: {message}")
        else:
            # Fallback to WhiteNoise if Spaces is not accessible
            raise Exception(f"Spaces not accessible: {message}")
    else:
        # No Spaces configuration, use WhiteNoise
        raise Exception("Spaces not configured")

except (ImportError, Exception) as e:
    # Fallback to WhiteNoise for static files
    logger.info(f"Using WhiteNoise for static files (Spaces not available: {e})")

    STATIC_URL = "/static/"
    STATIC_ROOT = BASE_DIR / "staticfiles"

    # Add the main static directory to STATICFILES_DIRS if it's not already there
    STATICFILES_DIRS = [
        BASE_DIR / "static",
    ]

    # Static files with WhiteNoise
    # Using CompressedManifestStaticFilesStorage for production optimization
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

    # WhiteNoise configuration
    WHITENOISE_MAX_AGE = (
        3600  # 1 hour; manifest hashing not working so unhashed files need shorter TTL
    )
    WHITENOISE_AUTOREFRESH = False  # Disabled for production optimization
    WHITENOISE_ALLOW_ALL_ORIGINS = True  # Allow serving from any host
    WHITENOISE_SKIP_COMPRESS_EXTENSIONS = [
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
        "zip",
        "gz",
        "tgz",
        "bz2",
        "tbz",
        "xz",
        "br",
    ]
    WHITENOISE_USE_FINDERS = (
        False  # Disabled for production - only serve from STATIC_ROOT
    )
    WHITENOISE_MANIFEST_STRICT = False  # Don't fail on missing files

    # Immutable Cache-Control for font files (long-lived, hashed by manifest)
    from grey_lit_project.whitenoise_headers import add_headers as _wn_add_headers

    WHITENOISE_ADD_HEADERS_FUNCTION = _wn_add_headers

    # Media files configuration (local storage)
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"

# Add static file mimetypes to ensure proper content-type headers
mimetypes.add_type("text/css", ".css", True)
mimetypes.add_type("text/javascript", ".js", True)

# SECURITY: CORS origins are explicitly listed from the environment variable.
# Never use CORS_ALLOW_ALL_ORIGINS=True in production -- combined with
# CORS_ALLOW_CREDENTIALS=True (set in base.py), it would expose session cookies
# to any origin. An empty default means no cross-origin requests are allowed
# unless explicitly configured.
CORS_ALLOWED_ORIGINS = get_env(
    "CORS_ALLOWED_ORIGINS",
    default="",
    cast=lambda v: [s.strip() for s in v.split(",") if s.strip()] if v else [],
)

# Production logging configuration - console only for DigitalOcean
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name} {message}",
            "style": "{",
        },
    },
    "filters": {
        "sensitive_data_filter": {
            "()": "grey_lit_project.logging_filters.SensitiveDataFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["sensitive_data_filter"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": get_env("DJANGO_LOG_LEVEL", default="WARNING"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": get_env("DJANGO_LOG_LEVEL", default="WARNING"),
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": get_env("DJANGO_LOG_LEVEL", default="WARNING"),
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "ERROR",  # Only show serious DB errors
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Celery Configuration
# First check if explicitly set in environment (for DigitalOcean)
CELERY_BROKER_URL = get_env("CELERY_BROKER_URL", default="")
CELERY_RESULT_BACKEND = get_env("CELERY_RESULT_BACKEND", default="")

# If not explicitly set, use Redis URL directly without connection testing
# Connection testing during settings import can fail and cause startup issues
if not CELERY_BROKER_URL:
    redis_url = get_env("REDIS_URL", default="")
    if redis_url:
        CELERY_BROKER_URL = redis_url
        CELERY_RESULT_BACKEND = redis_url
    else:
        # Fallback to database broker if no Redis URL
        CELERY_BROKER_URL = "django://"
        CELERY_RESULT_BACKEND = "django-db"

# Ensure we have defaults if still empty
if not CELERY_BROKER_URL:
    CELERY_BROKER_URL = "django://"
if not CELERY_RESULT_BACKEND:
    CELERY_RESULT_BACKEND = "django-db"

# SECURITY NOTE: ssl_cert_reqs=CERT_NONE disables TLS certificate verification
# for the Redis connection. This is required by DigitalOcean Managed Redis which
# uses self-signed certificates. The connection is still encrypted (TLS), but
# the server's identity is not verified. This is acceptable within a private
# VPC network but would be a risk on the public internet. If migrating to a Redis
# provider with proper CA-signed certificates, change to ssl.CERT_REQUIRED.
if CELERY_BROKER_URL.startswith("rediss://"):
    CELERY_BROKER_USE_SSL = {
        "ssl_cert_reqs": ssl.CERT_NONE,
        "ssl_ca_certs": None,
        "ssl_certfile": None,
        "ssl_keyfile": None,
    }
    CELERY_REDIS_BACKEND_USE_SSL = {
        "ssl_cert_reqs": ssl.CERT_NONE,
        "ssl_ca_certs": None,
        "ssl_certfile": None,
        "ssl_keyfile": None,
    }
    # Additional Celery settings for Redis SSL
    CELERY_REDIS_MAX_CONNECTIONS = 10
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    CELERY_BROKER_CONNECTION_RETRY = True
    CELERY_BROKER_CONNECTION_MAX_RETRIES = 10

# Sentry Configuration - Use centralized Sentry initialization
from apps.core.integrations import SentryInitializer

SentryInitializer.initialize(
    environment="production",
    traces_sample_rate=get_env_float("SENTRY_TRACES_SAMPLE_RATE", default=0.02),
    profiles_sample_rate=get_env_float("SENTRY_PROFILES_SAMPLE_RATE", default=0.0),
    release=get_env("SENTRY_RELEASE", default="1.0.0"),
)

# Environment identification -- required for system checks in apps/core/checks.py
ENVIRONMENT = "production"
DEPLOYMENT_TYPE = get_env("DEPLOYMENT_TYPE", default="digitalocean")
