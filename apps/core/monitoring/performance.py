"""
Minimal PerformanceMonitor stub for agent-grey repository
This replaces the complex monitoring system with simplified functionality
"""


class PerformanceMonitor:
    """Simplified performance monitor for basic dashboard metrics"""

    @staticmethod
    def get_dashboard_metrics():
        """Return basic dashboard metrics - simplified version"""
        return {
            "health_score": 95,  # Static good health score
            "total_operations": 0,
            "total_slow_operations": 0,
            "response_time_avg": 0.2,
            "error_rate": 0.0,
            "active_sessions": 0,
            "cache_hit_rate": 95.0,
            "cpu_usage": 15.0,
            "memory_usage": 45.0,
            "status": "healthy",
        }

    @staticmethod
    def track(operation_name: str = "unknown", metadata=None):
        """Simplified context manager for tracking operations"""
        return SimplifiedTracker(operation_name)


class SimplifiedTracker:
    """Minimal context manager that does nothing but prevents errors"""

    def __init__(self, operation_name: str):
        self.operation_name = operation_name

    def __enter__(self) -> str:
        return self.operation_name

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # No actual tracking in simplified version


# This module provides the minimal interface needed by monitoring.py
# without the complexity of the full monitoring system
