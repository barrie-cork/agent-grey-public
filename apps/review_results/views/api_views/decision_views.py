"""Decision and notes API views for the review_results app.

AJAX/JSON endpoints for the single-reviewer review interface: include/exclude
decisions, bulk decisions, notes updates, session statistics, URL access
logging, and including filtered results.
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.views import View

from apps.core.utils.error_responses import error_response as make_error_response
from apps.review_manager.models import SearchSession
from apps.review_results.api_types import (
    BulkReviewDecisionResponse,
    ErrorResponse,
    NotesResponse,
    NotesUpdateResponse,
    ReviewDecisionResponse,
    SessionStatsResponse,
    URLAccessResponse,
    validate_bulk_review_input,
    validate_review_decision_input,
)
from apps.review_results.models import (
    ReviewerDecision,
    SimpleReviewDecision,
    URLAccessLog,
)
from apps.review_results.providers import get_results_provider
from apps.review_results.services.review_cache_manager import ReviewCacheManager
from apps.review_results.services.simple_review_progress_service import (
    SimpleReviewProgressService,
)
from apps.review_results.views.mixins import SessionOwnershipMixin

logger = logging.getLogger(__name__)


class MakeDecisionAPIView(LoginRequiredMixin, SessionOwnershipMixin, View):
    """
    AJAX endpoint for making Include/Exclude review decisions.

    This API handles the core manual review functionality where researchers
    make decisions about individual search results. Features:

    - Accept Include/Exclude decisions with validation
    - Support for structured exclusion reasons (no_access, not_relevant, etc.)
    -  notes and reviewer comments
    - Automatic result status updates
    - JSON response with success/error handling

    The endpoint enforces that exclusion decisions must include a valid
    exclusion reason to maintain PRISMA compliance and audit trail quality.
    """

    def post(self, request, session_id):
        """
        Process a review decision for a specific result.

        Validates the decision data, creates or updates the review decision,
        and marks the result as reviewed in the processing pipeline.

        Args:
            request: POST request with result_id, decision, exclusion_reason, notes
            session_id: UUID of the search session

        Returns:
            JsonResponse: Success status with decision details or error information
        """
        try:
            # Validate session ownership
            session: SearchSession = self.get_session()

            # Get input data
            input_data = {
                "result_id": request.POST.get("result_id", ""),
                "decision": request.POST.get("decision", ""),
                "exclusion_reason": request.POST.get("exclusion_reason", "") or None,
                "notes": request.POST.get("notes", "") or None,
            }

            # Validate input using new validation function
            validation = validate_review_decision_input(input_data)
            if not validation["is_valid"]:
                error_response: ErrorResponse = {
                    "success": False,
                    "error": "; ".join(validation["errors"]),
                    "details": None,
                }
                return JsonResponse(error_response, status=400)

            # Extract validated data
            result_id = input_data["result_id"]
            decision = input_data["decision"]
            exclusion_reason = input_data["exclusion_reason"]
            notes = input_data["notes"]

            # Get the result using provider
            results_provider = get_results_provider()
            result = results_provider.get_result_by_id(result_id, session.id)

            if not result:
                return JsonResponse(
                    {"success": False, "error": "Result not found or access denied"}
                )

            # Check if Workflow #2 (multi-reviewer independent screening)
            is_workflow_2 = (
                session.current_configuration
                and session.current_configuration.is_workflow_2
            )

            if not session.current_configuration:
                logger.warning(
                    "Session %s has no ReviewConfiguration; defaulting to WF1 path",
                    session.id,
                )

            if is_workflow_2:
                # Workflow #2: Update or create ReviewerDecision
                # During initial screening, update existing decision (version increments for audit)
                # New records only created during conflict resolution (is_revote=True)
                existing_decision = ReviewerDecision.objects.active_for(
                    result, request.user
                ).first()

                if existing_decision:
                    # Update existing decision (version auto-increments for audit trail)
                    existing_decision.decision = (
                        decision.upper()
                    )  # Model uses UPPERCASE
                    existing_decision.exclusion_reason = exclusion_reason or ""
                    existing_decision.notes = notes or ""
                    existing_decision.save(allow_update=True)
                    decision_obj = existing_decision
                    created = False
                else:
                    # Create new decision (first time for this result)
                    decision_obj = ReviewerDecision.objects.create(
                        result=result,
                        reviewer=request.user,
                        organisation=session.organisation,
                        decision=decision.upper(),  # Model uses UPPERCASE
                        exclusion_reason=exclusion_reason or "",
                        notes=notes or "",
                        is_revote=False,
                    )
                    created = True
            else:
                # Workflow #1: Create or update SimpleReviewDecision (mutable)
                decision_obj, created = SimpleReviewDecision.objects.get_or_create(
                    result=result,
                    defaults={
                        "session": session,
                        "reviewer": request.user,
                        "decision": decision,
                        "exclusion_reason": exclusion_reason or "",
                        "notes": notes or "",
                    },
                )

                if not created:
                    # Update existing decision
                    decision_obj.decision = decision
                    decision_obj.exclusion_reason = exclusion_reason or ""
                    decision_obj.notes = notes or ""
                    decision_obj.reviewer = request.user
                    decision_obj.save()

            # Update ProcessedResult status using provider
            results_provider.mark_result_as_reviewed(result.id)

            # Update review activity and invalidate cache (PRP: Activity-Based Monitoring)
            try:
                ReviewCacheManager.update_review_activity(str(session.id))
                ReviewCacheManager.invalidate_review_cache(str(session.id))
            except Exception as cache_error:
                logger.debug(f"Cache update failed: {cache_error}")

            response_data: ReviewDecisionResponse = {
                "success": True,
                "decision": decision,
                "result_id": str(result_id),
                "message": f"Result marked as {decision}",
            }
            return JsonResponse(response_data)

        except Exception as e:
            logger.error(
                "Decision save failed for session %s: %s",
                session_id,
                str(e),
                exc_info=True,
            )
            error_response: ErrorResponse = {
                "success": False,
                "error": "An internal error occurred",
                "details": None,
            }
            return JsonResponse(error_response, status=500)

    def dispatch(self, request, *args, **kwargs):
        """Handle the dispatch for both GET and POST."""
        if request.method == "POST":
            return self.post(request, kwargs.get("session_id"))
        return make_error_response(Exception("Method not allowed"), status_code=405)


class BulkDecisionAPIView(LoginRequiredMixin, SessionOwnershipMixin, View):
    """
    AJAX endpoint for bulk Include/Exclude review decisions.

    Allows processing multiple results with a single decision and reason.
    This improves workflow efficiency for researchers reviewing large sets
    of search results that can be excluded for the same reason.
    """

    def post(self, request, session_id):  # noqa: C901 - Bulk processing
        """
        Process bulk review decisions for multiple results.

        Args:
            request: POST request with result_ids[], decision, exclusion_reason, notes
            session_id: UUID of the search session

        Returns:
            JsonResponse: Success status with processed count or error information
        """
        try:
            session = self.get_session()
        except PermissionDenied:
            error_response: ErrorResponse = {
                "success": False,
                "error": "You don't have permission to access this session.",
                "details": None,
            }
            return JsonResponse(error_response, status=403)
        except Http404:
            error_response = {
                "success": False,
                "error": "Session not found.",
                "details": None,
            }
            return JsonResponse(error_response, status=404)

        try:
            # Get input data
            input_data = {
                "result_ids": request.POST.getlist("result_ids[]"),
                "decision": request.POST.get("decision", ""),
                "exclusion_reason": request.POST.get("exclusion_reason", "") or None,
                "notes": request.POST.get("notes", "") or None,
            }

            # Validate input using new validation function
            validation = validate_bulk_review_input(input_data)
            if not validation["is_valid"]:
                error_response = {
                    "success": False,
                    "error": "; ".join(validation["errors"]),
                    "details": None,
                }
                return JsonResponse(error_response, status=400)

            # Extract validated data
            result_ids = input_data["result_ids"]
            decision = input_data["decision"]
            exclusion_reason = input_data["exclusion_reason"]
            notes = input_data["notes"]

            # Get all results and verify ownership
            results_provider = get_results_provider()
            results = []
            for result_id in result_ids:
                result = results_provider.get_result_by_id(result_id, session.id)
                if result:
                    results.append(result)

            if len(results) != len(result_ids):
                error_response = {
                    "success": False,
                    "error": "Some results not found or access denied",
                    "details": None,
                }
                return JsonResponse(error_response, status=404)

            # Process in a transaction for data integrity
            from django.db import transaction

            # Check if Workflow #2 (multi-reviewer independent screening)
            is_workflow_2 = (
                session.current_configuration
                and session.current_configuration.is_workflow_2
            )

            with transaction.atomic():
                created_count = 0
                updated_count = 0

                for result in results:
                    if is_workflow_2:
                        # Workflow #2: Update or create ReviewerDecision
                        existing_decision = ReviewerDecision.objects.active_for(
                            result, request.user
                        ).first()

                        if existing_decision:
                            # Update existing decision (version auto-increments)
                            existing_decision.decision = (
                                decision.upper()
                            )  # Model uses UPPERCASE
                            existing_decision.exclusion_reason = exclusion_reason or ""
                            existing_decision.notes = notes or ""
                            existing_decision.save(allow_update=True)
                            updated_count += 1
                        else:
                            # Create new decision (first time)
                            ReviewerDecision.objects.create(
                                result=result,
                                reviewer=request.user,
                                organisation=session.organisation,
                                decision=decision.upper(),  # Model uses UPPERCASE
                                exclusion_reason=exclusion_reason or "",
                                notes=notes or "",
                                is_revote=False,
                            )
                            created_count += 1
                    else:
                        # Workflow #1: Create or update SimpleReviewDecision (mutable)
                        decision_obj, created = (
                            SimpleReviewDecision.objects.update_or_create(
                                result=result,
                                defaults={
                                    "session": session,
                                    "reviewer": request.user,
                                    "decision": decision,
                                    "exclusion_reason": exclusion_reason or "",
                                    "notes": notes or "",
                                },
                            )
                        )

                        if created:
                            created_count += 1
                        else:
                            updated_count += 1

                    # Mark as reviewed
                    results_provider.mark_result_as_reviewed(result.id)

            response_data: BulkReviewDecisionResponse = {
                "success": True,
                "decision": decision,
                "processed_count": len(results),
                "created": created_count,
                "updated": updated_count,
                "message": f"Bulk {decision} completed for {len(results)} results",
            }
            return JsonResponse(response_data)

        except Exception as e:
            logger.error("Bulk decision error: %s", str(e), exc_info=True)
            error_response = {
                "success": False,
                "error": "An internal error occurred",
                "details": None,
            }
            return JsonResponse(error_response, status=500)

    def dispatch(self, request, *args, **kwargs):
        """Handle POST requests only."""
        if request.method == "POST":
            return self.post(request, kwargs.get("session_id"))
        return make_error_response(Exception("Method not allowed"), status_code=405)


class UpdateNotesAPIView(LoginRequiredMixin, SessionOwnershipMixin, View):
    """
    AJAX endpoints for managing reviewer notes and annotations.

    This API provides note-taking functionality for the manual review process,
    allowing researchers to add contextual comments and annotations to results.
    Features:

    - GET: Retrieve existing notes for a result
    - POST: Save or update notes for a result
    - Automatic creation of review decision records when needed
    - Notes persist independently of Include/Exclude decisions
    - Support for rich text annotations and reviewer comments

    Notes are essential for maintaining research quality and enabling
    collaboration between multiple reviewers on the same dataset.
    """

    def get(self, request, session_id):
        """
        Retrieve existing notes for a specific result.

        Args:
            request: GET request with result_id parameter
            session_id: UUID of the search session

        Returns:
            JsonResponse: Notes content or empty string if none exist
        """
        try:
            session: SearchSession = self.get_session()
            result_id: str = request.GET.get("result_id")

            if not result_id:
                error_response: ErrorResponse = {
                    "success": False,
                    "error": "Missing result_id",
                    "details": None,
                }
                return JsonResponse(error_response, status=400)

            # Get result using provider
            results_provider = get_results_provider()
            result = results_provider.get_result_by_id(result_id, session.id)

            if not result:
                error_response: ErrorResponse = {
                    "success": False,
                    "error": "Result not found",
                    "details": None,
                }
                return JsonResponse(error_response, status=404)

            # Check if Workflow #2 (multi-reviewer independent screening)
            is_workflow_2 = (
                session.current_configuration
                and session.current_configuration.is_workflow_2
            )

            if is_workflow_2:
                # Workflow #2: Get current user's ReviewerDecision
                decision = ReviewerDecision.objects.active_for(
                    result, request.user
                ).first()
            else:
                # Workflow #1: Get shared SimpleReviewDecision
                decision = SimpleReviewDecision.objects.filter(result=result).first()

            notes = decision.notes if decision else ""

            response_data: NotesResponse = {"success": True, "notes": notes}
            return JsonResponse(response_data)

        except Exception as e:
            error_response: ErrorResponse = {
                "success": False,
                "error": str(e),
                "details": None,
            }
            return JsonResponse(error_response, status=500)

    def post(self, request, session_id):
        """
        Save or update notes for a specific result.

        Creates or updates the notes field in the review decision record.
        If no decision exists, creates a new one with default pending status.

        Args:
            request: POST request with result_id and notes parameters
            session_id: UUID of the search session

        Returns:
            JsonResponse: Success status and confirmation message
        """
        try:
            session: SearchSession = self.get_session()

            # Get input data
            input_data = {
                "result_id": request.POST.get("result_id", ""),
                "notes": request.POST.get("notes", ""),
            }

            # Validate input (only require result_id, notes can be empty for clearing)
            if not input_data["result_id"]:
                error_response: ErrorResponse = {
                    "success": False,
                    "error": "Result ID is required",
                    "details": None,
                }
                return JsonResponse(error_response, status=400)

            # Extract validated data
            result_id = input_data["result_id"]
            notes = input_data["notes"]

            # Get result using provider
            results_provider = get_results_provider()
            result = results_provider.get_result_by_id(result_id, session.id)

            if not result:
                error_response: ErrorResponse = {
                    "success": False,
                    "error": "Result not found",
                    "details": None,
                }
                return JsonResponse(error_response, status=404)

            # Check if Workflow #2 (multi-reviewer independent screening)
            is_workflow_2 = (
                session.current_configuration
                and session.current_configuration.is_workflow_2
            )

            if is_workflow_2:
                # Workflow #2: Update or create ReviewerDecision
                existing_decision = ReviewerDecision.objects.active_for(
                    result, request.user
                ).first()

                if existing_decision:
                    # Update existing decision's notes
                    # Note: For ReviewerDecision, we update notes in place
                    # (immutability applies to decision field, but notes can be updated)
                    existing_decision.notes = notes
                    existing_decision.save(allow_update=True)
                    created = False
                else:
                    # Create new decision with notes (default to maybe - pending state)
                    ReviewerDecision.objects.create(
                        result=result,
                        reviewer=request.user,
                        organisation=session.organisation,
                        decision="MAYBE",  # Model uses UPPERCASE, MAYBE for pending review
                        notes=notes,
                        is_revote=False,
                    )
                    created = True
            else:
                # Workflow #1: Create or update SimpleReviewDecision
                decision, created = SimpleReviewDecision.objects.get_or_create(
                    result=result,
                    defaults={
                        "session": session,
                        "reviewer": request.user,
                        "notes": notes,
                    },
                )

                if not created:
                    decision.notes = notes
                    decision.save(update_fields=["notes"])

            response_data: NotesUpdateResponse = {
                "success": True,
                "message": "Notes saved successfully",
            }
            return JsonResponse(response_data)

        except Exception as e:
            error_response: ErrorResponse = {
                "success": False,
                "error": str(e),
                "details": None,
            }
            return JsonResponse(error_response, status=500)

    def dispatch(self, request, *args, **kwargs):
        """Handle dispatch for both GET and POST."""
        session_id: str = kwargs.get("session_id") or ""
        if request.method == "GET":
            return self.get(request, session_id)
        if request.method == "POST":
            return self.post(request, session_id)
        return make_error_response(Exception("Method not allowed"), status_code=405)


class GetSessionStatsAPIView(LoginRequiredMixin, SessionOwnershipMixin, View):
    """
    AJAX endpoint for real-time review progress tracking.

    This API provides live updates on review completion status, enabling
    dynamic progress bars and completion tracking in the UI. Features:

    - Total results count and reviewed count
    - Percentage completion calculation
    - Breakdown by decision type (included/excluded/pending)
    - Progress metrics for PRISMA reporting
    - Real-time updates without page refresh

    Progress tracking helps researchers monitor their review workflow
    and estimate time to completion for large result sets.
    """

    def get(self, request, session_id):
        """
        Get current review progress statistics.

        Calculates and returns comprehensive progress metrics including
        total counts, percentages, and decision breakdowns.

        Args:
            request: GET request
            session_id: UUID of the search session

        Returns:
            JsonResponse: Progress data with counts and percentages
        """
        try:
            session: SearchSession = self.get_session()
            service: SimpleReviewProgressService = SimpleReviewProgressService()
            progress = service.get_progress_summary(
                str(session.id), session=session, user=request.user
            )

            response_data: SessionStatsResponse = {
                "success": True,
                "progress": progress,
            }
            return JsonResponse(response_data)

        except Exception as e:
            logger.error(
                "Session stats failed for session %s: %s",
                session_id,
                str(e),
                exc_info=True,
            )
            error_response: ErrorResponse = {
                "success": False,
                "error": str(e),
                "details": None,
            }
            return JsonResponse(error_response, status=500)

    def dispatch(self, request, *args, **kwargs):
        """Handle GET requests only."""
        if request.method == "GET":
            return self.get(request, kwargs.get("session_id"))
        return make_error_response(Exception("Method not allowed"), status_code=405)


class TrackURLAccessAPIView(LoginRequiredMixin, SessionOwnershipMixin, View):
    """
    Track URL access attempts for PRISMA compliance reporting.

    This API logs attempts to access result URLs, tracking both successful
    and failed access attempts. This data is essential for PRISMA flow diagrams
    and helps identify broken links or inaccessible content. Features:

    - Log successful URL access attempts
    - Track access failures with reason codes
    - Automatic exclusion of broken links
    - Integration with review decisions
    - Audit trail for PRISMA reporting

    URL access tracking helps maintain data quality and provides transparency
    about which results were actually accessible during the review process.
    """

    def post(self, request, session_id):
        """
        Log a URL access attempt with success/failure status.

        Records whether a reviewer was able to successfully access a result URL,
        with automatic handling of broken links and access failures.

        Args:
            request: POST request with result_id, success, and failure_reason
            session_id: UUID of the search session

        Returns:
            JsonResponse: Confirmation of access logging
        """
        try:
            session: SearchSession = self.get_session()

            # Get parameters
            result_id = request.POST.get("result_id")
            access_successful = request.POST.get("success", "true") == "true"
            failure_reason = request.POST.get("failure_reason", "")

            if not result_id:
                error_response: ErrorResponse = {
                    "success": False,
                    "error": "Result ID is required",
                    "details": None,
                }
                return JsonResponse(error_response, status=400)

            # Get result using provider
            results_provider = get_results_provider()
            result = results_provider.get_result_by_id(result_id, session.id)

            if not result:
                error_response: ErrorResponse = {
                    "success": False,
                    "error": "Result not found",
                    "details": None,
                }
                return JsonResponse(error_response, status=404)

            # Create or update URLAccessLog
            access_log, created = URLAccessLog.objects.get_or_create(
                result=result,
                user=request.user,
                defaults={
                    "session": session,
                    "access_successful": access_successful,
                    "failure_reason": failure_reason if not access_successful else "",
                },
            )

            # Update if exists and access failed
            if not created and not access_successful:
                access_log.access_successful = False
                access_log.failure_reason = failure_reason
                access_log.save()

            # Mark result as retrieved for PRISMA reporting (regardless of success/failure)
            if not result.is_retrieved:
                from django.utils import timezone

                result.is_retrieved = True
                result.retrieved_at = timezone.now()
                result.save(update_fields=["is_retrieved", "retrieved_at"])

            # If marking as broken link, update review decision
            if not access_successful and failure_reason == "broken_link":
                decision, _ = SimpleReviewDecision.objects.get_or_create(
                    result=result,
                    defaults={
                        "session": session,
                        "reviewer": request.user,
                        "decision": "exclude",
                        "exclusion_reason": "no_access",
                        "notes": "URL is broken or inaccessible",
                    },
                )

            response_data: URLAccessResponse = {
                "success": True,
                "message": "URL access tracked",
                "created": created,
            }
            return JsonResponse(response_data)

        except Exception as e:
            error_response: ErrorResponse = {
                "success": False,
                "error": str(e),
                "details": None,
            }
            return JsonResponse(error_response, status=500)

    def dispatch(self, request, *args, **kwargs):
        """Handle POST requests only."""
        if request.method == "POST":
            return self.post(request, kwargs.get("session_id"))
        return make_error_response(Exception("Method not allowed"), status_code=405)


class IncludeFilteredResultAPIView(LoginRequiredMixin, SessionOwnershipMixin, View):
    """
    AJAX endpoint for including filtered results back into the review process.

    This API allows users to recover results that were filtered during processing
    (duplicates, errors) and add them back to their review queue. This implements
    the "Include Anyway" functionality from Issue #100 transparency features.
    """

    def post(self, request, session_id):
        """
        Include a filtered result back into the review process.

        Changes the processing_status from 'filtered' or 'error' to 'success'
        and makes the result available in the main review interface.

        Args:
            request: POST request with result_id parameter
            session_id: UUID of the search session

        Returns:
            JsonResponse: Success status and confirmation message
        """
        try:
            session = self.get_session()
            result_id = request.POST.get("result_id")

            if not result_id:
                error_response: ErrorResponse = {
                    "success": False,
                    "error": "Result ID is required",
                    "details": None,
                }
                return JsonResponse(error_response, status=400)

            # Get the filtered result
            from apps.results_manager.models import ProcessedResult

            try:
                result = ProcessedResult.objects.get(
                    id=result_id,
                    session=session,
                    processing_status__in=["filtered", "error"],
                )
            except ProcessedResult.DoesNotExist:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Filtered result not found or not accessible",
                    },
                    status=404,
                )

            # Change status to success and clear error details
            old_status = result.processing_status
            result.processing_status = "success"
            result.processing_error_category = ""
            result.processing_error_message = (
                f"Previously {old_status}, included manually by user"
            )
            result.save(
                update_fields=[
                    "processing_status",
                    "processing_error_category",
                    "processing_error_message",
                ]
            )

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Result recovered from {old_status} status and added to review queue",
                    "result_id": str(result_id),
                    "old_status": old_status,
                }
            )

        except Exception as e:
            logger.error(f"Include filtered result error: {str(e)}")
            return JsonResponse(
                {"success": False, "error": "An internal error occurred"}, status=500
            )

    def dispatch(self, request, *args, **kwargs):
        """Handle POST requests only."""
        if request.method == "POST":
            return self.post(request, kwargs.get("session_id"))
        return make_error_response(Exception("Method not allowed"), status_code=405)


# Dual Screening API Endpoints (Phase D - Multi-Reviewer Workflows)
