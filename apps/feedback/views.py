"""
Views for handling user feedback submissions.
"""

import json
import logging
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, ListView

from .forms import FeedbackForm, QuickFeedbackForm
from .models import UserFeedback
from .serializers import serialize_feedback
from .services import transcribe_audio_with_groq

logger = logging.getLogger(__name__)

# File upload size limits (bytes)
MAX_AUDIO_SIZE = 5 * 1024 * 1024  # 5MB
MAX_SCREENSHOT_SIZE = 2 * 1024 * 1024  # 2MB


class FeedbackSubmissionView(View):
    """
    Handle AJAX feedback submissions from any page.

    Supports both authenticated and anonymous users.
    Accepts JSON or multipart/form-data (for file uploads).
    """

    def post(self, request):
        """Handle POST request for feedback submission."""
        try:
            content_type = request.content_type or ""

            if "application/json" in content_type:
                data = json.loads(request.body)
                files = {}
            else:
                data = request.POST.dict()
                files = request.FILES

            # Parse interaction_context from JSON string (FormData sends as string)
            if isinstance(data.get("interaction_context"), str):
                try:
                    data["interaction_context"] = json.loads(
                        data["interaction_context"]
                    )
                except (json.JSONDecodeError, TypeError):
                    data["interaction_context"] = {}

            # Validate file sizes
            audio_file = files.get("audio_file")
            screenshot = files.get("screenshot")

            if audio_file and audio_file.size > MAX_AUDIO_SIZE:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Audio file too large (max 5MB).",
                    },
                    status=400,
                )

            if screenshot and screenshot.size > MAX_SCREENSHOT_SIZE:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Screenshot too large (max 2MB).",
                    },
                    status=400,
                )

            # Extract page context
            page_path = data.get("page_path", request.META.get("HTTP_REFERER", ""))
            page_title = data.get("page_title", "")

            # Capture browser information for debugging
            browser_info = {
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                "ip_address": self.get_client_ip(request),
                "timestamp": timezone.now().isoformat(),
                "page_url": page_path,
                "screen_resolution": data.get("screen_resolution", ""),
                "viewport_size": data.get("viewport_size", ""),
                "browser_language": request.META.get("HTTP_ACCEPT_LANGUAGE", ""),
            }

            # Create form with context
            form = FeedbackForm(
                data=data,
                user=request.user if request.user.is_authenticated else None,
                page_path=page_path,
                page_title=page_title,
            )

            if form.is_valid():
                feedback = form.save(commit=False)
                feedback.browser_info = browser_info

                # Enhanced fields from FormData
                feedback.severity = data.get("severity", "")
                feedback.expected_behaviour = data.get("expected_behaviour", "")
                feedback.actual_behaviour = data.get("actual_behaviour", "")
                feedback.frequency = data.get("frequency", "")
                feedback.contact_email = data.get("contact_email", "")
                feedback.interaction_context = data.get("interaction_context", {})

                # File uploads
                if audio_file:
                    feedback.audio_file = audio_file
                    feedback.audio_duration_ms = (
                        int(data.get("audio_duration_ms", 0)) or None
                    )

                if screenshot:
                    feedback.screenshot = screenshot

                feedback.save()

                # Trigger async transcription if audio was uploaded
                # Skip if already transcribed client-side
                pre_transcribed = data.get("pre_transcribed") == "true"
                if feedback.audio_file and not pre_transcribed:
                    from apps.feedback.tasks import transcribe_feedback_audio

                    transcribe_feedback_audio.delay(str(feedback.id))

                logger.info(
                    "Feedback submitted: %s from %s on %s",
                    feedback.id,
                    feedback.submitter_display,
                    page_path,
                )

                return JsonResponse(
                    {
                        "success": True,
                        "message": "Thank you for your feedback! We appreciate your input.",
                        "feedback_id": str(feedback.id),
                    }
                )
            else:
                return JsonResponse(
                    {
                        "success": False,
                        "errors": form.errors,
                        "message": "Please correct the errors and try again.",
                    },
                    status=400,
                )

        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "message": "Invalid JSON data provided."}, status=400
            )

        except (ValidationError, DatabaseError):
            logger.exception("Error processing feedback submission")
            return JsonResponse(
                {
                    "success": False,
                    "message": "An error occurred while submitting your feedback. Please try again.",
                },
                status=500,
            )

    def get_client_ip(self, request):
        """Get the client's IP address from the request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class TranscribeAudioView(LoginRequiredMixin, View):
    """Synchronously transcribe an audio file via Groq Whisper API."""

    def post(self, request):
        audio_file = request.FILES.get("audio_file")
        if not audio_file:
            return JsonResponse(
                {"success": False, "message": "No audio file provided."},
                status=400,
            )

        if audio_file.size > MAX_AUDIO_SIZE:
            return JsonResponse(
                {"success": False, "message": "Audio file too large (max 5MB)."},
                status=400,
            )

        try:
            audio_data = audio_file.read()
            filename = audio_file.name or "recording.webm"
            text = transcribe_audio_with_groq(audio_data, filename)
            return JsonResponse({"success": True, "text": text})
        except ValueError as e:
            logger.warning("Transcription config error: %s", e)
            return JsonResponse(
                {"success": False, "message": "Transcription service not configured."},
                status=503,
            )
        except Exception:
            logger.exception("Transcription failed")
            return JsonResponse(
                {
                    "success": False,
                    "message": "Transcription failed. Please type your feedback instead.",
                },
                status=502,
            )


class FeedbackExportView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Export feedback as JSON for clustering scripts. Staff only."""

    def test_func(self):
        return self.request.user.is_staff

    def get(self, request):
        status = request.GET.get("status", "new")
        limit = request.GET.get("limit", "0")
        has_issue = request.GET.get("has_issue")

        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 0

        qs = UserFeedback.objects.select_related("user").order_by("-created_at")
        if status != "all":
            qs = qs.filter(status=status)
        if has_issue:
            qs = qs.exclude(github_issue_number__isnull=True)
        if limit > 0:
            qs = qs[:limit]

        output = [serialize_feedback(fb, request=request) for fb in qs]
        return JsonResponse(output, safe=False)


