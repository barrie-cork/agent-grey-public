"""Report dashboard and generation views for the reporting app.

The main reporting dashboard (PRISMA flow, metrics, recent reports, generation
interface) and the report generation endpoint.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView, View

from apps.core.utils.error_responses import validation_error_response
from apps.review_manager.access import check_session_access
from apps.review_manager.models import SearchSession
from apps.reporting.api_types import (
    ReportGenerationInput,
)
from apps.reporting.models import ExportReport
from apps.reporting.services.dashboard_assembly_service import (
    ReportDashboardAssemblyService,
)

logger = logging.getLogger(__name__)


class ReportDashboardView(LoginRequiredMixin, TemplateView):
    """
    Main reporting dashboard showing available reports and visualizations.

    Displays:
    - PRISMA flow diagram
    - Performance metrics
    - Recent reports
    - Report generation interface
    """

    template_name = "reporting/dashboard.html"

    def get_context_data(self, **kwargs):
        """Get context data for reporting dashboard template.

        Args:
            **kwargs: Additional context variables including session_id.

        Returns:
            dict: Template context containing session, PRISMA flow data,
                 recent reports, and review statistics.
        """
        context = super().get_context_data(**kwargs)

        # Get session and validate access (owner or accepted-invitation reviewer)
        session_id = kwargs.get("session_id")
        session = get_object_or_404(SearchSession, id=session_id)
        has_access, _ = check_session_access(self.request.user, session)
        if not has_access:
            raise Http404("Session not found")

        assembly = ReportDashboardAssemblyService()
        prisma_flow_data = assembly.get_prisma_flow_data(session)

        # Get recent reports for this session with optimized query
        recent_reports = (
            ExportReport.objects.filter(session=session)
            .select_related("generated_by", "session")
            .order_by("-created_at")[:5]
        )

        # Calculate total reviewed (included + excluded + maybe)
        review_stats = {
            "total_reviewed": (
                prisma_flow_data.get("results_included", 0)
                + prisma_flow_data.get("results_excluded", 0)
                + prisma_flow_data.get("results_maybe", 0)
            )
        }

        context.update(
            {
                "session": session,
                "prisma_flow_data": prisma_flow_data,
                "recent_reports": recent_reports,
                "review_stats": review_stats,
            }
        )

        context.update(assembly.get_other_methods_context(session))

        # Debug log to verify PRISMA data structure for issue #88
        logger.debug(
            f"PRISMA flow data for template (session {session_id}): "
            f"{prisma_flow_data.get('identification', {}).get('total', 'MISSING')}"
        )

        return context


class ReportGenerationView(LoginRequiredMixin, View):
    """
    Handle report generation requests from dashboard form.

    Creates ExportReport records and initiates background processing.
    """

    def get(self, request, session_id):
        """Handle GET request for cloning reports."""
        # Get and validate session (owner or accepted-invitation reviewer)
        session = get_object_or_404(SearchSession, id=session_id)
        has_access, _ = check_session_access(request.user, session)
        if not has_access:
            raise Http404("Session not found")

        # Check if this is a clone request
        clone_id = request.GET.get("clone")
        if clone_id:
            # Get the report to clone (scope to the already-validated session)
            original_report = get_object_or_404(
                ExportReport, id=clone_id, session=session
            )

            # Create a new report with the same parameters
            report = ExportReport.objects.create(
                session=session,
                generated_by=request.user,
                report_type=original_report.report_type,
                export_format=original_report.export_format,
                title=f"{session.title} - {original_report.export_format.upper()} Report (Cloned)",
                file_size_bytes=0,
                parameters=original_report.parameters.copy(),
            )

            # Import task here to avoid circular imports
            try:
                from apps.reporting.tasks import generate_report_task

                generate_report_task.delay(str(report.id))

                messages.success(
                    request,
                    f"Report generation started. You'll be notified when your "
                    f"{original_report.export_format.upper()} report is ready.",
                )
            except (ImportError, OSError):
                messages.error(request, "Unable to start report generation.")

        else:
            messages.error(request, "No report specified to clone.")

        return redirect("reporting:dashboard", session_id=session.id)

    def post(self, request, session_id):
        """Handle form submission from dashboard."""

        session = self._get_and_validate_session(session_id, request.user)
        validated_data = self._validate_input_data(request.POST)
        if not validated_data:
            # For AJAX requests, return error as JSON
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return validation_error_response(
                    field_errors={"form": ["Invalid input data"]},
                    message="Invalid input data",
                )
            return redirect("reporting:dashboard", session_id=session_id)

        # Create report and queue generation atomically
        report, generation_queued = self._create_and_queue_report(
            session, request.user, validated_data
        )
        if not generation_queued:
            self._generate_demo_report(report, session)

        # Check if this is an AJAX request - ALWAYS return JSON for AJAX
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            # Return JSON response with report details for polling
            return JsonResponse(
                {
                    "report_id": str(report.id),
                    "status": report.status,
                    "title": report.title,
                    "export_format": report.export_format,  # Changed from 'format' to match JS expectations
                    "created_at": report.created_at.isoformat(),
                    "generation_mode": "async" if generation_queued else "demo",
                }
            )
        else:
            # Only redirect for non-AJAX requests
            return redirect("reporting:dashboard", session_id=session.id)

    def _get_and_validate_session(self, session_id, user):
        """Get and validate session access (owner or accepted-invitation reviewer)."""
        session = get_object_or_404(SearchSession, id=session_id)
        has_access, _ = check_session_access(user, session)
        if not has_access:
            raise Http404("Session not found")
        return session

    def _validate_input_data(self, post_data):
        """Validate and return cleaned data."""
        # Manual validation instead of Pydantic
        format_value = post_data.get("format", "pdf")

        # Validate format
        if format_value not in ["pdf", "json", "csv"]:
            messages.error(self.request, f"Invalid format: {format_value}")
            return None

        # Build validated data using TypedDict structure
        validated_data: ReportGenerationInput = {
            "format": format_value,
            "include_prisma_flow": post_data.get("include_prisma_flow") == "on",
            "include_prisma_checklist": post_data.get("include_checklist") == "on",
            "include_metadata": post_data.get("include_metadata") == "on",
        }

        return validated_data

    def _create_report_record(self, session, user, validated_data):
        """Create and return ExportReport instance."""
        report_type = self._determine_report_type(validated_data["format"])
        return ExportReport.objects.create(
            session=session,
            generated_by=user,
            report_type=report_type,
            export_format=validated_data["format"],
            title=f"{session.title} - {validated_data['format'].upper()} Report",
            file_size_bytes=0,
            parameters={
                "include_prisma_flow": validated_data["include_prisma_flow"],
                "include_checklist": validated_data["include_prisma_checklist"],
                "include_metadata": validated_data["include_metadata"],
            },
        )

    def _create_and_queue_report(self, session, user, validated_data):
        """Create report and queue generation atomically."""
        from django.db import connection, transaction

        with transaction.atomic():
            report = self._create_report_record(session, user, validated_data)
            report.save()  # Ensure committed before queuing

            # Small delay to ensure DB commit visibility across connections
            connection.ensure_connection()

            generation_queued = self._queue_report_generation(report)
            return report, generation_queued

    def _determine_report_type(self, format_type):
        """Determine report type based on format."""
        if format_type == "pdf":
            return "full_report"
        elif format_type == "csv":
            return "results_summary"
        else:
            return "bibliography"

    def _queue_report_generation(self, report):
        """Try to queue async report generation."""
        try:
            from apps.reporting.tasks import generate_report_task

            generate_report_task.delay(str(report.id))
            messages.success(
                self.request,
                f"Report generation started. You'll be notified when your "
                f"{report.export_format.upper()} report is ready.",
            )
            return True
        except (ImportError, OSError):
            return False

    def _generate_demo_report(self, report, session):
        """Generate report synchronously for demo purposes."""
        from apps.reporting.services.demo_report_service import DemoReportService

        demo_service = DemoReportService()
        demo_service.generate(report, session)
        messages.success(self.request, "Report generated successfully (demo mode).")
