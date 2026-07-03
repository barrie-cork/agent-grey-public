"""
Core API Views for Dual Screening.

Provides 6 core endpoints:
1. POST /api/results/claim/ - Claim next available result
2. POST /api/results/{id}/decide/ - Submit screening decision
3. POST /api/results/{id}/release/ - Release claimed result
4. GET /api/results/{id}/ - Get result details
5. GET /api/results/queue/ - View work queue
6. GET /api/sessions/{id}/blinding/ - Get blinding status

All session-scoped endpoints use session-first access control via
``get_validated_session`` / ``get_validated_result`` so that cross-org
reviewers (invited to a session in another org) can operate correctly.
"""

from typing import cast

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_results.api.utils import get_validated_result, get_validated_session
from apps.review_results.models import ReviewerAssignment
from apps.review_results.serializers import (
    ClaimResultInputSerializer,
    ManualResultInputSerializer,
    ProcessedResultSerializer,
    ReviewerDecisionInputSerializer,
    ReviewerDecisionOutputSerializer,
)
from apps.review_results.services.blinding_service import BlindingService
from apps.review_results.services.manual_result_service import ManualResultService
from apps.review_results.services.review_claim_service import ReviewClaimService
from apps.review_results.services.review_coordination_service import (
    ReviewCoordinationService,
)

# ============================================================================
# CLAIM NEXT RESULT
# ============================================================================


class ClaimResultView(APIView):
    """
    Claim next available result for review.

    Uses SELECT FOR UPDATE SKIP LOCKED for race-condition-free claiming.
    Validates session state before claiming.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ClaimResultInputSerializer,
        responses={
            200: ProcessedResultSerializer,
            404: OpenApiResponse(description="No results available"),
            400: OpenApiResponse(description="Session not ready for review"),
        },
        summary="Claim next available result",
        description=(
            "Atomically claim the next available result for review. "
            "Uses SKIP LOCKED to prevent race conditions."
        ),
    )
    def post(self, request):
        """Handle POST request to claim next result."""
        serializer = ClaimResultInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_id = serializer.validated_data.get("session_id")

        # Validate session access (session-first: resolves org from session)
        session = None
        if session_id:
            session, error = get_validated_session(request, session_id=str(session_id))
            if error:
                return error
            session = cast(SearchSession, session)

            # Check session state
            if session.status not in ["ready_for_review", "under_review"]:
                return Response(
                    {
                        "error": "session_not_ready",
                        "message": (
                            f"Session must be in ready_for_review or under_review state. "
                            f"Current state: {session.status}"
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Use session.organisation for the service call
        organisation = session.organisation if session else None
        if not organisation:
            return Response(
                {
                    "error": "missing_parameter",
                    "message": "session_id is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Call service layer to claim result
        claim_service = ReviewClaimService()
        result = claim_service.claim_next_result(
            reviewer=request.user,
            organisation=organisation,
            session_id=str(session_id) if session_id else None,
        )

        if not result:
            return Response(
                {
                    "error": "no_results_available",
                    "message": "No results available for review at this time",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get the assignment that was just created
        assignment = ReviewerAssignment.objects.filter(
            result=result, reviewer=request.user, is_active=True
        ).first()

        # Log activity
        if session_id:
            SessionActivity.objects.create(
                session_id=session_id,
                activity_type="result_claimed",
                description=f"Result claimed by {request.user.username}",
                user=request.user,
                metadata={
                    "result_id": str(result.id),
                    "role": assignment.role if assignment else "PRIMARY",
                },
            )

        # Serialize and return
        result_data = ProcessedResultSerializer(
            result, context={"request": request}
        ).data
        return Response(result_data, status=status.HTTP_200_OK)


# ============================================================================
# SUBMIT DECISION
# ============================================================================


class SubmitDecisionView(APIView):
    """
    Submit a screening decision for a result.

    Validates decision data, creates immutable decision record,
    detects conflicts, and auto-transitions session state.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ReviewerDecisionInputSerializer,
        responses={
            200: ReviewerDecisionOutputSerializer,
            400: OpenApiResponse(description="Validation error"),
            409: OpenApiResponse(description="Already decided"),
        },
        summary="Submit screening decision",
        description=(
            "Submit a reviewer's decision for a result. "
            "Automatically detects conflicts and updates session state."
        ),
    )
    def post(self, request, result_id):
        """Handle POST request to submit decision."""
        # Validate input
        serializer = ReviewerDecisionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Session-first access control
        result, session, error = get_validated_result(request, str(result_id))
        if error:
            return error
        result = cast(ProcessedResult, result)
        session = cast(SearchSession, session)
        organisation = session.organisation

        # Call service layer to submit decision
        coordination_service = ReviewCoordinationService()

        try:
            decision = coordination_service.submit_reviewer_decision(
                result_id=str(result_id),
                reviewer=request.user,
                decision_data=serializer.validated_data,
                organisation=organisation,
            )
        except ValueError as e:
            # Handle duplicate decision or other validation errors
            return Response(
                {"error": "already_decided", "message": str(e)},
                status=status.HTTP_409_CONFLICT,
            )

        # Auto-transition session to under_review on first decision
        if session.status == "ready_for_review":
            session.status = "under_review"
            session.save(update_fields=["status"])

            SessionActivity.objects.create(
                session=session,
                activity_type="status_changed",
                description="Session transitioned to under_review (first decision submitted)",
                user=request.user,
                metadata={
                    "old_status": "ready_for_review",
                    "new_status": "under_review",
                },
            )

        # Log decision submission
        SessionActivity.objects.create(
            session=session,
            activity_type="decision_submitted",
            description=f"{request.user.username} submitted {decision.decision} decision",
            user=request.user,
            metadata={
                "result_id": str(result.id),
                "decision": decision.decision,
                "confidence_level": decision.confidence_level,
            },
        )

        # Check if consensus reached or conflict detected
        result.refresh_from_db()

        # Serialize decision with blinding-aware context
        serializer_context = {
            "request": request,
            "session": session,
            "is_blinded": BlindingService.should_blind(session),
        }
        response_data = ReviewerDecisionOutputSerializer(
            decision, context=serializer_context
        ).data

        # Add status information to response
        if result.consensus_reached:
            response_data["status"] = "consensus_reached"
            response_data["message"] = (
                "Both reviewers agree. Result will advance to next stage."
            )
        elif result.reviewers_completed >= result.min_reviewers_required:
            # Check if conflict was created
            if (
                hasattr(result, "conflicts")
                and result.conflicts.filter(status="PENDING").exists()
            ):
                conflict = result.conflicts.filter(status="PENDING").first()
                response_data["status"] = "conflict_detected"

                # Respect blinding when showing conflict details
                if BlindingService.should_blind(session):
                    response_data["message"] = (
                        "Decision recorded. All reviewers have completed this result."
                    )
                else:
                    response_data["message"] = (
                        "Reviewers disagree. Conflict resolution required."
                    )
                    response_data["conflict_id"] = str(conflict.id)
                    response_data["conflict_type"] = conflict.conflict_type
        else:
            response_data["status"] = "awaiting_second_reviewer"
            response_data["message"] = "Decision recorded. Awaiting second reviewer."
            response_data["current_reviewer_count"] = result.reviewers_completed
            response_data["min_reviewers_required"] = result.min_reviewers_required

        return Response(response_data, status=status.HTTP_200_OK)