class QuickFeedbackView(View):
    """
    Handle quick feedback submissions (thumbs up/down, ratings).
    """

    def post(self, request):
        """Handle quick feedback submission."""
        try:
            if request.content_type == "application/json":
                data = json.loads(request.body)
            else:
                data = request.POST.dict()

            page_path = data.get("page_path", request.META.get("HTTP_REFERER", ""))
            page_title = data.get("page_title", "")

            form = QuickFeedbackForm(
                data=data,
                user=request.user if request.user.is_authenticated else None,
                page_path=page_path,
                page_title=page_title,
            )

            if form.is_valid():
                feedback = form.save()

                logger.info(f"Quick feedback submitted: {feedback.id}")

                return JsonResponse(
                    {"success": True, "message": "Thank you for your quick feedback!"}
                )
            else:
                return JsonResponse(
                    {"success": False, "errors": form.errors}, status=400
                )

        except (ValidationError, DatabaseError):
            logger.exception("Error processing quick feedback")
            return JsonResponse(
                {"success": False, "message": "An error occurred. Please try again."},
                status=500,
            )


class FeedbackListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    List view for administrators to review feedback.
    """

    model = UserFeedback
    template_name = "feedback/feedback_list.html"
    context_object_name = "feedback_list"
    paginate_by = 25

    def test_func(self):
        """Only allow staff users to view feedback."""
        return self.request.user.is_staff

    def get_queryset(self):
        """Filter feedback based on query parameters."""
        queryset = UserFeedback.objects.select_related("user").order_by("-created_at")

        # Filter by status
        status = self.request.GET.get("status")
        if status and status in dict(UserFeedback.STATUS_CHOICES):
            queryset = queryset.filter(status=status)

        # Filter by feedback type
        feedback_type = self.request.GET.get("type")
        if feedback_type and feedback_type in dict(UserFeedback.FEEDBACK_TYPES):
            queryset = queryset.filter(feedback_type=feedback_type)

        # Filter by page
        page_path = self.request.GET.get("page")
        if page_path:
            queryset = queryset.filter(page_path__icontains=page_path)

        # Date range filter
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")

        if date_from:
            try:
                date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
                queryset = queryset.filter(created_at__date__gte=date_from)
            except ValueError:
                pass

        if date_to:
            try:
                date_to = datetime.strptime(date_to, "%Y-%m-%d").date()
                queryset = queryset.filter(created_at__date__lte=date_to)
            except ValueError:
                pass

        return queryset

    def get_context_data(self, **kwargs):
        """Add additional context for the template."""
        context = super().get_context_data(**kwargs)

        # Add filter choices
        context["status_choices"] = UserFeedback.STATUS_CHOICES
        context["type_choices"] = UserFeedback.FEEDBACK_TYPES

        # Add current filter values
        context["current_filters"] = {
            "status": self.request.GET.get("status", ""),
            "type": self.request.GET.get("type", ""),
            "page": self.request.GET.get("page", ""),
            "date_from": self.request.GET.get("date_from", ""),
            "date_to": self.request.GET.get("date_to", ""),
        }

        # Add summary statistics
        qs = self.get_queryset()
        context["statistics"] = {
            "total": qs.count(),
            "new": qs.filter(status="new").count(),
            "in_progress": qs.filter(status="in_progress").count(),
            "resolved": qs.filter(status="resolved").count(),
            "critical": qs.filter(feedback_type="bug", rating__lte=2)
            .exclude(status__in=["resolved", "dismissed"])
            .count(),
        }

        return context


class FeedbackDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Detail view for individual feedback items.
    """

    model = UserFeedback
    template_name = "feedback/feedback_detail.html"
    context_object_name = "feedback"

    def test_func(self):
        """Only allow staff users to view feedback details."""
        return self.request.user.is_staff


