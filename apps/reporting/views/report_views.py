"""Report browsing, download, preview, status and PRISMA flow views.

Report list/detail browsing, file download with access control, in-browser
preview, generation status/progress APIs, and the PRISMA flow diagram and
checklist views.
"""

import logging
import time
from typing import List

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.db import DatabaseError, models
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView, View

from apps.review_manager.models import SearchSession
from apps.reporting.api_types import (
    ReportProgressItem,
    ReportProgressResponse,
    ReportStatusResponse,
)
from apps.reporting.models import ExportReport
from apps.reporting.services.prisma_reporting_service import PrismaReportingService
from apps.reporting.utils.error_handlers import handle_prisma_errors

logger = logging.getLogger(__name__)

# Race condition handling constants
# Time window in seconds to detect recently completed reports (potential race condition)
RACE_CONDITION_WINDOW_SECONDS = 5
# Wait time in seconds before retrying database read after race condition detected
RETRY_WAIT_SECONDS = 0.5


class ReportListView(LoginRequiredMixin, ListView):
    """
    List all reports for the authenticated user.

    Provides filtering and search capabilities.
    """

    model = ExportReport
    template_name = "reporting/report_list.html"
    context_object_name = "reports"
    paginate_by = 25

    def get_queryset(self):
        """Filter reports by user ownership."""
        return (
            ExportReport.objects.filter(session__owner=self.request.user)
            .select_related("session", "generated_by")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        """Add report statistics to context."""
        context = super().get_context_data(**kwargs)

        # Get all reports for the user (not just paginated)
        all_reports = ExportReport.objects.filter(
            session__owner=self.request.user
        ).select_related("session", "generated_by")

        # Calculate statistics
        context["total_count"] = all_reports.count()
        context["completed_count"] = all_reports.filter(status="completed").count()

        # Calculate storage used
        storage_used = (
            all_reports.filter(
                status="completed", file_size_bytes__isnull=False
            ).aggregate(total_size=models.Sum("file_size_bytes"))["total_size"]
            or 0
        )

        context["storage_used"] = storage_used

        return context


class ReportDetailView(LoginRequiredMixin, DetailView):
    """
    Display details of a specific report.

    Shows generation status, metadata, and download options.
    """

    model = ExportReport
    template_name = "reporting/report_detail.html"
    context_object_name = "report"
    pk_url_kwarg = "report_id"

    def get_object(self):
        """Get report and validate session ownership."""
        report = get_object_or_404(ExportReport, id=self.kwargs["report_id"])
        # Check if user owns the session
        if report.session.owner != self.request.user:
            raise Http404("Report not found")
        return report


class DownloadReportView(LoginRequiredMixin, View):
    """
    Secure file download with access control.

    Validates user ownership and serves files through Django.
    """

    def get(self, request, report_id):
        # Get report and validate ownership
        report = get_object_or_404(ExportReport, id=report_id)

        if report.session.owner != request.user:
            raise Http404("Report not found")

        # Determine appropriate redirect destination based on report type
        redirect_url = self._get_redirect_url(report)

        # Defence against race condition: if report recently completed but file_path not set yet
        if report.status == "completed" and not report.file_path:
            # Check if this is a recently completed report (potential race condition)
            time_since_completion = (
                timezone.now() - report.completed_at
            ).total_seconds()
            if (
                report.completed_at
                and time_since_completion < RACE_CONDITION_WINDOW_SECONDS
            ):
                logger.info(
                    f"Report {report_id} recently completed, waiting for file_path..."
                )
                time.sleep(RETRY_WAIT_SECONDS)  # Brief wait for transaction commit
                report.refresh_from_db()  # Reload from database

                if not report.file_path:
                    logger.warning(
                        f"Report {report_id} still missing file_path after retry"
                    )

        if report.status != "completed" or not report.file_path:
            logger.warning(
                f"Report {report_id} not ready for download - "
                f"status: {report.status}, file_path: {bool(report.file_path)}"
            )
            messages.error(request, "Report is not ready for download.")
            return redirect(redirect_url)

        # Check if file exists
        file_path = str(report.file_path)  # Convert FileField to string
        if not default_storage.exists(file_path):
            logger.error(f"Report file not found: {file_path} for report {report_id}")
            messages.error(
                request,
                "Report file not found. Please try generating the report again.",
            )
            return redirect(redirect_url)

        # Update download tracking
        report.download_count = (report.download_count or 0) + 1
        report.save(update_fields=["download_count"])

        # Serve file
        try:
            file_obj = default_storage.open(file_path, "rb")
            response = FileResponse(
                file_obj,
                as_attachment=True,
                filename=f"{report.title}.{report.export_format}",
            )
            response["Content-Type"] = report.get_content_type()
            logger.info(f"Successfully downloaded report {report_id}: {report.title}")
            return response
        except (FileNotFoundError, IOError) as e:
            logger.error(f"File I/O error downloading report {report_id}: {str(e)}")
            messages.error(request, f"Error downloading file: {str(e)}")
            return redirect(redirect_url)
        except (OSError, PermissionError, DatabaseError) as e:
            logger.exception(
                f"Unexpected error downloading report {report_id}: {str(e)}"
            )
            messages.error(
                request, "An unexpected error occurred while downloading the file"
            )
            return redirect(redirect_url)

    def _get_redirect_url(self, report):
        """
        Determine the appropriate redirect URL based on report type.

        For offline backup reports, redirect back to review interface.
        For other reports, redirect to reporting dashboard.
        """
        if report.report_type == "offline_backup":
            # Redirect back to the review results page where the offline backup button is located
            return reverse(
                "review_results:overview", kwargs={"session_id": report.session.id}
            )
        else:
            # For other reports, use the reporting dashboard
            return reverse(
                "reporting:dashboard", kwargs={"session_id": report.session.id}
            )


class PrismaFlowView(LoginRequiredMixin, View):
    """
    PRISMA 2020 flow diagram view.

    Returns JSON data for canvas-based diagram or handles export requests.
    """

    @handle_prisma_errors(default_return={})
    def get(self, request, *args, **kwargs):
        """Handle GET requests for PRISMA flow data or diagram export."""
        session_id = kwargs.get("session_id")
        session = get_object_or_404(SearchSession, id=session_id, owner=request.user)

        # Get format from query params
        format_type = request.GET.get("format", "json")

        # Generate PRISMA flow data
        prisma_service = PrismaReportingService()
        flow_data = prisma_service.generate_prisma_flow_data(str(session.id))

        if format_type == "json":
            # Return JSON data for canvas rendering
            return JsonResponse(flow_data)
        elif format_type in ["png", "pdf"]:
            # For PNG/PDF export, redirect to dashboard with export param
            return redirect(
                reverse("reporting:dashboard", kwargs={"session_id": session_id})
                + f"?export=prisma&format={format_type}"
            )
        else:
            return JsonResponse({"error": "Invalid format"}, status=400)


class PrismaChecklistView(LoginRequiredMixin, TemplateView):
    """
    PRISMA 2020 checklist compliance view.

    Shows 27-item checklist with completion status.
    """

    template_name = "reporting/prisma_checklist.html"

    @handle_prisma_errors(default_return={})
    def get_context_data(self, **kwargs):
        """Get context data for PRISMA checklist template.

        Args:
            **kwargs: Additional context variables including session_id.

        Returns:
            dict: Template context containing session and PRISMA checklist data.
        """
        context = super().get_context_data(**kwargs)

        session_id = kwargs.get("session_id")
        session = get_object_or_404(
            SearchSession, id=session_id, owner=self.request.user
        )

        prisma_service = PrismaReportingService()

        # Get checklist data - errors handled by decorator
        checklist_data = prisma_service.export_prisma_checklist(str(session.id))

        context.update(
            {
                "session": session,
                "checklist": checklist_data,
            }
        )

        return context


class ReportStatusAPIView(LoginRequiredMixin, View):
    """
    API endpoint for checking report generation status.

    Returns JSON with progress information using TypedDict.
    """

    def get(self, request, report_id):
        try:
            # Optimize query with select_related to avoid N+1 and speed up ownership check
            report = get_object_or_404(
                ExportReport.objects.select_related("session__owner"), id=report_id
            )

            # Validate ownership
            if report.session.owner != request.user:
                return JsonResponse({"error": "Access denied"}, status=403)

            # Build response using TypedDict structure directly
            response: ReportStatusResponse = {
                "id": str(report.id),
                "status": report.status,
                "progress_percentage": report.progress_percentage or 0,
                "title": report.title,
                "export_format": report.export_format,
                "created_at": report.created_at.isoformat(),
                "completed_at": (
                    report.completed_at.isoformat() if report.completed_at else None
                ),
                "download_url": (
                    reverse("reporting:download_report", args=[report.id])
                    if report.status == "completed" and report.file_path
                    else None
                ),
                "error_message": report.error_message,
            }

            return JsonResponse(response)

        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except (ExportReport.DoesNotExist, Http404):
            return JsonResponse({"error": "Report not found"}, status=404)
        except (DatabaseError, ValueError, KeyError):
            logger.exception("Unexpected error in report status API")
            return JsonResponse({"error": "An unexpected error occurred"}, status=500)


class ReportProgressAPIView(LoginRequiredMixin, View):
    """
    API endpoint for session report progress.

    Returns list of reports for a session with status using TypedDict.
    """

    def get(self, request, session_id):
        try:
            session = get_object_or_404(
                SearchSession, id=session_id, owner=request.user
            )

            reports = ExportReport.objects.filter(session=session).order_by(
                "-created_at"
            )[:10]

            # Build response using TypedDict structure directly
            report_items: List[ReportProgressItem] = []
            for report in reports:
                item: ReportProgressItem = {
                    "id": str(report.id),
                    "title": report.title,
                    "report_type": report.get_report_type_display(),
                    "export_format": report.export_format.upper(),
                    "status": report.status,
                    "progress_percentage": report.progress_percentage or 0,
                    "created_at": report.created_at.isoformat(),
                    "download_url": (
                        reverse("reporting:download_report", args=[report.id])
                        if report.status == "completed"
                        else None
                    ),
                }
                report_items.append(item)

            response: ReportProgressResponse = {"reports": report_items}
            return JsonResponse(response)

        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except (SearchSession.DoesNotExist, Http404):
            return JsonResponse({"error": "Session not found"}, status=404)
        except (DatabaseError, ValueError, KeyError):
            logger.exception("Unexpected error in report progress API")
            return JsonResponse({"error": "An unexpected error occurred"}, status=500)


class ReportPreviewView(LoginRequiredMixin, View):
    """
    Preview report in HTML format before generation.

    Renders the full report template with live data for preview purposes.
    """

    def get(self, request, report_id):
        """Handle GET request to preview a report."""
        report = self._get_and_validate_report(report_id, request.user)

        try:
            report_data = self._get_report_data(report)
            context = self._build_preview_context(report, report_data)
            html_content = self._render_preview(context)

            return HttpResponse(html_content, content_type="text/html")

        except (ValueError, AttributeError, KeyError) as e:
            return self._handle_preview_error(request, report_id, str(e))
        except (DatabaseError, TemplateDoesNotExist, OSError):
            logger.exception("Unexpected error generating report preview")
            return self._handle_preview_error(
                request,
                report_id,
                "An unexpected error occurred while generating report preview",
            )

    def _get_and_validate_report(self, report_id, user):
        """Get report and validate user ownership."""
        report = get_object_or_404(ExportReport, id=report_id)

        if report.session.owner != user:
            raise Http404("Report not found")

        return report

    def _get_report_data(self, report):
        """Retrieve report data from PrismaReportingService."""
        prisma_service = PrismaReportingService()

        return prisma_service.get_report_data(
            session_id=str(report.session.id), report_type=report.report_type
        )

    def _build_preview_context(self, report, report_data):
        """Build context dictionary for preview template."""
        return {
            "report": report,
            "session": report.session,
            "data": report_data,  # Template expects data under 'data' key
            "preview_mode": True,  # Flag to indicate preview mode
            "generated_at": timezone.now(),
            "include_prisma_flow": report.parameters.get("include_prisma_flow", True),
            "include_checklist": report.parameters.get("include_checklist", False),
            "include_metadata": report.parameters.get("include_metadata", True),
        }

    def _render_preview(self, context):
        """Render the preview template with context."""
        template = get_template("reporting/exports/full_report.html")
        return template.render(context)

    def _handle_preview_error(self, request, report_id, error_message):
        """Handle preview generation errors with user feedback."""
        messages.error(request, f"Unable to generate report preview: {error_message}")
        return redirect("reporting:report_detail", report_id=report_id)
