"""
Health check views for the Grey Literature Review app.

NOTE: These views are intentionally synchronous.
Async views under WSGI use async_to_sync which can fail during
interpreter shutdown (RuntimeError: cannot schedule new futures).
Since the app runs under WSGI (not ASGI), sync is simpler and more robust.
See: Sentry issue PYTHON-DJANGO-14W
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.cache import cache
from django.db import connections, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from .api_types import (
    CacheHealthResponse,
    HealthCheckResponse,
    LightHealthCheckResponse,
    ReadyCheckResponse,
    StaticDebugResponse,
)

logger = logging.getLogger(__name__)

# Track application start time for startup grace period
_APP_START_TIME = time.time()

# Startup grace period in seconds (skip Redis checks during this window)
_STARTUP_GRACE_PERIOD = 60


@csrf_exempt
@never_cache
@transaction.non_atomic_requests
def health_check(request):
    """Lightweight health check for load balancer probes. DB-only, targets <50ms."""
    try:
        db_conn = connections["default"]
        with db_conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        status = "healthy"
        status_code = 200
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        status = "unhealthy"
        status_code = 503

    response_data: LightHealthCheckResponse = {
        "status": status,
        "timestamp": timezone.now().isoformat(),
    }
    return JsonResponse(response_data, status=status_code)


@csrf_exempt
@never_cache
@transaction.non_atomic_requests
def detailed_health_check(request):
    """
    Detailed health check with parallel execution using ThreadPoolExecutor.

    Checks database, cache, Redis, Celery workers, and DigitalOcean Spaces.
    All checks run in parallel for improved performance.
    """

    def check_database():
        """Check database connection."""
        try:
            db_conn = connections["default"]
            with db_conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return "database", "healthy"
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return "database", "unhealthy"
        finally:
            connections["default"].close()

    def check_cache():
        """Check cache connection."""
        try:
            cache.set("health_check_test", "ok", 10)
            result = cache.get("health_check_test")
            return "cache", "healthy" if result == "ok" else "unhealthy"
        except Exception as e:
            logger.warning(f"Cache health check failed: {str(e)}")
            return "cache", "degraded"

    def check_redis():
        """Check Redis connection (with startup grace period)."""
        uptime = time.time() - _APP_START_TIME
        if uptime < _STARTUP_GRACE_PERIOD:
            logger.debug(
                f"Skipping Redis check during startup grace period "
                f"(uptime: {uptime:.1f}s < {_STARTUP_GRACE_PERIOD}s)"
            )
            return "redis", "starting_up"

        try:
            from apps.core.redis_config import check_redis_connection

            is_connected, message = check_redis_connection()

            if is_connected:
                return "redis", "healthy"
            else:
                logger.info(f"Redis not available: {message}")
                return "redis", "unavailable"
        except ImportError:
            return "redis", "not_configured"
        except Exception as e:
            logger.warning(f"Redis health check error: {str(e)}")
            return "redis", "error"

    def check_celery():
        """Check Celery worker status."""
        try:
            from celery import current_app

            inspect = current_app.control.inspect(timeout=1.0)
            stats = inspect.stats()

            if stats:
                worker_count = len(stats)
                return "celery", f"healthy ({worker_count} workers)"
            else:
                return "celery", "no_workers"
        except Exception as e:
            logger.warning(f"Celery health check failed: {str(e)}")
            return "celery", "unavailable"

    def check_spaces():
        """Check DigitalOcean Spaces connectivity."""
        try:
            from apps.core.spaces_config import check_spaces_connection

            is_connected, message = check_spaces_connection()

            if is_connected:
                return "spaces", "healthy"
            else:
                logger.info(f"Spaces not available: {message}")
                return "spaces", "unavailable"
        except ImportError:
            return "spaces", "not_configured"
        except Exception as e:
            logger.warning(f"Spaces health check error: {str(e)}")
            return "spaces", "error"

    # Run all checks in parallel using ThreadPoolExecutor
    checks = [check_database, check_cache, check_redis, check_celery, check_spaces]
    results = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(check): check for check in checks}
        for future in as_completed(futures, timeout=10):
            try:
                name, status = future.result()
                results[name] = status
            except Exception as e:
                check_func = futures[future]
                name = check_func.__name__.replace("check_", "")
                logger.error(f"Health check {name} exception: {e}")
                results[name] = "error"

    # Overall status - only fail if database is unhealthy
    db_status = results.get("database", "error")
    overall_status = "healthy" if db_status == "healthy" else "unhealthy"

    status_code = 200 if overall_status == "healthy" else 503

    response_data: HealthCheckResponse = {
        "status": overall_status,
        "checks": {
            "database": results.get("database", "error"),
            "cache": results.get("cache", "error"),
            "redis": results.get("redis", "error"),
            "celery": results.get("celery", "error"),
            "spaces": results.get("spaces", "error"),
        },
        "timestamp": timezone.now().isoformat(),
        "message": "Grey Literature Review App Health Check",
    }
    return JsonResponse(response_data, status=status_code)


@csrf_exempt
@never_cache
@transaction.non_atomic_requests
def cache_health_check(request):
    """
    Cache health check endpoint with detailed diagnostics.

    Returns:
        JsonResponse: Cache status and diagnostics
    """
    from apps.core.cache_utils import _get_redis_diagnostics, get_safe_cache

    try:
        cache_obj = get_safe_cache()

        if cache_obj:
            # Get cache backend info
            cache_backend = cache_obj.__class__.__name__

            # Get diagnostics for Redis backends
            diagnostics = {}
            if "Redis" in cache_backend:
                diagnostics = _get_redis_diagnostics(cache_backend)

            response_data: CacheHealthResponse = {
                "status": "healthy",
                "backend": cache_backend,
                "diagnostics": diagnostics,
                "message": "Cache is operational",
                "timestamp": timezone.now().isoformat(),
            }
            return JsonResponse(response_data)
        else:
            response_data = {
                "status": "unhealthy",
                "backend": None,
                "diagnostics": None,
                "message": "Cache validation failed or cache not available",
                "timestamp": timezone.now().isoformat(),
            }
            return JsonResponse(response_data, status=503)

    except Exception as e:
        logger.error(f"Cache health check error: {str(e)}")
        response_data = {
            "status": "error",
            "backend": None,
            "diagnostics": None,
            "message": f"Cache health check failed: {str(e)}",
            "timestamp": timezone.now().isoformat(),
        }
        return JsonResponse(response_data, status=503)


@csrf_exempt
@never_cache
@transaction.non_atomic_requests
def ready_check(request):
    """
    Readiness check for DigitalOcean.

    Returns:
        JsonResponse: Ready status
    """
    response_data: ReadyCheckResponse = {
        "status": "ready",
        "timestamp": timezone.now().isoformat(),
    }
    return JsonResponse(response_data)


@csrf_exempt
@never_cache
def static_debug(request):
    """Debug endpoint to check static file configuration."""
    import os

    from django.conf import settings

    static_info: StaticDebugResponse = {
        "STATIC_URL": settings.STATIC_URL,
        "STATIC_ROOT": str(settings.STATIC_ROOT),
        "STATICFILES_DIRS": [str(d) for d in getattr(settings, "STATICFILES_DIRS", [])],
        "STATICFILES_STORAGE": settings.STATICFILES_STORAGE,
        "DEBUG": settings.DEBUG,
        "WHITENOISE_AUTOREFRESH": getattr(settings, "WHITENOISE_AUTOREFRESH", None),
        "WHITENOISE_USE_FINDERS": getattr(settings, "WHITENOISE_USE_FINDERS", None),
        "WHITENOISE_MANIFEST_STRICT": getattr(
            settings, "WHITENOISE_MANIFEST_STRICT", None
        ),
        "WHITENOISE_ALLOW_ALL_ORIGINS": getattr(
            settings, "WHITENOISE_ALLOW_ALL_ORIGINS", None
        ),
        "middleware": list(settings.MIDDLEWARE),
        "whitenoise_enabled": "whitenoise.middleware.WhiteNoiseMiddleware"
        in settings.MIDDLEWARE,
        "static_root_exists": False,  # Will be updated below
        "static_root_files": 0,
        "static_root_dirs": None,
        "static_root_error": None,
        "staticfiles_dirs_exist": [],
        "test_files": {},
    }

    # Check if directories exist
    static_info["static_root_exists"] = os.path.exists(settings.STATIC_ROOT)
    static_info["static_root_files"] = 0
    if static_info["static_root_exists"]:
        try:
            static_info["static_root_files"] = len(
                [
                    f
                    for f in os.listdir(settings.STATIC_ROOT)
                    if os.path.isfile(os.path.join(settings.STATIC_ROOT, f))
                ]
            )
            # List first few directories in static root
            dirs = [
                d
                for d in os.listdir(settings.STATIC_ROOT)
                if os.path.isdir(os.path.join(settings.STATIC_ROOT, d))
            ]
            static_info["static_root_dirs"] = dirs[:10]
        except Exception as e:
            static_info["static_root_error"] = str(e)

    # Check STATICFILES_DIRS
    static_info["staticfiles_dirs_exist"] = []
    for static_dir in getattr(settings, "STATICFILES_DIRS", []):
        exists = os.path.exists(static_dir)
        static_info["staticfiles_dirs_exist"].append(
            {"path": str(static_dir), "exists": exists}
        )

    # Check for specific files
    test_files = [
        "css/style.css",
        "css/design-system/tokens.css",
        "admin/css/base.css",
        "js/main.js",
    ]

    static_info["test_files"] = {}
    for test_file in test_files:
        full_path = os.path.join(settings.STATIC_ROOT, test_file)
        static_info["test_files"][test_file] = {
            "path": full_path,
            "exists": os.path.exists(full_path),
        }

    return JsonResponse(static_info, json_dumps_params={"indent": 2})


@csrf_exempt
@never_cache
def static_test(request):
    """Test endpoint to verify WhiteNoise can serve a simple file."""
    import os

    from django.conf import settings
    from django.http import HttpResponse

    # Create a test file in STATIC_ROOT
    test_file_path = os.path.join(settings.STATIC_ROOT, "test.txt")
    try:
        os.makedirs(settings.STATIC_ROOT, exist_ok=True)
        with open(test_file_path, "w") as f:
            f.write("WhiteNoise static file test")

        return HttpResponse(
            f"Test file created at {test_file_path}. "
            f"Try accessing it at {settings.STATIC_URL}test.txt"
        )
    except Exception as e:
        return HttpResponse(f"Error creating test file: {str(e)}", status=500)
