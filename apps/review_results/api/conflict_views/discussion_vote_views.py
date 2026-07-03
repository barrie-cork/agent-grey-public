"""In-discussion straw-poll (vote) API views.

Workflow #2 endpoints for proposing a straw poll within a conflict discussion
and for responding to it.
"""

from typing import cast

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.review_manager.models import SessionActivity
from apps.review_results.api.utils import (
    get_validated_conflict,
    is_conflicting_reviewer,
)
from apps.review_results.models import (
    ConflictComment,
    ConflictResolution,
)


class ProposeDiscussionVoteView(APIView):
    """
    POST endpoint to propose a straw poll during conflict discussion.

    Creates an InDiscussionVote and a system ConflictComment as the anchor.
    Only conflicting reviewers can propose.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request={
            "type": "object",
            "properties": {
                "rationale": {"type": "string"},
            },
            "required": ["rationale"],
        },
        responses={
            201: OpenApiResponse(description="Straw poll created"),
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Conflict not found"),
        },
        summary="Propose a straw poll during discussion",
    )
    def post(self, request, conflict_id):
        """Create a new straw poll for the conflict discussion."""
        from apps.review_results.models import InDiscussionVote
        from apps.review_results.serializers import InDiscussionVoteSerializer

        # Session-first access control
        conflict, _session, error = get_validated_conflict(request, str(conflict_id))
        if error:
            return error
        conflict = cast(ConflictResolution, conflict)

        # Permission check: must be a conflicting reviewer
        if not is_conflicting_reviewer(request.user, conflict):
            return Response(
                {
                    "error": "permission_denied",
                    "message": "Only conflicting reviewers can propose straw polls",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validate input
        rationale = request.data.get("rationale", "").strip()
        if not rationale:
            return Response(
                {"error": "validation_error", "message": "Rationale is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create system comment as anchor
        system_comment = ConflictComment.objects.create(
            conflict=conflict,
            author=request.user,
            content=f"**Straw Poll Proposed**\n\n{rationale}",
            is_system_message=True,
        )

        # Create the vote
        vote = InDiscussionVote.objects.create(
            conflict=conflict,
            initiating_comment=system_comment,
            proposed_by=request.user,
            rationale=rationale,
        )

        # Update conflict status to IN_DISCUSSION if currently PENDING
        if conflict.status == "PENDING":
            conflict.status = "IN_DISCUSSION"
            conflict.save(update_fields=["status"])

        # Log activity
        SessionActivity.objects.create(
            session=conflict.result.session,
            activity_type="discussion_vote_proposed",
            description=f"{request.user.username} proposed a straw poll",
            user=request.user,
            metadata={
                "conflict_id": str(conflict_id),
                "vote_id": str(vote.id),
            },
        )

        serializer = InDiscussionVoteSerializer(vote)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class RespondToDiscussionVoteView(APIView):
    """
    POST endpoint to respond to a straw poll.

    Each reviewer can respond once per vote.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request={
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": ["INCLUDE", "EXCLUDE", "MAYBE"],
                },
            },
            "required": ["decision"],
        },
        responses={
            201: OpenApiResponse(description="Vote response recorded"),
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Vote not found"),
            409: OpenApiResponse(description="Already voted"),
        },
        summary="Respond to a straw poll",
    )
    def post(self, request, conflict_id, vote_id):
        """Submit a response to a straw poll."""
        from apps.review_results.models import (
            InDiscussionVote,
            InDiscussionVoteResponse,
        )
        from apps.review_results.serializers import InDiscussionVoteSerializer

        # Session-first access control
        conflict, _session, error = get_validated_conflict(request, str(conflict_id))
        if error:
            return error
        conflict = cast(ConflictResolution, conflict)

        # Get vote
        try:
            vote = InDiscussionVote.objects.select_related("conflict").get(
                id=vote_id, conflict=conflict
            )
        except InDiscussionVote.DoesNotExist:
            return Response(
                {"error": "not_found", "message": "Straw poll not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Permission check: must be a conflicting reviewer
        if not is_conflicting_reviewer(request.user, vote.conflict):
            return Response(
                {
                    "error": "permission_denied",
                    "message": "Only conflicting reviewers can respond to straw polls",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if vote.is_closed:
            return Response(
                {"error": "vote_closed", "message": "This straw poll is closed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate decision
        decision = request.data.get("decision", "").strip().upper()
        if decision not in ("INCLUDE", "EXCLUDE", "MAYBE"):
            return Response(
                {
                    "error": "validation_error",
                    "message": "Decision must be INCLUDE, EXCLUDE, or MAYBE",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check for duplicate response
        if InDiscussionVoteResponse.objects.filter(
            vote=vote, reviewer=request.user
        ).exists():
            return Response(
                {
                    "error": "already_voted",
                    "message": "You have already responded to this straw poll",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Create response
        InDiscussionVoteResponse.objects.create(
            vote=vote,
            reviewer=request.user,
            decision=decision,
        )

        # Log activity
        SessionActivity.objects.create(
            session=vote.conflict.result.session,
            activity_type="discussion_vote_response",
            description=f"{request.user.username} responded to straw poll",
            user=request.user,
            metadata={
                "conflict_id": str(conflict_id),
                "vote_id": str(vote_id),
                "decision": decision,
            },
        )

        # Return updated vote with all responses
        vote.refresh_from_db()
        serializer = InDiscussionVoteSerializer(vote)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
