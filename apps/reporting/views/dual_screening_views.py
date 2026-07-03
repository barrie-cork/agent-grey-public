"""Dual-screening reporting views.

IRR (Cohen's Kappa) report generation, audit-trail export, and saving the
PRISMA 2020 "other methods" data.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import View

from apps.review_manager.models import SearchSession
from apps.reporting.forms import PrismaOtherMethodsForm
from apps.reporting.models import ExportReport
from apps.reporting.services.prisma_reporting_service import PrismaReportingService

logger = logging.getLogger(__name__)


class IRRReportGenerateView(LoginRequiredMixin, View):
    """
    Generate Inter-Rater Reliability (IRR) report for dual screening.

    Creates PDF report with Cohen's Kappa metrics, percentage agreement,
    conflict breakdown, and compliance recommendations.
    """

    def post(self, request, session_id):
        """Generate IRR report asynchronously."""
        try:
            # Get session and validate ownership
            session = get_object_or_404(
                SearchSession, id=session_id, owner=request.user
            )

            # Validate dual screening is enabled for this session
            if (
                not session.current_configuration
                or session.current_configuration.min_reviewers_per_result < 2
            ):
                return JsonResponse(
                    {"error": "Dual screening is not enabled for this session"},
                    status=400,
                )

            # Create ExportReport instance
            report = ExportReport.objects.create(
                session=session,
                generated_by=request.user,
                report_type="irr_report",
                export_format="pdf",
                title=f"IRR Report - {session.title}",
                status="pending",
                parameters={
                    "include_metadata": request.POST.get("include_metadata") == "on",
                },
            )

            # Queue task asynchronously
            from apps.reporting.tasks import generate_irr_report_task

            task_result = generate_irr_report_task.apply_async(
                args=(str(report.id),),
                expires=300,
                retry=False,
            )

            logger.info(
                f"IRR report generation queued for session {session_id} "
                f"by user {request.user.id}, task_id: {task_result.id}"
            )

            # Return immediately for frontend polling
            return JsonResponse(
                {
                    "status": "generating",
                    "task_id": str(task_result.id),
                    "report_id": str(report.id),
                    "progress_url": reverse(
                        "reporting:api_report_status", args=[report.id]
                    ),
                    "download_url": reverse(
                        "reporting:download_report", args=[report.id]
                    ),
                    "message": "IRR report generation started. You will be notified when ready.",
                }
            )

        except SearchSession.DoesNotExist:
            logger.warning(
                f"IRR report attempted for non-existent session {session_id}"
            )
            return JsonResponse({"error": "Session not found"}, status=404)
        except (DatabaseError, ValueError, OSError) as e:
            logger.exception(
                f"IRR report generation failed for session {session_id}: {e}"
            )
            return JsonResponse(
                {
                    "error": "Failed to start IRR report generation. Please try again.",
                    "details": str(e) if request.user.is_staff else None,
                },
                status=500,
            )


class AuditTrailExportView(LoginRequiredMixin, View):
    """
    Export decision audit trail for PRISMA Item 7 compliance.

    Returns CSV file with complete reviewer decision history for
    institutional audits and transparent reporting.
    """

    def get(self, request, session_id):
        """Export audit trail as CSV download."""
        try:
            # Get session and validate ownership
            session = get_object_or_404(
                SearchSession, id=session_id, owner=request.user
            )

            # Generate CSV content using ExportService
            from apps.reporting.services.export_service import ExportService

            export_service = ExportService()
            csv_content = export_service.export_decision_audit_trail(str(session_id))

            # Create HTTP response with CSV
            response = HttpResponse(csv_content, content_type="text/csv")
            filename = f"audit_trail_{session.title}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'

            logger.info(
                f"Audit trail exported for session {session_id} by user {request.user.id}"
            )

            return response

        except SearchSession.DoesNotExist:
            logger.warning(
                f"Audit trail export attempted for non-existent session {session_id}"
            )
            messages.error(request, "Session not found")
            return redirect("review_results:overview", session_id=session_id)
        except (DatabaseError, ValueError, OSError) as e:
            logger.exception(f"Audit trail export failed for session {session_id}: {e}")
            messages.error(request, f"Failed to export audit trail: {str(e)}")
            return redirect("review_results:overview", session_id=session_id)


class PrismaOtherMethodsSaveView(LoginRequiredMixin, View):
    """Save or retrieve PRISMA 2020 'other methods' data for a session."""

    def get(self, request, session_id):
        """Return JSON: saved data merged with auto-populated defaults."""
        session = get_object_or_404(SearchSession, id=session_id, owner=request.user)

        prisma_service = PrismaReportingService()
        auto_data = prisma_service.auto_populate_other_methods(str(session.id))

        # Saved values override auto-populated defaults (exclude exclusion_reasons)
        saved = session.prisma_other_methods or {}
        merged = {**auto_data}
        for key in PrismaOtherMethodsForm.base_fields:
            if key in saved:
                merged[key] = saved[key]

        return JsonResponse(merged)

    def post(self, request, session_id):
        """Validate and save other-methods overrides."""
        session = get_object_or_404(SearchSession, id=session_id, owner=request.user)

        form = PrismaOtherMethodsForm(request.POST)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors}, status=400)

        # Build data dict from cleaned form fields
        data = {}
        for field_name in PrismaOtherMethodsForm.base_fields:
            value = form.cleaned_data.get(field_name)
            if value is not None:
                data[field_name] = value

        # Preserve exclusion_reasons from auto-populate (not user-editable)
        prisma_service = PrismaReportingService()
        auto_data = prisma_service.auto_populate_other_methods(str(session.id))
        data["exclusion_reasons"] = auto_data.get("exclusion_reasons", {})

        session.prisma_other_methods = data
        session.save(update_fields=["prisma_other_methods"])

        warnings = getattr(form, "warnings", [])
        return JsonResponse({"status": "saved", "warnings": warnings})


class ImportBrowsingVisitsView(LoginRequiredMixin, View):
    """
    JSON API endpoint for importing a browsing-visit report (Phase 0 prototype).

    POST with ``Content-Type: application/json`` body ``{"visits": [...]}``.
    Creates BrowsingVisit rows and promotes any entry with ``add_to_queue=true``
    to the screening queue via ManualResultService.
    """

    def post(self, request, session_id):
        """Process a JSON browsing report and create BrowsingVisit records."""
        import json

        session = get_object_or_404(SearchSession, id=session_id, owner=request.user)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON body."}, status=400)

        from apps.review_results.services.browsing_import_service import (
            BrowsingImportService,
        )

        result = BrowsingImportService.import_from_json(session, request.user, data)

        # Return 400 only when nothing was imported and there are errors
        if (
            result.errors
            and result.visits_created == 0
            and result.queue_items_added == 0
        ):
            return JsonResponse({"errors": result.errors}, status=400)

        status_code = (
            201 if (result.visits_created or result.queue_items_added) else 200
        )
        return JsonResponse(
            {
                "visits_created": result.visits_created,
                "visits_skipped": result.visits_skipped,
                "queue_items_added": result.queue_items_added,
                "errors": result.errors,
            },
            status=status_code,
        )
