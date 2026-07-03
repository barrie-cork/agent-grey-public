"""
URL configuration for the SERP execution module.
"""

from django.urls import path

from . import api, views

app_name = "serp_execution"

urlpatterns = [
    # Main views
    path(
        "session/<uuid:session_id>/status/",
        views.SearchExecutionStatusView.as_view(),
        name="execution_status",
    ),
    path(
        "execution/<uuid:execution_id>/recover/",
        views.ErrorRecoveryView.as_view(),
        name="error_recovery",
    ),
    path(
        "session/<uuid:session_id>/reconcile/",
        views.ReconcileStateView.as_view(),
        name="reconcile_state",
    ),
    # AJAX API endpoints
    path(
        "api/execution/<uuid:execution_id>/status/",
        api.execution_status_api,
        name="execution_status_api",
    ),
    path(
        "api/session/<uuid:session_id>/progress/",
        api.session_progress_api,
        name="session_progress_api",
    ),
    path(
        "api/session/<uuid:session_id>/quick-status/",
        api.session_quick_status_api,
        name="session_quick_status_api",
    ),
    path(
        "api/session/<uuid:session_id>/query-progress/",
        api.session_query_progress_api,
        name="session_query_progress_api",
    ),
    path(
        "api/execution/<uuid:execution_id>/retry/",
        api.retry_execution_api,
        name="retry_execution_api",
    ),
    path(
        "api/session/<uuid:session_id>/cancel/",
        api.cancel_session_api,
        name="cancel_session_api",
    ),
    # Diagnostic endpoints (admin/staff only)
    path(
        "api/diagnostic/test/",
        api.diagnostic_api_test,
        name="diagnostic_api_test",
    ),
    path(
        "api/session/<uuid:session_id>/diagnostic/",
        api.session_diagnostic_api,
        name="session_diagnostic_api",
    ),
    # Test view for SessionMonitor development
    path(
        "test/session-monitor/",
        views.TestSessionMonitorView.as_view(),
        name="test_session_monitor",
    ),
    path(
        "test/session-monitor/<uuid:session_id>/",
        views.TestSessionMonitorView.as_view(),
        name="test_session_monitor_with_id",
    ),
    # Test API endpoints for E2E testing (development only)
    path(
        "api/test/create-session/",
        api.create_test_session_api,
        name="create_test_session_api",
    ),
    path(
        "api/test/update-session/",
        api.update_test_session_api,
        name="update_test_session_api",
    ),
]