@login_required
@require_http_methods(["POST"])
def update_feedback_status(request, feedback_id):
    """
    AJAX endpoint to update feedback status.
    """
    if not request.user.is_staff:
        return JsonResponse(
            {"success": False, "message": "Permission denied."}, status=403
        )

    try:
        feedback = get_object_or_404(UserFeedback, id=feedback_id)

        new_status = request.POST.get("status")
        admin_notes = request.POST.get("admin_notes", "")

        if new_status not in dict(UserFeedback.STATUS_CHOICES):
            return JsonResponse(
                {"success": False, "message": "Invalid status."}, status=400
            )

        feedback.status = new_status
        if admin_notes:
            current_time = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
            note_entry = f"[{current_time}] {request.user.username}: {admin_notes}"
            if feedback.admin_notes:
                feedback.admin_notes += f"\n\n{note_entry}"
            else:
                feedback.admin_notes = note_entry

        feedback.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"Status updated to {feedback.get_status_display()}.",
            }
        )

    except (DatabaseError, ValueError):
        logger.exception("Error updating feedback status")
        return JsonResponse(
            {"success": False, "message": "An error occurred while updating status."},
            status=500,
        )


class FeedbackStatsView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    API endpoint for feedback statistics (for dashboards).
    """

    def test_func(self):
        """Only allow staff users to access statistics."""
        return self.request.user.is_staff

    def get(self, request):
        """Return feedback statistics in JSON format."""
        try:
            # Date range for statistics
            days = int(request.GET.get("days", 30))
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days)

            # Basic counts
            total_feedback = UserFeedback.objects.filter(
                created_at__date__gte=start_date
            ).count()

            # Group by feedback type
            type_stats = (
                UserFeedback.objects.filter(created_at__date__gte=start_date)
                .values("feedback_type")
                .annotate(count=Count("id"))
                .order_by("-count")
            )

            # Group by status
            status_stats = (
                UserFeedback.objects.filter(created_at__date__gte=start_date)
                .values("status")
                .annotate(count=Count("id"))
                .order_by("-count")
            )

            # Top pages with feedback
            page_stats = (
                UserFeedback.objects.filter(created_at__date__gte=start_date)
                .values("page_path", "page_title")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )

            # Daily feedback counts (single aggregated query)
            daily_counts_qs = (
                UserFeedback.objects.filter(created_at__date__gte=start_date)
                .annotate(date=TruncDate("created_at"))
                .values("date")
                .annotate(count=Count("id"))
                .order_by("date")
            )
            daily_counts_map = {
                entry["date"]: entry["count"] for entry in daily_counts_qs
            }
            daily_stats = [
                {
                    "date": (start_date + timedelta(days=i)).isoformat(),
                    "count": daily_counts_map.get(start_date + timedelta(days=i), 0),
                }
                for i in range(days)
            ]

            return JsonResponse(
                {
                    "success": True,
                    "data": {
                        "total_feedback": total_feedback,
                        "date_range": {
                            "start": start_date.isoformat(),
                            "end": end_date.isoformat(),
                        },
                        "by_type": list(type_stats),
                        "by_status": list(status_stats),
                        "top_pages": list(page_stats),
                        "daily_counts": daily_stats,
                    },
                }
            )

        except (DatabaseError, ValueError):
            logger.exception("Error generating feedback statistics")
            return JsonResponse(
                {"success": False, "message": "Error generating statistics."},
                status=500,
            )
