"""
URL configuration for the reporting app.

This module defines URL patterns for report generation, viewing,
and PRISMA compliance features.
"""

from django.urls import path

from . import views

app_name = "reporting"

urlpatterns = [
    # Main dashboard
    path(
        "sessions/<uuid:session_id>/",
        views.ReportDashboardView.as_view(),
        name="dashboard",
    ),
    # Report generation
    path(
        "sessions/<uuid:session_id>/generate/",
        views.ReportGenerationView.as_view(),
        name="generate_report",
    ),
    path(
        "sessions/<uuid:session_id>/offline-backup/",
        views.GenerateOfflineBackupView.as_view(),
        name="generate_offline_backup",
    ),
    path(
        "sessions/<uuid:session_id>/import-backup/",
        views.ImportOfflineBackupView.as_view(),
        name="import_backup",
    ),
    # Dual screening reports
    path(
        "sessions/<uuid:session_id>/irr-report/",
        views.IRRReportGenerateView.as_view(),
        name="generate_irr_report",
    ),
    path(
        "sessions/<uuid:session_id>/audit-trail/",
        views.AuditTrailExportView.as_view(),
        name="export_audit_trail",
    ),
    # Report management
    path("reports/", views.ReportListView.as_view(), name="report_list"),
    path(
        "reports/<uuid:report_id>/",
        views.ReportDetailView.as_view(),
        name="report_detail",
    ),
    path(
        "reports/<uuid:report_id>/download/",
        views.DownloadReportView.as_view(),
        name="download_report",
    ),
    path(
        "reports/<uuid:report_id>/preview/",
        views.ReportPreviewView.as_view(),
        name="preview_report",
    ),
    # PRISMA specific views (API endpoints)
    path(
        "api/session/<uuid:session_id>/prisma/flow/",
        views.PrismaFlowView.as_view(),
        name="api_prisma_flow",
    ),
    path(
        "sessions/<uuid:session_id>/prisma/checklist/",
        views.PrismaChecklistView.as_view(),
        name="prisma_checklist",
    ),
    path(
        "sessions/<uuid:session_id>/prisma/other-methods/",
        views.PrismaOtherMethodsSaveView.as_view(),
        name="prisma_other_methods_save",
    ),
    # Phase 0 browsing-visit import
    path(
        "api/session/<uuid:session_id>/import-browsing/",
        views.ImportBrowsingVisitsView.as_view(),
        name="api_import_browsing_visits",
    ),
    # API endpoints for AJAX
    path(
        "api/reports/<uuid:report_id>/status/",
        views.ReportStatusAPIView.as_view(),
        name="api_report_status",
    ),
    path(
        "api/session/<uuid:session_id>/reports/",
        views.ReportProgressAPIView.as_view(),
        name="api_report_progress",
    ),
    path(
        "api/session/<uuid:session_id>/charts/",
        views.ReportProgressAPIView.as_view(),
        name="api_chart_data",
    ),
]
