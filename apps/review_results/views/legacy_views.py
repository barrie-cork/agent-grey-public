"""
Function-based views for the review_results app.

This module contains function-based views for backward compatibility
and views that need to remain as functions for URL routing or other
legacy requirements.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SessionActivity

from ..providers import get_session_provider
from .api_views import (
    BulkDecisionAPIView,
    GetSessionStatsAPIView,
    IncludeFilteredResultAPIView,
    MakeDecisionAPIView,
    TrackURLAccessAPIView,
    UpdateNotesAPIView,
)
from .review_views import ResultsReviewView


# Function-based views for URL routing
def results_review_view(request, session_id):
    """Function wrapper for ResultsReviewView."""
    view = ResultsReviewView.as_view()
    return view(request, session_id=session_id)


@login_required
def make_decision_api(request, session_id):
    """Function wrapper for MakeDecisionAPIView."""
    view = MakeDecisionAPIView()
    view.request = request
    view.kwargs = {"session_id": session_id}
    return view.dispatch(request, session_id=session_id)


@login_required
def bulk_decision_api(request, session_id):
    """Function wrapper for BulkDecisionAPIView."""
    view = BulkDecisionAPIView()
    view.request = request
    view.kwargs = {"session_id": session_id}
    return view.dispatch(request, session_id=session_id)


@login_required
def notes_api(request, session_id):
    """Function wrapper for UpdateNotesAPIView."""
    view = UpdateNotesAPIView()
    view.request = request
    view.kwargs = {"session_id": session_id}
    return view.dispatch(request, session_id=session_id)


@login_required
def progress_api(request, session_id):
    """Function wrapper for GetSessionStatsAPIView."""
    view = GetSessionStatsAPIView()
    view.request = request
    view.kwargs = {"session_id": session_id}
    return view.dispatch(request, session_id=session_id)


@login_required
def track_url_access(request, session_id):
    """Function wrapper for TrackURLAccessAPIView."""
    view = TrackURLAccessAPIView()
    view.request = request
    view.kwargs = {"session_id": session_id}
    return view.dispatch(request, session_id=session_id)


@login_required
def include_filtered_result_api(request, session_id):
    """Function wrapper for IncludeFilteredResultAPIView."""
    view = IncludeFilteredResultAPIView()
    view.request = request
    view.kwargs = {"session_id": session_id}
    return view.dispatch(request, session_id=session_id)


@login_required
@require_http_methods(["POST"])
def complete_review_view(request, session_id):
    """
    Mark manual review as complete and transition to reporting phase.

    This function handles the final step of the manual review workflow,
    transitioning the session from 'under_review' to 'completed' status
    and redirecting to the reporting dashboard for PRISMA report generation.

    The completion process validates that the session is in a reviewable state
    and updates the workflow status to enable report generation features.

    Args:
        request: POST request from authenticated user
        session_id: UUID of the search session to complete

    Returns:
        HttpResponse: Redirect to reporting dashboard or back to review
                     with appropriate success/error messages
    """
    try:
        # Get session and verify ownership using provider
        session_provider = get_session_provider()
        session = session_provider.get_session(session_id)

        if not session:
            raise Http404("Session not found")

        if session.owner != request.user:
            raise PermissionDenied("You don't have permission to access this session.")

        # Check if session is in a reviewable state
        if session.status not in ["ready_for_review", "under_review"]:
            messages.error(request, "This session is not in a reviewable state.")
            return redirect("review_results:overview", session_id=session_id)

        # Check if all invited reviewers have completed their work
        from apps.results_manager.models import ProcessedResult
        from apps.review_manager.models import ReviewInvitation
        from apps.review_results.models import (
            ConflictResolution,
            ReviewerDecision,
            SimpleReviewDecision,
        )

        # Phase 08: Check for unresolved conflicts (dual-screening workflow)
        unresolved_conflicts = ConflictResolution.objects.filter(
            result__session=session, status="PENDING"
        ).count()

        if unresolved_conflicts > 0:
            messages.error(
                request,
                f"Cannot complete review: {unresolved_conflicts} unresolved conflict(s) remain. "
                "Please resolve all conflicts before completing the session.",
            )
            return redirect("review_results:overview", session_id=session_id)

        # Check for any pending or accepted invitations
        pending_invitations = ReviewInvitation.objects.filter(
            session=session, status=ReviewInvitation.STATUS_PENDING
        )

        if pending_invitations.exists():
            # Block completion if there are pending invitations
            pending_emails = ", ".join(
                [inv.invitee_email for inv in pending_invitations]
            )
            messages.error(
                request,
                f"Cannot complete review. The following reviewers have not yet accepted their invitations: {pending_emails}. "
                "Please wait for them to accept, or revoke their invitations before proceeding to reporting.",
            )
            return redirect("review_results:overview", session_id=session_id)

        # Check if accepted reviewers have completed all results
        pending_reviewers = []
        accepted_invitations = ReviewInvitation.objects.filter(
            session=session, status=ReviewInvitation.STATUS_ACCEPTED
        ).select_related("invitee")

        if accepted_invitations.exists():
            # Get all results for this session
            total_results = ProcessedResult.objects.filter(session=session).count()

            for invitation in accepted_invitations:
                if invitation.invitee:
                    # Count how many results this reviewer has reviewed
                    # Check both ReviewerDecision (dual-screening) and SimpleReviewDecision (single-screening)
                    reviewer_decision_count = (
                        ReviewerDecision.objects.filter(
                            result__session=session, reviewer=invitation.invitee
                        )
                        .values("result")
                        .distinct()
                        .count()
                    )

                    simple_decision_count = SimpleReviewDecision.objects.filter(
                        session=session, reviewer=invitation.invitee
                    ).count()

                    reviewed_count = max(reviewer_decision_count, simple_decision_count)

                    if reviewed_count < total_results:
                        pending_reviewers.append(
                            {
                                "email": invitation.invitee.email,
                                "reviewed": reviewed_count,
                                "total": total_results,
                            }
                        )

        if pending_reviewers:
            # Build error message listing pending reviewers
            reviewer_details = ", ".join(
                [
                    f"{r['email']} ({r['reviewed']}/{r['total']} results)"
                    for r in pending_reviewers
                ]
            )
            messages.error(
                request,
                f"Cannot complete review. The following invited reviewers have not finished: {reviewer_details}. "
                "Please wait for all reviewers to complete their work before proceeding to reporting.",
            )
            return redirect("review_results:overview", session_id=session_id)

        # Check for hidden results and warn user
        hidden_count = ProcessedResult.objects.filter(
            session=session, is_hidden=True
        ).count()
        if hidden_count > 0 and not request.POST.get("confirm_hidden"):
            # Get which iterations have hidden results
            hidden_rounds = list(
                ProcessedResult.objects.filter(session=session, is_hidden=True)
                .values_list("execution_round", flat=True)
                .distinct()
            )
            return JsonResponse(
                {
                    "status": "confirm_required",
                    "message": (
                        f"{hidden_count} results from iteration(s) "
                        f"{', '.join(str(r) for r in sorted(hidden_rounds))} "
                        "are hidden and will not be counted in the final report. "
                        "Continue?"
                    ),
                    "hidden_count": hidden_count,
                    "hidden_iterations": sorted(hidden_rounds),
                }
            )

        # Update session status to completed using provider
        session_provider.update_session_status(session.id, "completed")

        # Log the completion
        messages.success(
            request, "Review completed successfully! You can now generate reports."
        )

        # Redirect to reporting dashboard
        return redirect("reporting:dashboard", session_id=session_id)

    except Exception as e:
        messages.error(request, f"An error occurred: {str(e)}")
        return redirect("review_results:overview", session_id=session_id)


@login_required
@require_http_methods(["POST"])
def mark_reviewer_complete(request, session_id):
    """
    Mark the current reviewer's work as complete for dual-screening workflow.

    This endpoint is called by invited reviewers when they finish reviewing
    all results assigned to them. Updates the ReviewerCompletion record and
    triggers conflict detection if all reviewers have completed their work.

    Args:
        request: POST request from authenticated reviewer
        session_id: UUID of the search session

    Returns:
        JsonResponse with status:
            - 'success': Reviewer marked complete, all reviewers done, conflicts detected
            - 'waiting': Reviewer marked complete, waiting for others
            - 'error': An error occurred (with message)

    Expected by: results_overview.html (line ~883)
    Related to: Issue #35 (dual-screening workflow)
    """
    try:
        import logging

        from apps.review_manager.models import ReviewInvitation
        from apps.review_results.models import ReviewerCompletion, ReviewerDecision
        from apps.review_results.services.review_coordination_service import (
            ReviewCoordinationService,
        )

        logger = logging.getLogger(__name__)
        logger.info(
            f"mark_reviewer_complete called by user: {request.user.username if request.user.is_authenticated else 'anonymous'}"
        )

        # Get session and verify access
        session_provider = get_session_provider()
        session = session_provider.get_session(session_id)
        logger.info(f"Session found: {session.id if session else 'None'}")

        if not session:
            return JsonResponse(
                {"status": "error", "message": "Session not found"}, status=404
            )

        # Check if user has access to this session
        # They must be either the owner or an invited reviewer
        is_owner = session.owner == request.user
        has_invitation = ReviewInvitation.objects.filter(
            session=session,
            invitee=request.user,
            status=ReviewInvitation.STATUS_ACCEPTED,
        ).exists()

        if not (is_owner or has_invitation):
            return JsonResponse(
                {
                    "status": "error",
                    "message": "You do not have permission to access this session",
                },
                status=403,
            )

        # Find the ReviewerCompletion record for this user
        try:
            completion = ReviewerCompletion.objects.get(
                session=session, reviewer=request.user
            )
        except ReviewerCompletion.DoesNotExist:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "No completion record found. Your session may not be using dual-screening workflow.",
                },
                status=400,
            )

        # Sync total_results from live query, not denormalised field (#82)
        live_total = ProcessedResult.objects.filter(
            session=session,
            processing_status="success",
            is_hidden=False,
        ).count()
        if completion.total_results != live_total:
            ReviewerCompletion.objects.filter(session=session).update(
                total_results=live_total
            )

        # Sync reviewed_results from live decision counts for ALL reviewers (#82, #129)
        all_completions_qs = ReviewerCompletion.objects.filter(
            session=session
        ).select_related("reviewer")
        for comp in all_completions_qs:
            live_reviewed = (
                ReviewerDecision.objects.filter(
                    result__session=session,
                    result__processing_status="success",
                    result__is_hidden=False,
                    reviewer=comp.reviewer,
                    is_revote=False,
                )
                .values("result")
                .distinct()
                .count()
            )
            if comp.reviewed_results != live_reviewed:
                comp.reviewed_results = live_reviewed
                comp.save(update_fields=["reviewed_results", "updated_at"])

        completion.refresh_from_db()

        # Check if already completed
        if completion.completed_at:
            # Still need to return progress array for JavaScript
            all_completions = ReviewerCompletion.objects.filter(
                session=session
            ).select_related("reviewer")
            progress = []
            for comp in all_completions:
                progress.append(
                    {
                        "reviewer": comp.reviewer.username,
                        "reviewed": comp.reviewed_results,
                        "total": comp.total_results,
                        "complete": comp.completed_at is not None,
                    }
                )

            return JsonResponse(
                {
                    "status": "waiting",
                    "message": "You have already marked your review as complete.",
                    "progress": progress,
                }
            )

        # Mark as complete
        completion.completed_at = timezone.now()
        completion.save(update_fields=["completed_at", "updated_at"])

        # Check if all reviewers have completed
        all_completions = ReviewerCompletion.objects.filter(
            session=session
        ).select_related("reviewer")
        total_reviewers = all_completions.count()
        completed_reviewers = all_completions.filter(completed_at__isnull=False).count()

        # Build progress array for JavaScript
        progress = []
        for comp in all_completions:
            progress.append(
                {
                    "reviewer": comp.reviewer.username,
                    "reviewed": comp.reviewed_results,
                    "total": comp.total_results,
                    "complete": comp.completed_at is not None,
                }
            )

        all_complete = completed_reviewers == total_reviewers

        if all_complete:
            # Trigger IRR calculation in background (#80)
            from apps.review_results.tasks import calculate_session_irr_task

            calculate_session_irr_task.delay(session_id=str(session.id))

            # Trigger conflict detection
            try:
                coordination_service = ReviewCoordinationService()
                conflicts = coordination_service.detect_conflicts(session)

                return JsonResponse(
                    {
                        "status": "complete",
                        "message": f"All reviewers have completed. {len(conflicts)} conflict(s) detected.",
                        "conflicts_count": len(conflicts),
                        "redirect_url": reverse(
                            "review_results:overview", args=[session.id]
                        ),
                    }
                )
            except Exception as e:
                # Log but don't fail - conflict detection can happen later
                return JsonResponse(
                    {
                        "status": "complete",
                        "message": "Review marked complete. Conflict detection will run shortly.",
                        "conflicts_count": 0,
                        "redirect_url": reverse(
                            "review_results:overview", args=[session.id]
                        ),
                        "detection_error": str(e),
                    }
                )
        else:
            # Still waiting for other reviewers
            return JsonResponse(
                {
                    "status": "waiting",
                    "message": f"Your review is marked complete. Waiting for {total_reviewers - completed_reviewers} more reviewer(s).",
                    "progress": progress,
                    "completed_reviewers": completed_reviewers,
                    "total_reviewers": total_reviewers,
                }
            )

    except Exception as e:
        import logging
        import traceback

        logger = logging.getLogger(__name__)
        logger.error(f"mark_reviewer_complete error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

        return JsonResponse(
            {"status": "error", "message": f"An error occurred: {str(e)}"}, status=500
        )


@login_required
@require_http_methods(["POST"])
def hide_iteration_results(request, session_id, execution_round):
    """Hide all results from a specific execution round.

    Args:
        request: POST request from authenticated user.
        session_id: UUID of the search session.
        execution_round: Integer execution round to hide.

    Returns:
        JsonResponse with count of hidden results.
    """
    session_provider = get_session_provider()
    session = session_provider.get_session(session_id)

    if not session:
        return JsonResponse({"error": "Session not found"}, status=404)

    if session.owner != request.user:
        return JsonResponse({"error": "Permission denied"}, status=403)

    reason = f"Excluded: iteration {execution_round} results hidden by user"
    updated = ProcessedResult.objects.filter(
        session=session,
        execution_round=execution_round,
        is_hidden=False,
    ).update(is_hidden=True, hidden_reason=reason)

    SessionActivity.log_activity(
        session=session,
        activity_type="results_hidden",
        description=f"Hidden {updated} results from iteration {execution_round}",
        user=request.user,
        metadata={
            "execution_round": execution_round,
            "results_hidden": updated,
        },
    )

    return JsonResponse({"status": "success", "results_hidden": updated})


@login_required
@require_http_methods(["POST"])
def unhide_iteration_results(request, session_id, execution_round):
    """Unhide all results from a specific execution round.

    Args:
        request: POST request from authenticated user.
        session_id: UUID of the search session.
        execution_round: Integer execution round to unhide.

    Returns:
        JsonResponse with count of unhidden results.
    """
    session_provider = get_session_provider()
    session = session_provider.get_session(session_id)

    if not session:
        return JsonResponse({"error": "Session not found"}, status=404)

    if session.owner != request.user:
        return JsonResponse({"error": "Permission denied"}, status=403)

    updated = ProcessedResult.objects.filter(
        session=session,
        execution_round=execution_round,
        is_hidden=True,
    ).update(is_hidden=False, hidden_reason="")

    SessionActivity.log_activity(
        session=session,
        activity_type="results_unhidden",
        description=f"Unhidden {updated} results from iteration {execution_round}",
        user=request.user,
        metadata={
            "execution_round": execution_round,
            "results_unhidden": updated,
        },
    )

    return JsonResponse({"status": "success", "results_unhidden": updated})
