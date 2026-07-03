"""Conflict listing, detail, resolution and escalation API views.

Workflow #2 endpoints for listing conflicts, fetching conflict detail,
resolving and escalating conflicts, and adding discussion comments.
"""

from typing import cast

from django.core.paginator import Paginator
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import Permissions
from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_results.api.utils import (
    get_validated_conflict,
    get_validated_session,
    is_conflicting_reviewer,
)
from apps.review_results.models import (
    ConflictAccessLog,
    ConflictComment,
    ConflictResolution,
)
from apps.review_results.serializers import (
    ConflictCommentSerializer,
    ConflictResolutionDetailSerializer,
    ConflictResolutionInputSerializer,
    ConflictResolutionLeadViewSerializer,
    ConflictResolutionListSerializer,
    RevoteProposalSerializer,
)
from apps.review_results.services.review_coordination_service import (
    ReviewCoordinationService,
)


class ConflictListView(APIView):
    """
    List conflicts with filtering and pagination.

    Supports filtering by status, conflict_type, and assigned_to_me.

    **Updated (2025-11-02)**: Session owners can now view conflicts during review phase
    for early calibration. Uses blinded serializer (ConflictResolutionLeadViewSerializer).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "status",
                str,
                description="Filter by status (PENDING, IN_DISCUSSION, ESCALATED, RESOLVED)",
            ),
            OpenApiParameter(
                "conflict_type", str, description="Filter by conflict type"
            ),
            OpenApiParameter(
                "assigned_to_me",
                bool,
                description="Show only conflicts I'm involved in",
            ),
            OpenApiParameter("session_id", str, description="Filter by session ID"),
            OpenApiParameter("page", int, description="Page number (default: 1)"),
            OpenApiParameter(
                "per_page", int, description="Results per page (default: 20, max: 100)"
            ),
        ],
        responses={200: ConflictResolutionListSerializer(many=True)},
        summary="List conflicts",
        description="Get a paginated list of conflicts with optional filters.",
    )
    def get(self, request):
        """Handle GET request to list conflicts."""
        session, error = get_validated_session(
            request, allow_roles=[Permissions.CONFLICT_VIEW]
        )
        if error:
            return error
        session = cast(SearchSession, session)

        # Session-wide counts (before any filtering)
        base_qs = ConflictResolution.objects.filter(result__session=session)
        session_total = base_qs.count()
        session_resolved = base_qs.filter(status="RESOLVED").count()
        session_counts = {
            "total": session_total,
            "resolved": session_resolved,
            "pending": session_total - session_resolved,
        }

        queryset = base_qs.prefetch_related(
            "conflicting_decisions__reviewer"
        ).select_related("result", "result__session")

        # Apply filters
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())

        conflict_type_filter = request.query_params.get("conflict_type")
        if conflict_type_filter:
            queryset = queryset.filter(conflict_type=conflict_type_filter.upper())

        assigned_to_me = request.query_params.get("assigned_to_me")
        if assigned_to_me and assigned_to_me.lower() == "true":
            # Filter to conflicts where user is one of the conflicting reviewers
            queryset = queryset.filter(
                conflicting_decisions__reviewer=request.user
            ).distinct()

        # Order by detection time (newest first)
        queryset = queryset.order_by("-detected_at")

        # Pagination
        try:
            page_num = int(request.query_params.get("page", 1))
        except (ValueError, TypeError):
            page_num = 1
        try:
            per_page = min(int(request.query_params.get("per_page", 20)), 100)
        except (ValueError, TypeError):
            per_page = 20

        paginator = Paginator(queryset, per_page)
        page = paginator.get_page(page_num)

        # Add blinding context to serializer
        from apps.review_results.services.blinding_service import BlindingService

        # Determine if blinding is active for any session in results
        # (Note: conflicts from different sessions might have different blinding rules)
        serializer_context = {"request": request, "blinding_service": BlindingService}

        # Determine which serializer to use based on user role
        # If session owner during review phase: use blinded serializer
        # Otherwise: use full serializer
        use_blinded_serializer = False
        if session:
            # Check if user is session owner and blinding is active
            is_session_owner = session.owner == request.user
            blinding_active = BlindingService.should_blind(session)

            if is_session_owner and blinding_active:
                use_blinded_serializer = True

                # Log audit entry for each conflict accessed
                for conflict in page.object_list:
                    ConflictAccessLog.objects.create(
                        organisation=conflict.organisation,
                        conflict=conflict,
                        accessed_by=request.user,
                        access_type="LIST_VIEW",
                        is_session_owner=True,
                    )

        # Serialize with appropriate serializer
        if use_blinded_serializer:
            serializer = ConflictResolutionLeadViewSerializer(
                page.object_list, many=True, context=serializer_context
            )
        else:
            serializer = ConflictResolutionListSerializer(
                page.object_list, many=True, context=serializer_context
            )

        # Build response with pagination metadata
        return Response(
            {
                "count": paginator.count,
                "page": page_num,
                "num_pages": paginator.num_pages,
                "next": page.has_next(),
                "previous": page.has_previous(),
                "results": serializer.data,
                "session_counts": session_counts,
            },
            status=status.HTTP_200_OK,
        )


# ============================================================================
# GET CONFLICT DETAILS
# ============================================================================


@extend_schema(
    responses={200: ConflictResolutionDetailSerializer},
    summary="Get conflict details",
    description="Retrieve full details for a specific conflict including all conflicting decisions.",
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_conflict_detail(request, conflict_id):
    """Get details for a specific conflict."""
    # Session-first access control (oversight: CONFLICT_VIEW role or participation)
    conflict, _session, error = get_validated_conflict(
        request,
        str(conflict_id),
        prefetch=True,
        allow_roles=[Permissions.CONFLICT_VIEW],
    )
    if error:
        return error
    conflict = cast(ConflictResolution, conflict)

    # Log access for audit trail
    ConflictAccessLog.objects.create(
        organisation=conflict.organisation,
        conflict=conflict,
        accessed_by=request.user,
        access_type="DETAIL_VIEW",
        is_session_owner=(
            conflict.result.session.owner == request.user
            if conflict.result and conflict.result.session
            else False
        ),
    )

    serializer = ConflictResolutionDetailSerializer(conflict)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ============================================================================
# RESOLVE CONFLICT
# ============================================================================


class ResolveConflictView(APIView):
    """
    Resolve a conflict with a final decision.

    Creates a final decision record and updates conflict status to RESOLVED.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ConflictResolutionInputSerializer,
        responses={
            200: ConflictResolutionDetailSerializer,
            400: OpenApiResponse(description="Validation error"),
            409: OpenApiResponse(description="Already resolved"),
        },
        summary="Resolve conflict",
        description="Resolve a conflict by providing a final decision. Requires SENIOR_RESEARCHER or INFORMATION_SPECIALIST role.",
    )
    def post(self, request, conflict_id):
        """Handle POST request to resolve conflict."""
        # Session-first access control: CONFLICT_VIEW role or participation grants
        # access to the conflict; the CONFLICT_RESOLVE check below gates the
        # resolve action itself (every resolver also holds CONFLICT_VIEW).
        conflict, session, error = get_validated_conflict(
            request, str(conflict_id), allow_roles=[Permissions.CONFLICT_VIEW]
        )
        if error:
            return error
        conflict = cast(ConflictResolution, conflict)
        session = cast(SearchSession, session)
        organisation = session.organisation

        # Role check: only arbitrators (SENIOR_RESEARCHER+) can resolve
        if not request.user.has_perm(Permissions.CONFLICT_RESOLVE, organisation):
            return Response(
                {
                    "error": "permission_denied",
                    "message": "Only arbitrators or administrators can resolve conflicts.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if already resolved (409 before validation)
        if conflict.status == "RESOLVED":
            return Response(
                {
                    "error": "already_resolved",
                    "message": "This conflict has already been resolved",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Validate input (after org/conflict checks)
        serializer = ConflictResolutionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Inject resolution method from session configuration (server-authoritative)
        resolution_data = serializer.validated_data.copy()
        config = conflict.result.session.current_configuration
        resolution_data["resolution_method"] = config.conflict_resolution_method

        # Call service layer to resolve conflict
        coordination_service = ReviewCoordinationService()

        try:
            resolved_conflict = coordination_service.resolve_conflict(
                conflict_id=str(conflict_id),
                resolver=request.user,
                resolution_data=resolution_data,
                organisation=organisation,
            )
        except ValueError as e:
            return Response(
                {"error": "resolution_error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Log activity
        SessionActivity.objects.create(
            session=session,
            activity_type="conflict_resolved",
            description=f"{request.user.username} resolved conflict using {resolution_data['resolution_method']}",
            user=request.user,
            metadata={
                "conflict_id": str(conflict_id),
                "resolution_method": resolution_data["resolution_method"],
                "final_decision": resolution_data["decision"],
            },
        )

        # Log conflict access for audit trail
        ConflictAccessLog.objects.create(
            organisation=organisation,
            conflict=conflict,
            accessed_by=request.user,
            access_type="ARBITRATION",
            is_session_owner=(session.owner == request.user),
        )

        # Re-fetch with full relations so serializer has session data
        resolved_conflict = (
            ConflictResolution.objects.select_related("result__session")
            .prefetch_related("conflicting_decisions__reviewer")
            .get(pk=resolved_conflict.pk)
        )

        # Serialize and return
        response_serializer = ConflictResolutionDetailSerializer(resolved_conflict)
        response_data = response_serializer.data
        response_data["success"] = True
        response_data["message"] = (
            f"Conflict resolved via {resolution_data['resolution_method']}"
        )

        return Response(response_data, status=status.HTTP_200_OK)


class EscalateConflictView(APIView):
    """
    POST endpoint to escalate a conflict to an arbitrator.

    Sets conflict status to ESCALATED and notifies the session owner.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Optional reason for escalation",
                    },
                },
            }
        },
        responses={
            200: ConflictResolutionDetailSerializer,
            400: OpenApiResponse(
                description="Validation error or escalation not allowed"
            ),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Conflict not found"),
        },
        summary="Escalate conflict to arbitrator",
        description="Escalate a conflict for arbitration by a senior researcher. Only conflicting reviewers can escalate.",
    )
    def post(self, request, conflict_id):
        """Escalate a conflict to an arbitrator."""
        # Session-first access control
        conflict, _session, error = get_validated_conflict(request, str(conflict_id))
        if error:
            return error
        conflict = cast(ConflictResolution, conflict)

        # Guard: user must be a conflicting reviewer
        if not is_conflicting_reviewer(request.user, conflict):
            return Response(
                {
                    "error": "not_reviewer",
                    "message": "Only conflicting reviewers can escalate",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Guard: conflict must not be resolved or already escalated
        if conflict.status in ("RESOLVED", "ESCALATED"):
            return Response(
                {
                    "error": "invalid_status",
                    "message": f"Cannot escalate a conflict with status {conflict.status}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = request.data.get("reason", "").strip()

        # Update conflict status
        conflict.status = "ESCALATED"
        conflict.save(update_fields=["status"])

        # Create system message
        system_message_content = (
            f"**Conflict escalated to arbitrator by {request.user.username}**"
        )
        if reason:
            system_message_content += f"\n\nReason: {reason}"

        ConflictComment.objects.create(
            conflict=conflict,
            author=None,
            content=system_message_content,
            is_system_message=True,
        )

        # Log activity
        SessionActivity.objects.create(
            session=conflict.result.session,
            activity_type="conflict_escalated",
            description=f"{request.user.username} escalated conflict to arbitrator",
            user=request.user,
            metadata={
                "conflict_id": str(conflict_id),
                "reason": reason,
            },
        )

        # Send email notification to session owner
        from apps.review_results.services.email_notification_service import (
            EmailNotificationService,
        )

        email_service = EmailNotificationService()
        email_service.notify_conflict_escalated(
            conflict_id=str(conflict_id),
            escalated_by_id=str(request.user.id),
            reason=reason,
        )

        # Serialize and return
        serializer = ConflictResolutionDetailSerializer(conflict)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ============================================================================
# ADD DISCUSSION COMMENT
# ============================================================================


@extend_schema(
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "comment": {"type": "string", "description": "Discussion comment"},
            },
            "required": ["comment"],
        }
    },
    responses={
        200: ConflictResolutionDetailSerializer,
        400: OpenApiResponse(description="Validation error"),
    },
    summary="Add discussion comment",
    description="Add a discussion comment to a conflict. Updates conflict status to IN_DISCUSSION if PENDING.",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_conflict_discussion(request, conflict_id):
    """Add a discussion comment to a conflict."""
    # Session-first access control: CONFLICT_VIEW role or participation grants
    # access to the conflict; the comment gate below (conflicting reviewer or
    # CONFLICT_COMMENT) decides who may actually post.
    conflict, session, error = get_validated_conflict(
        request, str(conflict_id), allow_roles=[Permissions.CONFLICT_VIEW]
    )
    if error:
        return error
    conflict = cast(ConflictResolution, conflict)
    session = cast(SearchSession, session)

    # Validate input
    comment = request.data.get("comment")
    if not comment:
        return Response(
            {"error": "validation_error", "message": "Comment field is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check if user is one of the conflicting reviewers or an admin
    user_is_reviewer = is_conflicting_reviewer(request.user, conflict)

    # Check if user can discuss conflicts (using centralised permission system)
    can_discuss = request.user.has_perm(
        Permissions.CONFLICT_COMMENT, session.organisation
    )

    if not (user_is_reviewer or can_discuss):
        return Response(
            {
                "error": "permission_denied",
                "message": "Only conflicting reviewers or administrators can add discussion comments",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # Append comment to resolution_notes
    timestamp = f"\n[{request.user.username} - {conflict.detected_at.strftime('%Y-%m-%d %H:%M')}]"
    new_comment = f"{timestamp}\n{comment}"

    if conflict.resolution_notes:
        conflict.resolution_notes += f"\n\n{new_comment}"
    else:
        conflict.resolution_notes = new_comment

    # Update status to IN_DISCUSSION if currently PENDING
    if conflict.status == "PENDING":
        conflict.status = "IN_DISCUSSION"

    conflict.save(update_fields=["resolution_notes", "status"])

    # Log activity
    SessionActivity.objects.create(
        session=session,
        activity_type="conflict_discussion",
        description=f"{request.user.username} added discussion comment to conflict",
        user=request.user,
        metadata={"conflict_id": str(conflict_id)},
    )

    # Serialize and return
    serializer = ConflictResolutionDetailSerializer(conflict)
    response_data = serializer.data
    response_data["success"] = True
    response_data["message"] = "Discussion comment added successfully"

    return Response(response_data, status=status.HTTP_200_OK)


# ============================================================================
# CONSENSUS DISCUSSION API ENDPOINTS (Phase 3)
# ============================================================================


class ConflictDetailView(APIView):
    """
    GET endpoint to retrieve full conflict data for discussion page.

    Returns:
        - conflict metadata
        - result data
        - conflicting_decisions
        - comments (top-level only, replies nested)
        - active_revote_proposal
        - permissions object (can_comment, can_propose_revote, etc.)
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Full conflict data"),
            403: OpenApiResponse(
                description="Permission denied - not a conflicting reviewer"
            ),
            404: OpenApiResponse(description="Conflict not found"),
        },
        summary="Get full conflict discussion data",
        description="Retrieve all data needed for the conflict discussion page including comments and permissions.",
    )
    def get(self, request, conflict_id):
        """Get full conflict data for discussion page."""
        # Session-first access control with prefetch
        # (oversight: CONFLICT_VIEW role or participation; secondary gate below)
        conflict, session, error = get_validated_conflict(
            request,
            str(conflict_id),
            prefetch=True,
            allow_roles=[Permissions.CONFLICT_VIEW],
        )
        if error:
            return error
        conflict = cast(ConflictResolution, conflict)
        session = cast(SearchSession, session)

        # Check if user is a conflicting reviewer
        user_is_reviewer = is_conflicting_reviewer(request.user, conflict)
        is_session_owner = session.owner == request.user

        # Check if user can view conflicts (using centralised permission system)
        can_view = request.user.has_perm(Permissions.CONFLICT_VIEW, conflict)

        # Conflicting reviewers, session owners, or admins can view
        if not (user_is_reviewer or is_session_owner or can_view):
            return Response(
                {
                    "error": "permission_denied",
                    "message": "Only conflicting reviewers or administrators can view conflict discussions",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Serialize conflict
        conflict_serializer = ConflictResolutionDetailSerializer(conflict)

        # Get top-level comments (parent=None) with nested replies
        top_level_comments = conflict.comments.filter(
            parent=None, is_deleted=False
        ).order_by("created_at")
        comments_data = ConflictCommentSerializer(top_level_comments, many=True).data

        # Get active revote proposal
        active_proposal = conflict.get_active_revote_proposal()
        active_proposal_data = (
            RevoteProposalSerializer(active_proposal).data if active_proposal else None
        )

        # Build permissions object
        permissions = {
            "can_comment": user_is_reviewer or can_view,
            "can_propose_revote": conflict.can_propose_revote(request.user),
            "can_accept_revote": active_proposal.can_accept(request.user)
            if active_proposal
            else False,
            # F1/PMD #282: must mirror the resolve POST's permission check
            # (CONFLICT_RESOLVE), not view access — a LEAD_REVIEWER can view
            # but not resolve, so keying off can_view showed them a form whose
            # submit then 403'd.
            "can_resolve": request.user.has_perm(Permissions.CONFLICT_RESOLVE, conflict)
            and conflict.status != "RESOLVED",
            # F1/PMD #282: mirror EscalateConflictView's guard so the frontend
            # gates the escalate button without re-implementing permission logic
            # (only conflicting reviewers, and not once RESOLVED/ESCALATED).
            "can_escalate": user_is_reviewer
            and conflict.status not in ("RESOLVED", "ESCALATED"),
        }

        # Build response
        response_data = {
            "conflict": conflict_serializer.data,
            "comments": comments_data,
            "active_revote_proposal": active_proposal_data,
            "permissions": permissions,
        }

        return Response(response_data, status=status.HTTP_200_OK)