# ============================================================================
# RELEASE RESULT
# ============================================================================


@extend_schema(
    request=None,
    responses={
        200: OpenApiResponse(description="Result released successfully"),
        404: OpenApiResponse(description="No active claim found"),
    },
    summary="Release claimed result",
    description="Release a result that was previously claimed by the current user.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def release_result(request, result_id):
    """Release a claimed result."""
    # Session-first access control
    result, session, error = get_validated_result(request, str(result_id))
    if error:
        return error
    session = cast(SearchSession, session)

    # Call service layer to release claim
    claim_service = ReviewClaimService()
    released = claim_service.release_claim(
        result_id=str(result_id),
        reviewer=request.user,
        organisation=session.organisation,
    )

    if not released:
        return Response(
            {
                "error": "no_active_claim",
                "message": "No active claim found for this result",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # Log activity
    SessionActivity.objects.create(
        session=session,
        activity_type="result_released",
        description=f"{request.user.username} released result",
        user=request.user,
        metadata={"result_id": str(result_id)},
    )

    return Response(
        {"success": True, "message": "Result released successfully"},
        status=status.HTTP_200_OK,
    )


# ============================================================================
# GET RESULT DETAILS
# ============================================================================


@extend_schema(
    responses={200: ProcessedResultSerializer},
    summary="Get result details",
    description="Retrieve details for a specific result.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_result_detail(request, result_id):
    """Get details for a specific result."""
    # Session-first access control
    result, _session, error = get_validated_result(request, str(result_id))
    if error:
        return error
    result = cast(ProcessedResult, result)

    serializer = ProcessedResultSerializer(result, context={"request": request})
    return Response(serializer.data, status=status.HTTP_200_OK)


# ============================================================================
# GET WORK QUEUE
# ============================================================================


@extend_schema(
    summary="View work queue",
    description="Get paginated work queue for the current reviewer in a session.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_work_queue(request):
    """Get paginated work queue for dual screening.

    Returns results with computed status for the current user:
    - pending: not yet decided by this reviewer
    - claimed_by_me: assigned to this reviewer but not yet decided
    - decided_by_me: this reviewer has submitted a decision
    - conflict: result has an unresolved conflict
    """
    from apps.review_results.models import ConflictResolution, ReviewerDecision

    # Session-first access control
    session, error = get_validated_session(request)
    if error:
        return error
    session = cast(SearchSession, session)

    # Get all results for this session
    results_qs = (
        ProcessedResult.objects.filter(session=session)
        .select_related("session", "session__current_configuration")
        .order_by("created_at")
    )

    # Pre-fetch user's decisions and assignments for this session
    my_decisions = dict(
        ReviewerDecision.objects.filter(
            result__session=session, reviewer=request.user
        ).values_list("result_id", "decision")
    )

    # Lookup for the serializer's my_decision value -- must mirror active_for
    # semantics (non-revote decisions only), unlike my_decisions above.
    my_active_decisions = dict(
        ReviewerDecision.objects.filter(
            result__session=session, reviewer=request.user, is_revote=False
        ).values_list("result_id", "decision")
    )
    my_assignments = set(
        ReviewerAssignment.objects.filter(
            result__session=session, reviewer=request.user, is_active=True
        ).values_list("result_id", flat=True)
    )
    conflict_result_ids = set(
        ConflictResolution.objects.filter(
            result__session=session, status="PENDING"
        ).values_list("result_id", flat=True)
    )

    # Build work queue items with computed status
    queue_items = []
    for result in results_qs:
        result_id = result.pk
        if result_id in conflict_result_ids:
            item_status = "conflict"
        elif result_id in my_decisions:
            item_status = "decided_by_me"
        elif result_id in my_assignments:
            item_status = "claimed_by_me"
        else:
            item_status = "pending"
        queue_items.append({"result": result, "status": item_status})

    # Filter by status if requested
    status_filter = request.query_params.get("status")
    if status_filter:
        queue_items = [item for item in queue_items if item["status"] == status_filter]

    # Paginate
    try:
        page = int(request.query_params.get("page", 1))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(int(request.query_params.get("per_page", 25)), 100)
    except (ValueError, TypeError):
        per_page = 25
    total = len(queue_items)
    num_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    page_items = queue_items[start : start + per_page]

    # Serialize
    serialized_results = []
    for item in page_items:
        result_data = ProcessedResultSerializer(
            item["result"],
            context={"request": request, "my_decision_lookup": my_active_decisions},
        ).data
        entry = {"result": result_data, "status": item["status"]}
        if item["status"] == "decided_by_me":
            entry["my_decision"] = {
                "decision": my_decisions.get(item["result"].pk),
            }
        serialized_results.append(entry)

    return Response(
        {
            "count": total,
            "next": f"?page={page + 1}" if page < num_pages else None,
            "previous": f"?page={page - 1}" if page > 1 else None,
            "page": page,
            "num_pages": num_pages,
            "results": serialized_results,
        },
        status=status.HTTP_200_OK,
    )


# ============================================================================
# ADD MANUAL RESULT
# ============================================================================


class AddManualResultView(APIView):
    """
    Add a manually discovered result to a session's screening queue.

    Used when reviewers discover relevant resources while browsing source URLs.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ManualResultInputSerializer,
        responses={
            201: ProcessedResultSerializer,
            400: OpenApiResponse(description="Validation error or duplicate URL"),
            409: OpenApiResponse(description="Session not in reviewable state"),
        },
        summary="Add manual result",
        description=(
            "Add a manually discovered result to a session. "
            "The result enters the standard screening workflow."
        ),
    )
    def post(self, request):
        """Handle POST request to add a manual result."""
        serializer = ManualResultInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_id = serializer.validated_data["session_id"]

        # Session-first access control
        session, error = get_validated_session(request, session_id=str(session_id))
        if error:
            return error
        session = cast(SearchSession, session)

        try:
            result = ManualResultService.add_manual_result(
                session=session,
                user=request.user,
                url=serializer.validated_data["url"],
                title=serializer.validated_data["title"],
                justification=serializer.validated_data["justification"],
                snippet=serializer.validated_data.get("snippet", ""),
            )
        except ValueError as e:
            error_msg = str(e)
            if "state" in error_msg:
                return Response(
                    {"error": "invalid_session_state", "message": error_msg},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(
                {"error": "validation_error", "message": error_msg},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result_data = ProcessedResultSerializer(
            result, context={"request": request}
        ).data
        return Response(result_data, status=status.HTTP_201_CREATED)


# ============================================================================
# GET BLINDING STATUS
# ============================================================================


@extend_schema(
    responses={
        200: OpenApiResponse(
            description="Blinding status for session",
            response={
                "type": "object",
                "properties": {
                    "is_blinded": {"type": "boolean"},
                    "min_reviewers": {"type": "integer"},
                    "reason": {"type": "string"},
                },
            },
        )
    },
    summary="Get session blinding status",
    description="Check if blinding is enforced for this session and get configuration details.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_blinding_status(request, session_id):
    """Get blinding status for a session."""
    # Session-first access control
    session, error = get_validated_session(request, session_id=str(session_id))
    if error:
        return error
    session = cast(SearchSession, session)

    # Get blinding status from service
    blinding_status = BlindingService.get_blinding_status(session)

    return Response(blinding_status, status=status.HTTP_200_OK)
