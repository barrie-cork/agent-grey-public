"""Work-queue and dual-screening API views for the review_results app.

AJAX/JSON endpoints for the multi-reviewer screening workflow: atomic claiming
of the next result, submitting and skipping decisions, and per-reviewer
progress tracking.
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from apps.core.utils.error_responses import error_response as make_error_response
from apps.organisation.models import OrganisationMembership

logger = logging.getLogger(__name__)


class ClaimNextResultAPIView(LoginRequiredMixin, View):
    """
    API endpoint for claiming the next available result in dual screening workflow.

    This implements first-come, first-served result assignment using
    ReviewClaimService.claim_next_result() with SELECT FOR UPDATE SKIP LOCKED
    to prevent race conditions.

    POST /api/screening/claim-next/
    Request Body (optional):
        {
            "session_id": "uuid"  # Optional: scope to specific session
        }

    Response:
        {
            "success": true,
            "result": {
                "id": "uuid",
                "title": "...",
                "snippet": "...",
                "url": "...",
                ... other ProcessedResult fields
            },
            "assignment_role": "PRIMARY|SECONDARY|ARBITRATOR"
        }

    Error Response (no results available):
        {
            "success": false,
            "error": "No results available for review",
            "code": "NO_RESULTS_AVAILABLE"
        }
    """

    def post(self, request):
        """Claim next available result for dual screening."""
        try:
            from apps.review_results.services.review_claim_service import (
                ReviewClaimService,
            )

            # Get organisation from user's first membership
            membership = OrganisationMembership.objects.filter(
                user=request.user
            ).first()
            organisation = membership.organisation if membership else None

            if not organisation:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "User must belong to an organisation",
                        "code": "NO_ORGANISATION",
                    },
                    status=400,
                )

            # Get optional session_id from request body
            import json

            try:
                body = json.loads(request.body) if request.body else {}
                session_id = body.get("session_id")
            except json.JSONDecodeError:
                session_id = None

            # Use ReviewClaimService to claim next result
            service = ReviewClaimService()
            result = service.claim_next_result(
                reviewer=request.user, organisation=organisation, session_id=session_id
            )

            if not result:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "No results available for review",
                        "code": "NO_RESULTS_AVAILABLE",
                    },
                    status=404,
                )

            # Get the assignment to return the role
            from apps.review_results.models import ReviewerAssignment

            assignment = ReviewerAssignment.objects.filter(
                result=result, reviewer=request.user, is_active=True
            ).first()

            # Serialise result
            result_data = {
                "id": str(result.id),
                "title": result.title,
                "snippet": result.snippet,
                "url": result.url,
                "source_organization": result.source_organization,
                "domain": result.domain,
                "created_at": result.created_at.isoformat(),
                "session_id": str(result.session_id),
            }

            return JsonResponse(
                {
                    "success": True,
                    "result": result_data,
                    "assignment_role": assignment.role if assignment else "PRIMARY",
                    "message": "Result claimed successfully",
                }
            )

        except Exception as e:
            logger.error(f"Claim next result error: {str(e)}")
            return JsonResponse(
                {
                    "success": False,
                    "error": "An internal error occurred",
                    "code": "SERVER_ERROR",
                },
                status=500,
            )

    def dispatch(self, request, *args, **kwargs):
        """Handle POST requests only."""
        if request.method == "POST":
            return self.post(request)
        return make_error_response(Exception("Method not allowed"), status_code=405)


class SubmitDecisionAPIView(LoginRequiredMixin, View):
    """
    API endpoint for submitting a review decision in dual screening workflow.

    This implements decision submission with automatic conflict detection using
    ReviewCoordinationService.submit_reviewer_decision().

    POST /api/screening/submit-decision/
    Request Body:
        {
            "result_id": "uuid",
            "decision": "INCLUDE|EXCLUDE|MAYBE|ABSTAIN",
            "exclusion_reason": "optional",
            "confidence_level": 1-3,
            "notes": "optional",
            "screening_stage": "SCREENING",  # optional, defaults to SCREENING
            "time_spent_seconds": int  # optional
        }

    Response:
        {
            "success": true,
            "decision": {
                "id": "uuid",
                "decision": "INCLUDE",
                "created_at": "...",
                ...
            },
            "conflict_detected": false,
            "consensus_reached": true,
            "reviewers_completed": 2,
            "min_reviewers_required": 2
        }
    """

    def post(self, request):
        """Submit review decision with conflict detection."""
        try:
            import json

            from apps.review_results.services.review_coordination_service import (
                ReviewCoordinationService,
            )

            # Parse request body
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse(
                    {"success": False, "error": "Invalid JSON in request body"},
                    status=400,
                )

            # Validate required fields
            result_id = body.get("result_id")
            decision = body.get("decision")

            if not result_id:
                return JsonResponse(
                    {"success": False, "error": "result_id is required"}, status=400
                )

            if not decision:
                return JsonResponse(
                    {"success": False, "error": "decision is required"}, status=400
                )

            if decision not in ["INCLUDE", "EXCLUDE", "MAYBE", "ABSTAIN"]:
                return JsonResponse(
                    {"success": False, "error": f"Invalid decision value: {decision}"},
                    status=400,
                )

            # Validate exclusion_reason if decision is EXCLUDE
            if decision == "EXCLUDE" and not body.get("exclusion_reason"):
                return JsonResponse(
                    {
                        "success": False,
                        "error": "exclusion_reason is required for EXCLUDE decisions",
                    },
                    status=400,
                )

            # Get organisation from user's first membership
            membership = OrganisationMembership.objects.filter(
                user=request.user
            ).first()
            organisation = membership.organisation if membership else None

            if not organisation:
                return JsonResponse(
                    {"success": False, "error": "User must belong to an organisation"},
                    status=400,
                )

            # Prepare decision data
            decision_data = {
                "decision": decision,
                "exclusion_reason": body.get("exclusion_reason", ""),
                "confidence_level": body.get("confidence_level", 2),
                "notes": body.get("notes", ""),
                "screening_stage": body.get("screening_stage", "SCREENING"),
                "time_spent_seconds": body.get("time_spent_seconds"),
            }

            # Submit decision using ReviewCoordinationService
            service = ReviewCoordinationService()
            decision_obj = service.submit_reviewer_decision(
                result_id=result_id,
                reviewer=request.user,
                decision_data=decision_data,
                organisation=organisation,
            )

            # Get updated result to check conflict status
            from apps.results_manager.models import ProcessedResult

            result = ProcessedResult.objects.get(id=result_id)

            # Check if conflict was detected
            from apps.review_results.models import ConflictResolution

            conflict_exists = ConflictResolution.objects.filter(
                result=result, status="PENDING"
            ).exists()

            # Serialise decision
            decision_response = {
                "id": str(decision_obj.id),
                "decision": decision_obj.decision,
                "exclusion_reason": decision_obj.exclusion_reason,
                "confidence_level": decision_obj.confidence_level,
                "notes": decision_obj.notes,
                "screening_stage": decision_obj.screening_stage,
                "decided_at": decision_obj.decided_at.isoformat(),
            }

            return JsonResponse(
                {
                    "success": True,
                    "decision": decision_response,
                    "conflict_detected": conflict_exists,
                    "consensus_reached": result.consensus_reached,
                    "reviewers_completed": result.reviewers_completed,
                    "min_reviewers_required": result.min_reviewers_required,
                    "message": "Decision submitted successfully",
                }
            )

        except ValueError as e:
            # Handle validation errors from service
            return JsonResponse({"success": False, "error": str(e)}, status=400)
        except Exception as e:
            logger.error(f"Submit decision error: {str(e)}")
            return JsonResponse(
                {"success": False, "error": "An internal error occurred"}, status=500
            )

    def dispatch(self, request, *args, **kwargs):
        """Handle POST requests only."""
        if request.method == "POST":
            return self.post(request)
        return make_error_response(Exception("Method not allowed"), status_code=405)


class SkipResultAPIView(LoginRequiredMixin, View):
    """
    API endpoint for skipping a claimed result in dual screening workflow.

    POST /api/screening/skip-result/
    Request Body:
        {
            "result_id": "uuid",
            "skip_reason": "optional"
        }

    Response:
        {
            "success": true,
            "message": "Result skipped successfully",
            "next_result": {
                ... result data or null
            }
        }
    """

    def post(self, request):
        """Skip a claimed result and optionally claim next."""
        try:
            import json

            from apps.review_results.models import ResultSkip
            from apps.review_results.services.review_claim_service import (
                ReviewClaimService,
            )

            # Parse request body
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse(
                    {"success": False, "error": "Invalid JSON in request body"},
                    status=400,
                )

            result_id = body.get("result_id")
            skip_reason = body.get("skip_reason", "")

            if not result_id:
                return JsonResponse(
                    {"success": False, "error": "result_id is required"}, status=400
                )

            # Get organisation from user's first membership
            membership = OrganisationMembership.objects.filter(
                user=request.user
            ).first()
            organisation = membership.organisation if membership else None

            if not organisation:
                return JsonResponse(
                    {"success": False, "error": "User must belong to an organisation"},
                    status=400,
                )

            # Get result
            from apps.results_manager.models import ProcessedResult

            try:
                result = ProcessedResult.objects.get(id=result_id)
            except ProcessedResult.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Result not found"}, status=404
                )

            # Create skip record
            ResultSkip.objects.create(
                organisation=organisation,
                result=result,
                reviewer=request.user,
                reason=skip_reason,
            )

            # Release the claim
            service = ReviewClaimService()
            service.release_claim(
                result_id=result_id, reviewer=request.user, organisation=organisation
            )

            # Try to claim next result
            next_result = service.claim_next_result(
                reviewer=request.user,
                organisation=organisation,
                session_id=str(result.session_id),
            )

            next_result_data = None
            if next_result:
                next_result_data = {
                    "id": str(next_result.id),
                    "title": next_result.title,
                    "snippet": next_result.snippet,
                    "url": next_result.url,
                    "source_organization": next_result.source_organization,
                    "domain": next_result.domain,
                }

            return JsonResponse(
                {
                    "success": True,
                    "message": "Result skipped successfully",
                    "next_result": next_result_data,
                }
            )

        except Exception as e:
            logger.error(f"Skip result error: {str(e)}")
            return JsonResponse(
                {"success": False, "error": "An internal error occurred"}, status=500
            )

    def dispatch(self, request, *args, **kwargs):
        """Handle POST requests only."""
        if request.method == "POST":
            return self.post(request)
        return make_error_response(Exception("Method not allowed"), status_code=405)


class ReviewProgressAPIView(LoginRequiredMixin, View):
    """
    API endpoint for getting review progress statistics for dual screening.

    GET /api/screening/progress/<session_id>/

    Response:
        {
            "success": true,
            "progress": {
                "total_results": int,
                "reviewed_by_user": int,
                "pending": int,
                "conflicts": int,
                "my_assignments": [...]
            }
        }
    """

    def get(self, request, session_id):
        """Get review progress for session."""
        try:
            from apps.review_manager.models import SearchSession
            from apps.review_results.models import (
                ConflictResolution,
                ReviewerAssignment,
                ReviewerDecision,
            )

            # Get session
            try:
                session = SearchSession.objects.get(id=session_id)
            except SearchSession.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Session not found"}, status=404
                )

            # Check permissions (user must be reviewer or session owner)
            user_membership = OrganisationMembership.objects.filter(
                user=request.user
            ).first()
            user_org = user_membership.organisation if user_membership else None
            if request.user != session.owner and user_org != session.organisation:
                return JsonResponse(
                    {"success": False, "error": "Permission denied"}, status=403
                )

            # Get total results for session
            from apps.results_manager.models import ProcessedResult

            total_results = ProcessedResult.objects.filter(session=session).count()

            # Get results reviewed by current user
            reviewed_by_user = (
                ReviewerDecision.objects.filter(
                    result__session=session, reviewer=request.user
                )
                .values("result")
                .distinct()
                .count()
            )

            # Get pending results (not enough reviewers)
            from django.db.models import F

            pending = ProcessedResult.objects.filter(
                session=session, reviewers_completed__lt=F("min_reviewers_required")
            ).count()

            # Get conflicts
            conflicts = ConflictResolution.objects.filter(
                result__session=session, status="PENDING"
            ).count()

            # Get user's active assignments
            my_assignments = (
                ReviewerAssignment.objects.filter(
                    result__session=session, reviewer=request.user, is_active=True
                )
                .select_related("result")
                .values("id", "result__id", "result__title", "role", "assigned_at")[:10]
            )  # Limit to 10 most recent

            my_assignments_list = [
                {
                    "assignment_id": str(a["id"]),
                    "result_id": str(a["result__id"]),
                    "result_title": a["result__title"],
                    "role": a["role"],
                    "assigned_at": a["assigned_at"].isoformat(),
                }
                for a in my_assignments
            ]

            return JsonResponse(
                {
                    "success": True,
                    "progress": {
                        "total_results": total_results,
                        "reviewed_by_user": reviewed_by_user,
                        "pending": pending,
                        "conflicts": conflicts,
                        "my_assignments": my_assignments_list,
                        "completion_percentage": round(
                            (total_results - pending) / total_results * 100
                            if total_results > 0
                            else 0,
                            2,
                        ),
                    },
                }
            )

        except Exception as e:
            logger.error(f"Review progress error: {str(e)}")
            return JsonResponse(
                {"success": False, "error": "An internal error occurred"}, status=500
            )

    def dispatch(self, request, *args, **kwargs):
        """Handle GET requests only."""
        if request.method == "GET":
            return self.get(request, kwargs.get("session_id"))
        return make_error_response(Exception("Method not allowed"), status_code=405)


# Conflict Discussion API Endpoints (Phase 05 - Vue SPA Consensus Discussion)
