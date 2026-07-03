"""
Enhanced Logging Configuration for Agent Grey
=============================================

This module provides comprehensive logging configuration for both
development and production environments, with support for:
- Multiple log files by category
- Log rotation
- Structured logging
- Performance tracking
- Error aggregation
- Integration with Sentry
"""

from pathlib import Path

from apps.core.env_config import get_env

# Get the base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Create logs directory structure safely (avoid during collectstatic)
LOG_BASE_DIR = BASE_DIR / "logs"


def _ensure_log_dirs():
    """Safely ensure log directories exist, but only when actually needed."""
    try:
        if not LOG_BASE_DIR.exists():
            LOG_BASE_DIR.mkdir(exist_ok=True)
        # Create subdirectories as needed
        for subdir in ["django", "apps", "api", "celery", "security", "performance"]:
            subdir_path = LOG_BASE_DIR / subdir
            if not subdir_path.exists():
                subdir_path.mkdir(exist_ok=True)
    except (OSError, PermissionError):
        # Fail silently during collectstatic or other build phases
        pass


def get_logging_config(debug=False):
    """
    Generate logging configuration based on environment.

    Args:
        debug: Whether in debug mode (affects log levels and verbosity)

    Returns:
        Dictionary with logging configuration
    """

    # Ensure log directories exist (safe during all phases)
    _ensure_log_dirs()

    # Determine log levels based on environment
    if debug:
        default_level = "DEBUG"
        django_level = "INFO"
        db_level = "DEBUG"  # Show SQL queries in debug
        app_level = "DEBUG"
    else:
        default_level = "INFO"
        django_level = "WARNING"
        db_level = "WARNING"
        app_level = get_env("APP_LOG_LEVEL", default="INFO")

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            # Detailed formatter for file logs
            "verbose": {
                "format": "[{levelname:8}] {asctime} | {name:40} | {funcName:20} | {message}",
                "style": "{",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            # Simple formatter for console output
            "simple": {
                "format": "[{levelname}] {message}",
                "style": "{",
            },
            # Simple colored formatter for development console (fallback without colorlog)
            "colored": {
                "format": "[{levelname}] {message}",
                "style": "{",
            },
            # JSON formatter for structured logging
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            },
            # Performance tracking formatter
            "performance": {
                "format": "{asctime} | {name} | {message} | duration={duration:.3f}s",
                "style": "{",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "filters": {
            # Filter to only show errors and above
            "require_error_or_higher": {
                "()": "django.utils.log.RequireDebugFalse",
            },
            # Custom filter for sensitive data
            "sensitive_data_filter": {
                "()": "grey_lit_project.logging_filters.SensitiveDataFilter",
            },
        },
        "handlers": {
            # Console handler for development and production
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "simple",  # Use simple formatter always to avoid colorlog dependency
                "level": "DEBUG" if debug else "INFO",
                "filters": ["sensitive_data_filter"],
            },
            # Main application log file
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(LOG_BASE_DIR / "apps" / "application.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "formatter": "verbose",
                "level": "INFO",
                "filters": ["sensitive_data_filter"],
            },
            # Error log file
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(LOG_BASE_DIR / "apps" / "errors.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 10,
                "formatter": "verbose",
                "level": "ERROR",
                "filters": ["sensitive_data_filter"],
            },
            # Django system log
            "django_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(LOG_BASE_DIR / "django" / "django.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "formatter": "verbose",
                "level": django_level,
                "filters": ["sensitive_data_filter"],
            },
            # Database query log (only in debug)
            "db_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(LOG_BASE_DIR / "django" / "database.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 3,
                "formatter": "verbose",
                "level": "DEBUG",
                "filters": ["sensitive_data_filter"],
            },
            # API calls log
            "api_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(LOG_BASE_DIR / "api" / "api_calls.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "formatter": "json",  # Use JSON for API logs
                "level": "INFO",
                "filters": ["sensitive_data_filter"],
            },
            # Celery tasks log
            "celery_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(LOG_BASE_DIR / "celery" / "celery.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 5,
                "formatter": "verbose",
                "level": "INFO",
                "filters": ["sensitive_data_filter"],
            },
            # Security events log
            "security_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(LOG_BASE_DIR / "security" / "security.log"),
                "maxBytes": 10 * 1024 * 1024,  # 10MB
                "backupCount": 10,
                "formatter": "json",
                "level": "WARNING",
                "filters": ["sensitive_data_filter"],
            },
            # Performance metrics log
            "performance_file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "filename": str(LOG_BASE_DIR / "performance" / "performance.log"),
                "when": "midnight",
                "interval": 1,
                "backupCount": 30,
                "formatter": "json",
                "level": "INFO",
                "filters": ["sensitive_data_filter"],
            },
            # Mail admins on critical errors
            "mail_admins": {
                "class": "django.utils.log.AdminEmailHandler",
                "level": "ERROR",
                "filters": ["require_error_or_higher", "sensitive_data_filter"],
                "include_html": True,
            },
        },
        "loggers": {
            # Django system loggers
            "django": {
                "handlers": ["console", "django_file"],
                "level": django_level,
                "propagate": False,
            },
            "django.request": {
                "handlers": ["console", "django_file", "error_file"],
                "level": "WARNING",
                "propagate": False,
            },
            "django.db.backends": {
                "handlers": ["db_file"] if debug else [],
                "level": db_level,
                "propagate": False,
            },
            "django.security": {
                "handlers": ["console", "security_file"],
                "level": "WARNING",
                "propagate": False,
            },
            # Application loggers
            "apps": {
                "handlers": ["console", "file", "error_file"],
                "level": app_level,
                "propagate": False,
            },
            "apps.review_manager": {
                "handlers": ["console", "file"],
                "level": app_level,
                "propagate": False,
            },
            "apps.search_strategy": {
                "handlers": ["console", "file"],
                "level": app_level,
                "propagate": False,
            },
            "apps.serp_execution": {
                "handlers": ["console", "file", "api_file"],
                "level": app_level,
                "propagate": False,
            },
            "apps.results_manager": {
                "handlers": ["console", "file"],
                "level": app_level,
                "propagate": False,
            },
            "apps.review_results": {
                "handlers": ["console", "file"],
                "level": app_level,
                "propagate": False,
            },
            "apps.reporting": {
                "handlers": ["console", "file"],
                "level": app_level,
                "propagate": False,
            },
            # Celery loggers
            "celery": {
                "handlers": ["console", "celery_file"],
                "level": "INFO",
                "propagate": False,
            },
            "celery.task": {
                "handlers": ["console", "celery_file"],
                "level": "INFO",
                "propagate": False,
            },
            "celery.beat": {
                "handlers": ["console", "celery_file"],
                "level": "INFO",
                "propagate": False,
            },
            # API and external service loggers
            "api": {
                "handlers": ["console", "api_file"],
                "level": "INFO",
                "propagate": False,
            },
            "serper": {
                "handlers": ["console", "api_file"],
                "level": "INFO",
                "propagate": False,
            },
            # Performance logger
            "performance": {
                "handlers": ["performance_file"],
                "level": "INFO",
                "propagate": False,
            },
            # Security logger
            "security": {
                "handlers": ["console", "security_file"],
                "level": "WARNING",
                "propagate": False,
            },
            # Silence noisy loggers
            "django.utils.autoreload": {
                "level": "WARNING",
            },
            "PIL": {
                "level": "WARNING",
            },
            "urllib3": {
                "level": "WARNING",
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": default_level,
        },
    }
