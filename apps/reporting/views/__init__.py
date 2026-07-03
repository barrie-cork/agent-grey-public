"""Views package for the reporting app.

This package splits the former single views module into cohesive submodules.
All public view classes are re-exported here so existing ``views.X`` references
(e.g. in reporting/urls.py via ``from . import views``) keep working unchanged.
"""

from .backup_views import GenerateOfflineBackupView, ImportOfflineBackupView
from .dashboard_views import ReportDashboardView, ReportGenerationView
from .dual_screening_views import (
    AuditTrailExportView,
    ImportBrowsingVisitsView,
    IRRReportGenerateView,
    PrismaOtherMethodsSaveView,
)
from .report_views import (
    DownloadReportView,
    PrismaChecklistView,
    PrismaFlowView,
    ReportDetailView,
    ReportListView,
    ReportPreviewView,
    ReportProgressAPIView,
    ReportStatusAPIView,
)

__all__ = [
    # Dashboard and generation
    "ReportDashboardView",
    "ReportGenerationView",
    # Report browsing, download, preview, status, PRISMA flow/checklist
    "ReportListView",
    "ReportDetailView",
    "DownloadReportView",
    "PrismaFlowView",
    "PrismaChecklistView",
    "ReportStatusAPIView",
    "ReportProgressAPIView",
    "ReportPreviewView",
    # Offline backup
    "GenerateOfflineBackupView",
    "ImportOfflineBackupView",
    # Dual screening
    "IRRReportGenerateView",
    "AuditTrailExportView",
    "PrismaOtherMethodsSaveView",
    "ImportBrowsingVisitsView",
]
