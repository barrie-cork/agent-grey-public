"""Offline backup export and import views for the reporting app.

Generate an offline backup of review data and import an Excel offline backup.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import View

from apps.review_manager.models import SearchSession
from apps.reporting.forms import ExcelImportForm
from apps.reporting.models import ExportReport

logger = logging.getLogger(__name__)


class GenerateOfflineBackupView(LoginRequiredMixin, View):
    """
    Generate offline backup Excel export for review sessions.

    Allows users to download search results and PRISMA data as a fully
    functional Excel workbook during the review phase for offline work.
    """

    def post(self, request, session_id):
        """Generate offline backup Excel file asynchronously."""
        try:
            # Get session and validate ownership with optimized query
            session = get_object_or_404(
                SearchSession.objects.only("id", "title", "status", "owner_id"),
                id=session_id,
                owner=request.user,
            )

            # Validate session status - only available during review phase
            if session.status not in ["ready_for_review", "under_review"]:
                return JsonResponse(
                    {
                        "error": "Offline backup is only available during the review phase",
                        "current_status": session.get_status_display(),
                    },
                    status=400,
                )

            # Create ExportReport instance immediately (validation happens in Celery task)
            # This responds quickly to the user while task processes asynchronously
            report = ExportReport.objects.create(
                session=session,
                generated_by=request.user,
                report_type="offline_backup",
                export_format="xlsx",
                title=f"Offline Backup - {session.title}",
                status="pending",
                parameters={
                    "backup_type": "full_review_data",
                    "include_prisma_stats": True,
                    "include_validation": True,
                },
            )

            # Queue task asynchronously
            from apps.reporting.tasks import generate_report_task

            task_id = None
            try:
                # Use apply_async with task-level timeout to prevent hanging
                task_result = generate_report_task.apply_async(
                    args=(str(report.id),),
                    expires=300,  # Task expires after 5 minutes if not picked up
                    retry=False,
                )
                task_id = str(task_result.id)

                logger.info(
                    f"Offline backup generation queued for session {session_id} "
                    f"by user {request.user.id}, task_id: {task_id}"
                )
            except (ConnectionError, TimeoutError, OSError) as queue_error:
                # Log but don't fail - frontend will poll report status
                logger.error(
                    f"Failed to queue Celery task for report {report.id}: {queue_error}",
                    exc_info=True,
                )
                # Task may still be picked up by autodiscovery

            # Return immediately to prevent timeout
            # Frontend will poll progress_url for status updates
            return JsonResponse(
                {
                    "status": "generating",
                    "task_id": task_id,
                    "report_id": str(report.id),
                    "progress_url": reverse(
                        "reporting:api_report_status", args=[report.id]
                    ),
                    "download_url": reverse(
                        "reporting:download_report", args=[report.id]
                    ),
                    "message": "Offline backup generation started. You will be notified when ready.",
                }
            )

        except SearchSession.DoesNotExist:
            logger.warning(
                f"Offline backup attempted for non-existent session {session_id}"
            )
            return JsonResponse({"error": "Session not found"}, status=404)
        except (DatabaseError, ValueError, OSError) as e:
            logger.exception(
                f"Offline backup generation failed for session {session_id}: {e}"
            )
            return JsonResponse(
                {
                    "error": "Failed to start backup generation. Please try again.",
                    "details": str(e) if request.user.is_staff else None,
                },
                status=500,
            )


class ImportOfflineBackupView(LoginRequiredMixin, View):
    """
    Handle Excel import for syncing offline review changes.

    Allows users to upload edited Excel offline backup files and
    synchronise review decisions back to the database.
    """

    def get(self, request, session_id):
        """Display import form."""
        session = get_object_or_404(SearchSession, id=session_id, owner=request.user)

        # Validate session status - only available during review phase
        if session.status not in ["ready_for_review", "under_review"]:
            messages.error(request, "Import is only available during the review phase.")
            return redirect("review_results:overview", session_id=session_id)

        form = ExcelImportForm(initial={"session": session_id})

        from django.template.response import TemplateResponse

        return TemplateResponse(
            request,
            "reporting/import_backup.html",
            {
                "form": form,
                "session": session,
            },
        )

    def post(self, request, session_id):
        """Process uploaded Excel file."""
        session = get_object_or_404(SearchSession, id=session_id, owner=request.user)

        # Validate session status
        if session.status not in ["ready_for_review", "under_review"]:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {"error": "Import is only available during the review phase"},
                    status=400,
                )
            else:
                messages.error(
                    request, "Import is only available during the review phase."
                )
                return redirect("review_results:overview", session_id=session_id)

        form = ExcelImportForm(request.POST, request.FILES)

        if form.is_valid():
            excel_file = form.cleaned_data["excel_file"]

            # Save temporarily to disk
            import tempfile

            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
                for chunk in excel_file.chunks():
                    tmp_file.write(chunk)
                temp_path = tmp_file.name

            # Queue import task with reviewer ID
            from apps.reporting.tasks import import_excel_backup_task

            task_result = import_excel_backup_task.delay(
                str(session_id), temp_path, reviewer_id=request.user.id
            )

            logger.info(
                f"Excel import task queued for session {session_id} by user {request.user.id}"
            )

            # Check if this is an AJAX request
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "status": "processing",
                        "task_id": str(task_result.id),
                        "message": "Import started. Processing your changes...",
                    }
                )
            else:
                messages.success(request, "Import started. You'll see results shortly.")
                return redirect("review_results:overview", session_id=session_id)

        # Form validation failed
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {"error": "Invalid file upload", "errors": form.errors}, status=400
            )
        else:
            from django.template.response import TemplateResponse

            return TemplateResponse(
                request,
                "reporting/import_backup.html",
                {
                    "form": form,
                    "session": session,
                },
            )
