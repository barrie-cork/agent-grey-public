"""
TypedDict definitions for health app API responses.
"""

from typing import Any, Dict, List, Literal, TypedDict

# Health status literal types
HealthStatus = Literal["healthy", "unhealthy", "degraded", "unknown"]
ServiceStatus = Literal[
    "healthy",
    "unhealthy",
    "degraded",
    "unavailable",
    "not_configured",
    "unknown",
    "no_workers",
    "error",
]
ReadyStatus = Literal["ready"]

# ============================================================================
# Main Health Check Response
# ============================================================================


class LightHealthCheckResponse(TypedDict):
    """Lightweight health check response for load balancer probes."""

    status: HealthStatus
    timestamp: str  # ISO format timestamp


class HealthChecks(TypedDict):
    """Individual health check results."""

    database: ServiceStatus
    cache: ServiceStatus
    redis: ServiceStatus
    celery: str  # Can include worker count like "healthy (2 workers)"
    spaces: ServiceStatus


class HealthCheckResponse(TypedDict):
    """Main health check endpoint response."""

    status: HealthStatus
    checks: HealthChecks
    timestamp: str  # ISO format timestamp
    message: str


# ============================================================================
# Cache Health Check Response
# ============================================================================


class CacheHealthResponse(TypedDict):
    """Cache health check endpoint response."""

    status: HealthStatus | Literal["error"]
    backend: str | None
    diagnostics: Dict[str, Any] | None
    message: str
    timestamp: str  # ISO format timestamp


class RedisDiagnostics(TypedDict):
    """Redis diagnostics information."""

    host: str
    port: int
    db: int
    connection_pool_stats: Dict[str, Any]


# ============================================================================
# Readiness Check Response
# ============================================================================


class ReadyCheckResponse(TypedDict):
    """Readiness check endpoint response."""

    status: ReadyStatus
    timestamp: str  # ISO format timestamp


# ============================================================================
# Static Debug Response
# ============================================================================


class StaticFileInfo(TypedDict):
    """Information about a static file."""

    path: str
    exists: bool


class StaticDirInfo(TypedDict):
    """Information about a static directory."""

    path: str
    exists: bool


class StaticDebugResponse(TypedDict):
    """Static files debug endpoint response."""

    STATIC_URL: str
    STATIC_ROOT: str
    STATICFILES_DIRS: List[str]
    STATICFILES_STORAGE: str
    DEBUG: bool
    WHITENOISE_AUTOREFRESH: bool | None
    WHITENOISE_USE_FINDERS: bool | None
    WHITENOISE_MANIFEST_STRICT: bool | None
    WHITENOISE_ALLOW_ALL_ORIGINS: bool | None
    middleware: List[str]
    whitenoise_enabled: bool
    static_root_exists: bool
    static_root_files: int
    static_root_dirs: List[str] | None
    static_root_error: str | None
    staticfiles_dirs_exist: List[StaticDirInfo]
    test_files: Dict[str, StaticFileInfo]


# ============================================================================
# Service-Specific Health Responses
# ============================================================================


class DatabaseHealthInfo(TypedDict):
    """Database health information."""

    status: ServiceStatus
    connection_count: int | None
    response_time_ms: float | None
    error: str | None


class CeleryHealthInfo(TypedDict):
    """Celery health information."""

    status: ServiceStatus
    worker_count: int | None
    active_tasks: int | None
    queued_tasks: int | None
    error: str | None


class RedisHealthInfo(TypedDict):
    """Redis health information."""

    status: ServiceStatus
    connected: bool
    memory_used_mb: float | None
    uptime_seconds: int | None
    error: str | None


# ============================================================================
# Composite Health Response (for monitoring dashboards)
# ============================================================================


class ServiceHealth(TypedDict):
    """Individual service health details."""

    name: str
    status: ServiceStatus
    message: str | None
    details: Dict[str, Any] | None
    last_checked: str  # ISO format timestamp


class SystemHealthResponse(TypedDict):
    """Comprehensive system health response."""

    overall_status: HealthStatus
    timestamp: str  # ISO format timestamp
    environment: str
    services: List[ServiceHealth]
    warnings: List[str]
    errors: List[str]


# ============================================================================
# Error Response
# ============================================================================


class HealthErrorResponse(TypedDict):
    """Error response for health endpoints."""

    status: Literal["error"]
    message: str
    details: Dict[str, Any] | None
