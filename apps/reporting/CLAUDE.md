# Reporting App

PRISMA 2020 reports, PDF/Excel/Word export, and email notifications.

## Model

- `ExportReport` -- report record with file storage (`report_upload_path`), `get_content_type`

## Views

| View | Purpose |
|------|---------|
| `ReportDashboardView` | Report overview + PRISMA other methods form |
| `ReportGenerationView` | Create and queue report generation (GET/POST) |
| `ReportListView` / `ReportDetailView` | Browse reports |
| `DownloadReportView` | File download with redirect |
| `ReportPreviewView` | In-browser report preview |
| `PrismaFlowView` / `PrismaChecklistView` | PRISMA 2020 flow diagram and checklist |
| `ReportStatusAPIView` / `ReportProgressAPIView` | Generation status APIs |
| `GenerateOfflineBackupView` / `ImportOfflineBackupView` | Offline backup export/import |
| `IRRReportGenerateView` | IRR-specific report generation |
| `AuditTrailExportView` | Audit trail export |
| `PrismaOtherMethodsSaveView` | GET/POST JSON API for PRISMA other methods data |

`views/` is a package: `dashboard_views` (dashboard + generation), `report_views` (browse/download/preview/status + PRISMA flow/checklist), `backup_views`, `dual_screening_views`. All classes are re-exported from `views/__init__.py`, so `from . import views; views.X` is unchanged.

## Other Key Files

- `tasks.py` -- Celery tasks for async report generation (WeasyPrint PDF)
- `services/` -- report generation services, `ReportEmailService`. `PrismaReportingService._gather_identification_data()` counts `is_manually_added=True` results as `other_sources`. `ReportDashboardAssemblyService` builds the dashboard's PRISMA-flow and other-methods context (with a shared basic-stats fallback), keeping `ReportDashboardView.get_context_data` thin.
- `utils/` -- report utilities
- `forms.py` -- report configuration forms
- `dependencies.py` -- dependency injection
- `constants.py` -- report type constants (`STANDARD_EXCLUSION_REASONS` derived from `SimpleReviewDecision` at startup via `apps.py`)
