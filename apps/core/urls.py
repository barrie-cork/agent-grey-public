"""
URL routing for core app features including monitoring.
"""

from django.urls import path

from .views.metadata import MetadataAPIView, MetadataHealthCheckView
from .views.monitoring import (
    ConnectionMonitoringAPI,
    HealthCheckView,
    WorkflowMonitoringAPI,
    WorkflowMonitoringDashboard,
)  # Now imports from views/monitoring/__init__.py (refactored module)
from .views.monitoring_dashboard import UnifiedMonitoringDashboard

# SSE removed - using simple polling instead

app_name = "core"

urlpatterns = [
    # Monitoring URLs
    path(
        "monitoring/workflow/",
        WorkflowMonitoringDashboard.as_view(),
        name="monitoring_dashboard",
    ),
    path(
        "monitoring/unified/",
        UnifiedMonitoringDashboard.as_view(),
        name="unified_monitoring",
    ),
    path("monitoring/api/", WorkflowMonitoringAPI.as_view(), name="monitoring_api"),
    path(
        "api/monitoring/connections/",
        ConnectionMonitoringAPI.as_view(),
        name="connection_monitoring_api",
    ),
    # Health check endpoint (Issue #85)
    path("health/", HealthCheckView.as_view(), name="health_check"),
    # Metadata URLs
    path("metadata/api/", MetadataAPIView.as_view(), name="metadata_api"),
    path("metadata/health/", MetadataHealthCheckView.as_view(), name="metadata_health"),
    # SSE removed - using simple polling instead of real-time events
]
