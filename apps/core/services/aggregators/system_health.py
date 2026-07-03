"""
System health aggregation service.

Replaces large inline methods in monitoring views with a focused,
cacheable service for collecting system health and performance metrics.
"""

import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import psutil
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from apps.core.services.base import BaseService
from apps.core.types.monitoring_types import (
    ResourceUsageData,
    ServiceStatusData,
    SystemHealthData,
)


class SystemHealthConfig(Dict[str, Any]):
    """Configuration for system health aggregation."""

    cache_timeout: int
    cpu_threshold: float
    memory_threshold: float
    disk_threshold: float


class SystemHealthAggregator(BaseService[SystemHealthConfig]):
    """
    Aggregates system health and performance metrics for monitoring dashboards.

    Replaces large inline methods from monitoring views with a focused,
    testable, and cacheable service for tracking system resources.
    """

    SERVICE_NAME = "SystemHealthAggregator"
    SERVICE_VERSION = "1.0.0"

    def _initialize(self) -> None:
        """Initialize the system health aggregator."""
        self.cache_timeout = self.config.get("cache_timeout", 60)  # 1 minute default
        self.cpu_threshold = self.config.get("cpu_threshold", 80.0)  # 80% CPU
        self.memory_threshold = self.config.get("memory_threshold", 80.0)  # 80% Memory
        self.disk_threshold = self.config.get("disk_threshold", 85.0)  # 85% Disk

    def health_check(self) -> bool:
        """Check if the service can collect system metrics."""
        try:
            # Test basic system metrics collection
            psutil.cpu_percent()
            psutil.virtual_memory()
            psutil.disk_usage("/")

            # Test database connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

            return True
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False

    def get_default_config(self) -> SystemHealthConfig:
        """Get default configuration."""
        return SystemHealthConfig(
            cache_timeout=60,
            cpu_threshold=80.0,
            memory_threshold=80.0,
            disk_threshold=85.0,
        )

    def get_health_data(self, include_detailed: bool = False) -> SystemHealthData:
        """
        Get aggregated system health data.

        Args:
            include_detailed: Whether to include detailed resource breakdowns

        Returns:
            SystemHealthData with system metrics
        """
        cache_key = f"system_health_{'detailed' if include_detailed else 'basic'}"

        # Check cache first
        cached_data = self.get_cached_value(cache_key)
        if cached_data:
            return cached_data

        # Generate fresh health data
        with self._measure_performance("get_system_health"):
            try:
                health_data = self._collect_system_health(include_detailed)

                # Cache the results
                self.set_cached_value(cache_key, health_data)

                return health_data

            except Exception as e:
                self._handle_error(
                    e, {"include_detailed": include_detailed}, "get_system_health"
                )
                # Return basic health data on error
                return self._get_emergency_health_data()

    def _collect_system_health(self, include_detailed: bool) -> SystemHealthData:
        """Collect system health metrics."""
        # Get resource usage
        resource_usage = self._get_resource_usage()

        # Get service statuses
        service_statuses = self._get_service_statuses()

        # Calculate overall health score
        health_score = self._calculate_health_score(resource_usage, service_statuses)

        # Get system information
        system_info = self._get_system_info() if include_detailed else {}

        # Check for alerts
        alerts = self._check_system_alerts(resource_usage, service_statuses)

        return SystemHealthData(
            overall_health_score=health_score,
            resource_usage=resource_usage,
            service_statuses=service_statuses,
            system_info=system_info,
            alerts=alerts,
            last_updated=timezone.now(),
        )

    def _get_resource_usage(self) -> ResourceUsageData:
        """Get current resource usage metrics."""
        try:
            # CPU usage (1 second sample)
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count() or 0

            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_gb = memory.used / (1024**3)
            memory_total_gb = memory.total / (1024**3)

            # Disk usage
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100
            disk_used_gb = disk.used / (1024**3)
            disk_total_gb = disk.total / (1024**3)

            # Load average (Unix systems)
            try:
                load_avg = psutil.getloadavg()
                load_1min = load_avg[0]
                load_5min = load_avg[1]
                load_15min = load_avg[2]
            except (AttributeError, OSError):
                # Not available on Windows
                load_1min = load_5min = load_15min = 0.0

            return ResourceUsageData(
                cpu_percent=cpu_percent,
                cpu_count=cpu_count,
                memory_percent=memory_percent,
                memory_used_gb=round(memory_used_gb, 2),
                memory_total_gb=round(memory_total_gb, 2),
                disk_percent=round(disk_percent, 1),
                disk_used_gb=round(disk_used_gb, 2),
                disk_total_gb=round(disk_total_gb, 2),
                load_1min=round(load_1min, 2),
                load_5min=round(load_5min, 2),
                load_15min=round(load_15min, 2),
            )
        except Exception as e:
            self.logger.error(f"Failed to collect resource usage: {e}")
            # Return minimal data on error
            return ResourceUsageData(
                cpu_percent=0.0,
                cpu_count=1,
                memory_percent=0.0,
                memory_used_gb=0.0,
                memory_total_gb=0.0,
                disk_percent=0.0,
                disk_used_gb=0.0,
                disk_total_gb=0.0,
                load_1min=0.0,
                load_5min=0.0,
                load_15min=0.0,
            )

    def _get_service_statuses(self) -> List[ServiceStatusData]:
        """Get the status of key system services."""
        statuses = []

        # Database connection
        db_status = self._check_database_health()
        statuses.append(
            ServiceStatusData(
                name="Database",
                status="healthy" if db_status["healthy"] else "unhealthy",
                response_time_ms=db_status["response_time_ms"],
                details=db_status.get("details", {}),
            )
        )

        # Cache service
        cache_status = self._check_cache_health()
        statuses.append(
            ServiceStatusData(
                name="Cache",
                status="healthy" if cache_status["healthy"] else "unhealthy",
                response_time_ms=cache_status["response_time_ms"],
                details=cache_status.get("details", {}),
            )
        )

        # Celery status (if available)
        celery_status = self._check_celery_health()
        if celery_status:
            statuses.append(
                ServiceStatusData(
                    name="Celery",
                    status="healthy" if celery_status["healthy"] else "unhealthy",
                    response_time_ms=celery_status.get("response_time_ms", 0),
                    details=celery_status.get("details", {}),
                )
            )

        return statuses

    def _check_database_health(self) -> Dict[str, Any]:
        """Check database connection health."""
        try:
            start_time = timezone.now()

            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM django_migrations")
                result = cursor.fetchone()

            end_time = timezone.now()
            response_time_ms = (end_time - start_time).total_seconds() * 1000

            return {
                "healthy": True,
                "response_time_ms": round(response_time_ms, 2),
                "details": {
                    "migrations_count": result[0] if result else 0,
                    "connection_name": connection.settings_dict.get("NAME", "unknown"),
                },
            }
        except Exception as e:
            return {
                "healthy": False,
                "response_time_ms": 0,
                "details": {"error": str(e)},
            }

    def _check_cache_health(self) -> Dict[str, Any]:
        """Check cache service health."""
        try:
            start_time = timezone.now()

            # Test cache set and get
            test_key = f"health_check_{timezone.now().timestamp()}"
            test_value = "ok"

            cache.set(test_key, test_value, timeout=10)
            retrieved_value = cache.get(test_key)
            cache.delete(test_key)

            end_time = timezone.now()
            response_time_ms = (end_time - start_time).total_seconds() * 1000

            healthy = retrieved_value == test_value

            return {
                "healthy": healthy,
                "response_time_ms": round(response_time_ms, 2),
                "details": {
                    "cache_backend": settings.CACHES["default"]["BACKEND"],
                    "test_successful": healthy,
                },
            }
        except Exception as e:
            return {
                "healthy": False,
                "response_time_ms": 0,
                "details": {"error": str(e)},
            }

    def _check_celery_health(self) -> Optional[Dict[str, Any]]:
        """Check Celery worker health (if available)."""
        try:
            from celery import current_app

            start_time = timezone.now()

            # Check if workers are available
            inspect = current_app.control.inspect()
            active_workers = inspect.active()

            end_time = timezone.now()
            response_time_ms = (end_time - start_time).total_seconds() * 1000

            if active_workers:
                worker_count = len(active_workers)
                healthy = worker_count > 0
            else:
                worker_count = 0
                healthy = False

            return {
                "healthy": healthy,
                "response_time_ms": round(response_time_ms, 2),
                "details": {
                    "worker_count": worker_count,
                    "active_workers": (
                        list(active_workers.keys()) if active_workers else []
                    ),
                },
            }
        except ImportError:
            # Celery not available
            return None
        except Exception as e:
            return {
                "healthy": False,
                "response_time_ms": 0,
                "details": {"error": str(e)},
            }

    def _calculate_health_score(
        self,
        resource_usage: ResourceUsageData,
        service_statuses: List[ServiceStatusData],
    ) -> float:
        """Calculate an overall health score (0-100)."""
        scores = []

        # Resource usage scores (higher usage = lower score)
        cpu_score = max(0, 100 - resource_usage.cpu_percent)
        memory_score = max(0, 100 - resource_usage.memory_percent)
        disk_score = max(0, 100 - resource_usage.disk_percent)

        scores.extend([cpu_score, memory_score, disk_score])

        # Service health scores
        for service in service_statuses:
            service_score = 100 if service.status == "healthy" else 0
            scores.append(service_score)

        # Calculate weighted average
        if scores:
            return round(sum(scores) / len(scores), 1)
        else:
            return 0.0

    def _get_system_info(self) -> Dict[str, Any]:
        """Get detailed system information."""
        try:
            return {
                "python_version": sys.version,
                "platform": sys.platform,
                "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat(),
                "process_count": len(psutil.pids()),
                "network_interfaces": len(psutil.net_if_addrs()),
                "django_version": getattr(settings, "DJANGO_VERSION", "unknown"),
            }
        except Exception as e:
            self.logger.error(f"Failed to collect system info: {e}")
            return {"error": str(e)}

    def _check_system_alerts(
        self,
        resource_usage: ResourceUsageData,
        service_statuses: List[ServiceStatusData],
    ) -> List[Dict[str, Any]]:
        """Check for system alerts based on thresholds."""
        alerts = []

        # CPU threshold alert
        if resource_usage.cpu_percent > self.cpu_threshold:
            alerts.append(
                {
                    "type": "cpu_high",
                    "severity": "warning",
                    "message": f"CPU usage is {resource_usage.cpu_percent}% (threshold: {self.cpu_threshold}%)",
                    "value": resource_usage.cpu_percent,
                    "threshold": self.cpu_threshold,
                }
            )

        # Memory threshold alert
        if resource_usage.memory_percent > self.memory_threshold:
            alerts.append(
                {
                    "type": "memory_high",
                    "severity": "warning",
                    "message": (
                        f"Memory usage is {resource_usage.memory_percent}% "
                        f"(threshold: {self.memory_threshold}%)"
                    ),
                    "value": resource_usage.memory_percent,
                    "threshold": self.memory_threshold,
                }
            )

        # Disk threshold alert
        if resource_usage.disk_percent > self.disk_threshold:
            alerts.append(
                {
                    "type": "disk_high",
                    "severity": (
                        "critical" if resource_usage.disk_percent > 95 else "warning"
                    ),
                    "message": f"Disk usage is {resource_usage.disk_percent}% (threshold: {self.disk_threshold}%)",
                    "value": resource_usage.disk_percent,
                    "threshold": self.disk_threshold,
                }
            )

        # Service health alerts
        for service in service_statuses:
            if service.status != "healthy":
                alerts.append(
                    {
                        "type": "service_unhealthy",
                        "severity": "critical",
                        "message": f"{service.name} service is {service.status}",
                        "service": service.name,
                        "status": service.status,
                    }
                )

        return alerts

    def _get_emergency_health_data(self) -> SystemHealthData:
        """Return minimal health data when collection fails."""
        return SystemHealthData(
            overall_health_score=0.0,
            resource_usage=ResourceUsageData(
                cpu_percent=0.0,
                cpu_count=1,
                memory_percent=0.0,
                memory_used_gb=0.0,
                memory_total_gb=0.0,
                disk_percent=0.0,
                disk_used_gb=0.0,
                disk_total_gb=0.0,
                load_1min=0.0,
                load_5min=0.0,
                load_15min=0.0,
            ),
            service_statuses=[],
            system_info={"status": "error"},
            alerts=[
                {
                    "type": "system_error",
                    "severity": "critical",
                    "message": "Failed to collect system health data",
                }
            ],
            last_updated=timezone.now(),
        )

    def get_quick_status(self) -> Dict[str, Any]:
        """
        Get a quick system status summary for dashboards.

        Returns:
            Dictionary with quick status information
        """
        cache_key = "system_quick_status"

        # Check cache first (30 second timeout for quick status)
        cached_status = self.get_cached_value(cache_key)
        if cached_status:
            return cached_status

        with self._measure_performance("get_quick_status"):
            try:
                # Get basic metrics without detailed info
                health_data = self._collect_system_health(include_detailed=False)

                # Create quick status summary
                quick_status = {
                    "overall_status": self._determine_overall_status(
                        health_data.overall_health_score
                    ),
                    "health_score": health_data.overall_health_score,
                    "cpu_percent": health_data.resource_usage.cpu_percent,
                    "memory_percent": health_data.resource_usage.memory_percent,
                    "disk_percent": health_data.resource_usage.disk_percent,
                    "alert_count": len(health_data.alerts),
                    "critical_alerts": len(
                        [
                            a
                            for a in health_data.alerts
                            if a.get("severity") == "critical"
                        ]
                    ),
                    "timestamp": timezone.now().isoformat(),
                }

                # Cache for 30 seconds
                self.set_cached_value(cache_key, quick_status, timeout=30)

                return quick_status

            except Exception as e:
                self._handle_error(e, {}, "get_quick_status")
                return {
                    "overall_status": "error",
                    "health_score": 0.0,
                    "cpu_percent": 0.0,
                    "memory_percent": 0.0,
                    "disk_percent": 0.0,
                    "alert_count": 1,
                    "critical_alerts": 1,
                    "timestamp": timezone.now().isoformat(),
                }

    def _determine_overall_status(self, health_score: float) -> str:
        """Determine overall status based on health score."""
        if health_score >= 90:
            return "excellent"
        elif health_score >= 75:
            return "good"
        elif health_score >= 50:
            return "degraded"
        else:
            return "poor"
