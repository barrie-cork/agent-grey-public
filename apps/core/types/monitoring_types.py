"""
Comprehensive TypedDict definitions for monitoring and dashboard data.

This module provides type-safe structures for all monitoring-related data
exchanges, replacing generic Dict[str, Any] usage throughout the system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict, Union


# System Health Types
@dataclass
class ComponentStatusData:
    """Status information for individual system components."""

    name: str
    status: str  # 'healthy', 'degraded', 'unhealthy'
    last_check: str  # ISO datetime
    response_time_ms: Optional[int] = None
    details: Optional[str] = None


@dataclass
class ResourceUsageData:
    """System resource usage metrics."""

    cpu_percent: float
    cpu_count: int
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    load_1min: float
    load_5min: float
    load_15min: float


@dataclass
class ServiceStatusData:
    """Status information for system services."""

    name: str
    status: str  # 'healthy', 'unhealthy'
    response_time_ms: float
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealthData:
    """Overall system health information."""

    overall_health_score: float
    resource_usage: ResourceUsageData
    service_statuses: List[ServiceStatusData]
    system_info: Dict[str, Any]
    alerts: List[Dict[str, Any]]
    last_updated: datetime


# Workflow Statistics Types
class StatusDistributionData(TypedDict):
    """Distribution of session statuses."""

    draft: int
    defining_search: int
    ready_to_execute: int
    executing: int
    processing_results: int
    ready_for_review: int
    under_review: int
    completed: int
    archived: int


class WorkflowStatsData(TypedDict):
    """Workflow execution statistics."""

    sessions_last_hour: int
    sessions_last_24h: int
    status_distribution: StatusDistributionData
    avg_completion_time_hours: float
    error_rate_24h: float
    processing_sessions: int
    stuck_sessions: int


# Connection and Performance Metrics
class ApiCallData(TypedDict):
    """API call metrics for specific endpoints."""

    endpoint: str
    call_count: int
    avg_response_time_ms: float
    success_rate: float


class DatabaseMetricsData(TypedDict):
    """Database performance metrics."""

    connection_count: int
    max_connections: int
    query_avg_time_ms: float
    slow_queries_count: int
    last_backup: Optional[str]  # ISO datetime


class CacheMetricsData(TypedDict):
    """Cache system performance metrics."""

    hit_rate: float  # 0.0 to 1.0
    memory_usage_mb: int
    keys_count: int
    evictions_per_hour: int
    avg_response_time_ms: float


class CeleryMetricsData(TypedDict):
    """Celery task queue metrics."""

    active_tasks: int
    pending_tasks: int
    failed_tasks_24h: int
    avg_task_time_seconds: float
    workers_online: int


class ConnectionMetricsData(TypedDict):
    """Connection and API metrics data."""

    api_calls_last_hour: int
    api_calls_last_24h: int
    successful_calls: int
    failed_calls: int
    avg_response_time_ms: float
    api_call_distribution: List[ApiCallData]
    api_error_rate: float
    timeout_errors: int
    connection_healthy: bool


# Activity and Event Types
class ActivityEventData(TypedDict):
    """Individual activity event information."""

    timestamp: str  # ISO datetime
    type: str  # 'session_created', 'execution_started', 'processing_completed', etc.
    session_id: Optional[str]
    user_id: Optional[str]
    details: str
    severity: str  # 'info', 'warning', 'error'


class RecentActivitiesData(TypedDict):
    """Recent system activities and events."""

    events: List[ActivityEventData]
    total_events_24h: int
    error_events_count: int
    warning_events_count: int
    last_updated: str  # ISO datetime


# Error and Alert Types
class ErrorPatternData(TypedDict):
    """Common error pattern information."""

    error_type: str
    count: int
    first_seen: str  # ISO datetime
    last_seen: str  # ISO datetime
    affected_sessions: List[str]
    resolution_status: str  # 'open', 'investigating', 'resolved'


class AlertData(TypedDict):
    """System alert information."""

    alert_id: str
    type: str  # 'performance', 'error_rate', 'capacity', 'availability'
    severity: str  # 'low', 'medium', 'high', 'critical'
    message: str
    triggered_at: str  # ISO datetime
    acknowledged: bool
    resolved: bool


class ErrorSummaryData(TypedDict):
    """Summary of system errors and issues."""

    error_patterns: List[ErrorPatternData]
    active_alerts: List[AlertData]
    total_errors_24h: int
    critical_errors_1h: int
    resolution_rate: float  # 0.0 to 1.0


# Resource Utilisation Types
class ResourceUtilisationData(TypedDict):
    """Simplified system resource utilisation metrics for dashboard summaries."""

    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_io_mbps: float
    active_connections: int


class CapacityPlanningData(TypedDict):
    """Capacity planning and scaling metrics."""

    current_load: float  # 0.0 to 1.0
    projected_load_7d: float
    recommended_scaling: Optional[str]  # 'scale_up', 'scale_down', 'maintain'
    resource_constraints: List[str]


# Search and Processing Metrics
class SearchExecutionMetricsData(TypedDict):
    """Search execution performance metrics."""

    executions_last_hour: int
    avg_execution_time_seconds: float
    success_rate: float  # 0.0 to 1.0
    rate_limit_hits: int
    api_errors: int


class ProcessingMetricsData(TypedDict):
    """Results processing performance metrics."""

    results_processed_24h: int
    avg_processing_time_ms: float
    deduplication_rate: float  # 0.0 to 1.0
    processing_errors: int
    backlog_size: int


class ReviewMetricsData(TypedDict):
    """Review workflow metrics."""

    sessions_under_review: int
    avg_review_time_hours: float
    completion_rate: float  # 0.0 to 1.0
    pending_reviews: int


# Comprehensive Monitoring Response Types
class MonitoringDashboardData(TypedDict):
    """Complete monitoring dashboard data structure."""

    system_health: SystemHealthData
    workflow_stats: WorkflowStatsData
    connection_metrics: ConnectionMetricsData
    recent_activities: RecentActivitiesData
    error_summary: ErrorSummaryData
    resource_usage: ResourceUtilisationData
    capacity_planning: CapacityPlanningData


class DetailedMetricsData(TypedDict):
    """Detailed metrics for specific subsystems."""

    search_execution: SearchExecutionMetricsData
    processing: ProcessingMetricsData
    review: ReviewMetricsData
    timestamp: str  # ISO datetime
    collection_duration_ms: int


# API Response Types
class MonitoringAPIResponse(TypedDict):
    """Standard monitoring API response structure."""

    success: bool
    timestamp: str  # ISO datetime
    data: MonitoringDashboardData
    errors: Optional[List[str]]
    warnings: Optional[List[str]]


class MetricsAPIResponse(TypedDict):
    """Metrics-specific API response structure."""

    success: bool
    timestamp: str  # ISO datetime
    metrics: DetailedMetricsData
    metadata: dict  # Collection metadata


# Time-series Data Types
class TimeSeriesDataPoint(TypedDict):
    """Individual time series data point."""

    timestamp: str  # ISO datetime
    value: Union[int, float]
    label: Optional[str]


class TimeSeriesData(TypedDict):
    """Time series data collection."""

    name: str
    unit: str  # 'count', 'percent', 'seconds', 'mb', etc.
    data_points: List[TimeSeriesDataPoint]
    aggregation_type: str  # 'avg', 'sum', 'max', 'min'


class HistoricalMetricsData(TypedDict):
    """Historical metrics for trend analysis."""

    series: List[TimeSeriesData]
    period: str  # '1h', '24h', '7d', '30d'
    granularity: str  # '1m', '5m', '1h', '1d'
    generated_at: str  # ISO datetime


# Configuration and Threshold Types
class ThresholdConfig(TypedDict):
    """Performance threshold configuration."""

    warning_threshold: float
    critical_threshold: float
    unit: str
    check_interval_seconds: int


class MonitoringConfigData(TypedDict):
    """Monitoring system configuration."""

    enabled_checks: List[str]
    check_intervals: dict[str, int]  # check_name -> interval_seconds
    thresholds: dict[str, ThresholdConfig]  # metric_name -> threshold_config
    retention_days: int
    alert_channels: List[str]


# Export all types for easy importing
__all__ = [
    # System Health
    "ComponentStatusData",
    "SystemHealthData",
    # Workflow Statistics
    "StatusDistributionData",
    "WorkflowStatsData",
    # Connection Metrics
    "DatabaseMetricsData",
    "CacheMetricsData",
    "CeleryMetricsData",
    "ConnectionMetricsData",
    # Activities and Events
    "ActivityEventData",
    "RecentActivitiesData",
    # Errors and Alerts
    "ErrorPatternData",
    "AlertData",
    "ErrorSummaryData",
    # Resource Usage
    "ResourceUsageData",
    "ResourceUtilisationData",
    "CapacityPlanningData",
    # Search and Processing
    "SearchExecutionMetricsData",
    "ProcessingMetricsData",
    "ReviewMetricsData",
    # Response Types
    "MonitoringDashboardData",
    "DetailedMetricsData",
    "MonitoringAPIResponse",
    "MetricsAPIResponse",
    # Time Series
    "TimeSeriesDataPoint",
    "TimeSeriesData",
    "HistoricalMetricsData",
    # Configuration
    "ThresholdConfig",
    "MonitoringConfigData",
]
