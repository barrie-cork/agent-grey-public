"""
Review manager views package.

This package contains view modules for the review_manager app,
organized by functionality.
"""

# Import all views from the main views module for backward compatibility
from apps.review_manager.views_main import (
    DashboardView,
    SessionArchiveView,
    SessionCreateView,
    SessionDeleteView,
    SessionDetailView,
    SessionNavigateView,
    SessionUpdateView,
)

# SSE views are imported separately when needed
from .sse import session_status_stream

__all__ = [
    "DashboardView",
    "SessionArchiveView",
    "SessionCreateView",
    "SessionDeleteView",
    "SessionDetailView",
    "SessionNavigateView",
    "SessionUpdateView",
    "session_status_stream",
]
