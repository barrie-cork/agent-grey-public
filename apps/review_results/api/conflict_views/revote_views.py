"""Conflict comment and revote API views.

Workflow #2 endpoints for adding conflict comments and for the revote flow
(propose, accept, and submit a revote decision).
"""

from datetime import timedelta
from typing import cast

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import Permissions
from apps.review_manager.models import SearchSession, SessionActivity
from apps.review_results.api.utils import (
    get_validated_conflict,
    is_conflicting_reviewer,
)
from apps.review_results.models import (
    ConflictComment,
    ConflictResolution,
    ReviewerDecision,
    RevoteProposal,
)
from apps.review_results.serializers import (
    ConflictCommentCreateSerializer,
    ConflictCommentSerializer,
    ReviewerDecisionCreateSerializer,
    RevoteProposalSerializer,
)


class ConflictCommentCreateView(APIView):
    """
    POST endpoint to create discussion comments on conflicts.

    Supports top-level comments and threaded replies.
    Updates conflict status to IN_DISCUSSION if currently PENDING.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ConflictCommentCreateSerializer,
        responses={
            201: ConflictCommentSerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(
                description="Permission denied - not a conflicting reviewer"
            ),
            404: OpenApiResponse(description="Conflict not found"),
        },
        summary="Add comment to conflict discussion",
        description="Create a new comment on a conflict. Supports threaded replies via parent_id.",
    )
    def post(self, request, conflict_id):
        """Create a new discussion comment."""
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

        # Check if user is a conflicting reviewer
        user_is_reviewer = is_conflicting_reviewer(request.user, conflict)

        # Check if user can comment on conflicts (using centralised permission system)
        can_comment = request.user.has_perm(
            Permissions.CONFLICT_COMMENT, session.organisation
        )

        if not (user_is_reviewer or can_comment):
            return Response(
                {
                    "error": "permission_denied",
                    "message": "Only conflicting reviewers or administrators can add discussion comments",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validate input
        serializer = ConflictCommentCreateSerializer(data=request.data)
        serializer.conflict = conflict  # Set context for parent validation

        if not serializer.is_valid():
            return Response(
                {"error": "validation_error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create comment
        comment_data = serializer.validated_data
        parent_comment = None
        if comment_data.get("parent_id"):
            try:
                parent_comment = ConflictComment.objects.get(
                    id=comment_data["parent_id"], conflict=conflict
                )
            except ConflictComment.DoesNotExist:
                return Response(
                    {
                        "error": "validation_error",
                        "message": "Parent comment not found",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        comment = ConflictComment.objects.create(
            conflict=conflict,
            author=request.user,
            parent=parent_comment,
            content=comment_data["content"],
            is_system_message=False,
            criterion_tag=comment_data.get("criterion_tag", ""),
        )

        # Update conflict status to IN_DISCUSSION if currently PENDING
        if conflict.status == "PENDING":
            conflict.status = "IN_DISCUSSION"
            conflict.save(update_fields=["status"])

        # Log activity
        SessionActivity.objects.create(
            session=session,
            activity_type="conflict_comment_added",
            description=f"{request.user.username} added comment to conflict discussion",
            user=request.user,
            metadata={
                "conflict_id": str(conflict_id),
                "comment_id": str(comment.id),
                "is_reply": parent_comment is not None,
            },
        )

        # Send email notifications (Phase 4)
        from apps.review_results.services.email_notification_service import (
            EmailNotificationService,
        )

        email_service = EmailNotificationService()
        email_service.notify_conflict_comment_added(
            conflict_id=str(conflict_id),
            comment_id=str(comment.id),
            commenter_id=str(request.user.id),
        )

        # Serialize and return
        response_serializer = ConflictCommentSerializer(comment)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ProposeRevoteView(APIView):
    """
    POST endpoint to propose a re-vote for a conflict.

    Creates a RevoteProposal and system message.
    Auto-accepts for the proposer.
    Updates conflict status to ESCALATED.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "rationale": {
                        "type": "string",
                        "description": "Reason for proposing re-vote",
                    },
                },
                "required": ["rationale"],
            }
        },
        responses={
            201: RevoteProposalSerializer,
            400: OpenApiResponse(
                description="Validation error or proposal not allowed"
            ),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Conflict not found"),
        },
        summary="Propose re-vote for conflict",
        description="Create a re-vote proposal. Proposer automatically accepts. All reviewers must accept before re-voting can begin.",
    )
    def post(self, request, conflict_id):
        """Propose a re-vote for a conflict."""
        # Session-first access control
        conflict, _session, error = get_validated_conflict(request, str(conflict_id))
        if error:
            return error
        conflict = cast(ConflictResolution, conflict)

        # Check if user can propose re-vote
        if not conflict.can_propose_revote(request.user):
            return Response(
                {
                    "error": "proposal_not_allowed",
                    "message": "Cannot propose re-vote: either not a conflicting reviewer, active proposal exists, or conflict already resolved",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate rationale
        rationale = request.data.get("rationale", "").strip()
        if not rationale:
            return Response(
                {"error": "validation_error", "message": "Rationale is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create proposal
        proposal = RevoteProposal.objects.create(
            conflict=conflict,
            proposed_by=request.user,
            rationale=rationale,
            status="PROPOSED",
            expires_at=timezone.now() + timedelta(hours=48),
        )

        # Auto-accept for proposer
        proposal.accepted_by.add(request.user)

        # Create system message
        system_message_content = (
            f"**Re-vote proposed by {request.user.username}**\n\nRationale: {rationale}"
        )
        ConflictComment.objects.create(
            conflict=conflict,
            author=None,  # System message has no author
            content=system_message_content,
            is_system_message=True,
        )

        # Update conflict status to ESCALATED
        conflict.status = "ESCALATED"
        conflict.save(update_fields=["status"])

        # Log activity
        SessionActivity.objects.create(
            session=conflict.result.session,
            activity_type="revote_proposed",
            description=f"{request.user.username} proposed re-vote for conflict",
            user=request.user,
            metadata={"conflict_id": str(conflict_id), "proposal_id": str(proposal.id)},
        )

        # Send email notifications (Phase 4)
        from apps.review_results.services.email_notification_service import (
            EmailNotificationService,
        )

        email_service = EmailNotificationService()
        email_service.notify_revote_proposed(
            conflict_id=str(conflict_id),
            proposal_id=str(proposal.id),
            proposer_id=str(request.user.id),
        )

        # Serialize and return
        serializer = RevoteProposalSerializer(proposal)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AcceptRevoteView(APIView):
    """
    POST endpoint to accept a re-vote proposal.

    Adds user to accepted_by list.
    If all reviewers accepted, changes status to ACCEPTED and sends notifications.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: RevoteProposalSerializer,
            400: OpenApiResponse(description="Cannot accept proposal"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Conflict or proposal not found"),
        },
        summary="Accept re-vote proposal",
        description="Accept a re-vote proposal. When all reviewers accept, proposal status changes to ACCEPTED and re-voting can begin.",
    )
    def post(self, request, conflict_id, proposal_id):
        """Accept a re-vote proposal."""
        # Session-first access control
        conflict, _session, error = get_validated_conflict(request, str(conflict_id))
        if error:
            return error
        conflict = cast(ConflictResolution, conflict)

        # Get proposal
        try:
            proposal = RevoteProposal.objects.get(id=proposal_id, conflict=conflict)
        except RevoteProposal.DoesNotExist:
            return Response(
                {"error": "not_found", "message": "Conflict or proposal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user can accept
        if not proposal.can_accept(request.user):
            return Response(
                {
                    "error": "cannot_accept",
                    "message": "Cannot accept: either not a conflicting reviewer, proposal not in PROPOSED status, or proposal expired",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Add user to accepted_by
        proposal.accepted_by.add(request.user)

        # Check if all reviewers have accepted
        all_accepted = proposal.all_accepted()
        if all_accepted:
            proposal.status = "ACCEPTED"
            proposal.accepted_at = timezone.now()
            proposal.save(update_fields=["status", "accepted_at"])

            # Create system message
            system_message_content = "**Re-vote accepted by all reviewers**\n\nReviewers can now submit new decisions."
            ConflictComment.objects.create(
                conflict=conflict,
                author=None,
                content=system_message_content,
                is_system_message=True,
            )

            # Send email notification (Phase 4)
            from apps.review_results.services.email_notification_service import (
                EmailNotificationService,
            )

            email_service = EmailNotificationService()
            email_service.notify_revote_ready(
                conflict_id=str(conflict_id), proposal_id=str(proposal.id)
            )

        # Log activity
        SessionActivity.objects.create(
            session=conflict.result.session,
            activity_type="revote_accepted",
            description=f"{request.user.username} accepted re-vote proposal",
            user=request.user,
            metadata={
                "conflict_id": str(conflict_id),
                "proposal_id": str(proposal_id),
                "all_accepted": all_accepted,
            },
        )

        # Serialize and return
        serializer = RevoteProposalSerializer(proposal)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SubmitRevoteDecisionView(APIView):
    """
    POST endpoint to submit a re-vote decision.

    Creates a new ReviewerDecision with is_revote=True.
    Updates proposal status to IN_PROGRESS on first decision.
    Checks for consensus when all decisions submitted.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=ReviewerDecisionCreateSerializer,
        responses={
            201: OpenApiResponse(description="Re-vote decision submitted"),
            400: OpenApiResponse(description="Validation error or cannot submit"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Conflict or proposal not found"),
        },
        summary="Submit re-vote decision",
        description="Submit a new decision as part of a re-vote. When all reviewers submit, consensus is checked automatically.",
    )
    def post(self, request, conflict_id, proposal_id):
        """Submit a re-vote decision."""
        # Session-first access control
        conflict, session, error = get_validated_conflict(request, str(conflict_id))
        if error:
            return error
        conflict = cast(ConflictResolution, conflict)
        session = cast(SearchSession, session)
        organisation = session.organisation

        # Get proposal
        try:
            proposal = RevoteProposal.objects.prefetch_related(
                "revote_decisions__reviewer"
            ).get(id=proposal_id, conflict=conflict)
        except RevoteProposal.DoesNotExist:
            return Response(
                {"error": "not_found", "message": "Conflict or proposal not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check proposal status is ACCEPTED or IN_PROGRESS
        if proposal.status not in ["ACCEPTED", "IN_PROGRESS"]:
            return Response(
                {
                    "error": "proposal_not_accepted",
                    "message": "Cannot submit re-vote decision: proposal not yet accepted by all reviewers",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user is a conflicting reviewer
        if not is_conflicting_reviewer(request.user, conflict):
            return Response(
                {
                    "error": "permission_denied",
                    "message": "Only conflicting reviewers can submit re-vote decisions",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check for existing re-vote decision from this user
        existing_decision = ReviewerDecision.objects.filter(
            result=conflict.result,
            reviewer=request.user,
            is_revote=True,
            revote_proposal=proposal,
        ).first()

        if existing_decision:
            return Response(
                {
                    "error": "already_voted",
                    "message": "You have already submitted a re-vote decision for this proposal",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate input
        serializer = ReviewerDecisionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "validation_error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create re-vote decision
        decision_data = serializer.validated_data
        new_decision = ReviewerDecision.objects.create(
            organisation=organisation,
            result=conflict.result,
            reviewer=request.user,
            decision=decision_data["decision"],
            exclusion_reason=decision_data.get("exclusion_reason", ""),
            notes=decision_data.get("notes", ""),
            is_revote=True,
            revote_proposal=proposal,
            screening_stage="SCREENING",
            confidence_level=2,  # Default medium confidence
        )

        # Update proposal status to IN_PROGRESS if this is the first re-vote decision
        if proposal.status == "ACCEPTED":
            proposal.status = "IN_PROGRESS"
            proposal.save(update_fields=["status"])

        # Check if all reviewers have submitted re-vote decisions
        revote_decisions = ReviewerDecision.objects.filter(
            result=conflict.result, is_revote=True, revote_proposal=proposal
        )
        revote_decision_count = revote_decisions.count()
        required_reviewer_count = conflict.conflicting_decisions.count()

        # Log activity
        SessionActivity.objects.create(
            session=session,
            activity_type="revote_decision_submitted",
            description=f"{request.user.username} submitted re-vote decision: {decision_data['decision']}",
            user=request.user,
            metadata={
                "conflict_id": str(conflict_id),
                "proposal_id": str(proposal_id),
                "decision_id": str(new_decision.id),
                "decision": decision_data["decision"],
                "decisions_submitted": revote_decision_count,
                "decisions_required": required_reviewer_count,
            },
        )

        # If all reviewers have submitted, check for consensus
        if revote_decision_count == required_reviewer_count:
            # Get all re-vote decisions
            revote_decision_values = list(
                revote_decisions.values_list("decision", flat=True)
            )

            # Check if all decisions are the same
            consensus_reached = len(set(revote_decision_values)) == 1

            if consensus_reached:
                # Consensus reached!
                consensus_decision = revote_decision_values[0]

                # Update proposal
                proposal.status = "COMPLETED"
                proposal.completed_at = timezone.now()
                proposal.resulted_in_consensus = True
                proposal.save(
                    update_fields=["status", "completed_at", "resulted_in_consensus"]
                )

                # Set final decision to the consensus re-vote decision
                final_decision = revote_decisions.first()

                # Update conflict
                conflict.status = "RESOLVED"
                conflict.resolution_method = "CONSENSUS"
                conflict.resolved_at = timezone.now()
                conflict.final_decision = final_decision
                conflict.save(
                    update_fields=[
                        "status",
                        "resolution_method",
                        "resolved_at",
                        "final_decision",
                    ]
                )

                # Create system message
                system_message_content = f"**Consensus reached through re-vote!**\n\nAll reviewers agreed to **{consensus_decision}** the result."
                ConflictComment.objects.create(
                    conflict=conflict,
                    author=None,
                    content=system_message_content,
                    is_system_message=True,
                )

                # Log consensus
                SessionActivity.objects.create(
                    session=session,
                    activity_type="consensus_reached",
                    description=f"Consensus reached through re-vote: {consensus_decision}",
                    user=request.user,
                    metadata={
                        "conflict_id": str(conflict_id),
                        "proposal_id": str(proposal_id),
                        "consensus_decision": consensus_decision,
                    },
                )

                # Send email notification (Phase 4)
                from apps.review_results.services.email_notification_service import (
                    EmailNotificationService,
                )

                email_service = EmailNotificationService()
                email_service.notify_consensus_reached_via_revote(
                    conflict_id=str(conflict_id),
                    proposal_id=str(proposal_id),
                    consensus_decision=consensus_decision,
                )

            else:
                # No consensus - needs arbitration
                proposal.status = "COMPLETED"
                proposal.completed_at = timezone.now()
                proposal.resulted_in_consensus = False
                proposal.save(
                    update_fields=["status", "completed_at", "resulted_in_consensus"]
                )

                # Create system message
                system_message_content = f"**Re-vote completed but no consensus reached**\n\nDecisions: {', '.join(revote_decision_values)}\n\nArbitration required."
                ConflictComment.objects.create(
                    conflict=conflict,
                    author=None,
                    content=system_message_content,
                    is_system_message=True,
                )

        # Serialize and return
        from apps.review_results.serializers import ReviewerDecisionOutputSerializer

        response_serializer = ReviewerDecisionOutputSerializer(new_decision)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


# ============================================================================
# IN-DISCUSSION VOTING (STRAW POLL) ENDPOINTS
# ============================================================================
