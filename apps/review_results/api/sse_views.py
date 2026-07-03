"""
Server-Sent Events (SSE) views for real-time conflict discussion updates.

Provides push-based updates for consensus discussion events, eliminating
the need for client-side polling. Implements Django 5.2 async patterns
with proper ATOMIC_REQUESTS handling.

Events:
- new_comment: New discussion comment posted
- revote_proposed: Re-vote proposal created
- revote_accepted: Re-vote proposal accepted by all reviewers
- revote_decision_submitted: Reviewer submitted re-vote decision
- consensus_reached: Conflict resolved via re-vote consensus
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from asgiref.sync import sync_to_async
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.review_results.models import (
    ConflictComment,
    ConflictResolution,
    RevoteProposal,
)
from apps.review_results.serializers import (
    ConflictCommentSerializer,
    RevoteProposalSerializer,
)

logger = logging.getLogger(__name__)


@csrf_exempt  # SSE doesn't support CSRF tokens in EventSource API
@login_required
@transaction.non_atomic_requests  # Required for async views with ATOMIC_REQUESTS=True (Django 5.2)
async def conflict_discussion_stream(request, conflict_id):  # noqa: C901 - SSE stream
    """
    SSE endpoint for real-time conflict discussion updates.

    Streams discussion events to connected clients using Server-Sent Events.
    Implements Django 5.2 async patterns with proper database thread safety.

    Args:
        request: Django HttpRequest
        conflict_id: UUID of the ConflictResolution

    Returns:
        StreamingHttpResponse with text/event-stream content type

    SSE Event Format:
        event: new_comment
        data: {"comment": {...}}

        event: revote_proposed
        data: {"proposal": {...}}

    Security:
        - User must be a conflicting reviewer or admin
        - Login required via @login_required decorator
        - CSRF exempt as EventSource API doesn't support CSRF tokens

    Django 5.2 Compatibility:
        - Uses @transaction.non_atomic_requests for async view compatibility
        - Uses sync_to_async(thread_sensitive=True) for database queries
        - Thread-safe database connection handling
    """

    async def event_generator():
        """
        Async generator for SSE events.

        Monitors conflict discussion activity and yields SSE-formatted events.
        Implements change detection, error handling, and graceful termination.

        Yields:
            str: SSE-formatted event strings (event: event_name\\ndata: {...}\\n\\n)
        """
        try:
            # Verify permissions
            def check_permissions():
                """
                Check if user can view this conflict discussion.

                Returns:
                    tuple: (has_access: bool, conflict: ConflictResolution or None, error_msg: str or None)
                """
                try:
                    from apps.organisation.models import OrganisationMembership

                    conflict = (
                        ConflictResolution.objects.prefetch_related(
                            "conflicting_decisions__reviewer"
                        )
                        .select_related("result__session")
                        .get(id=conflict_id)
                    )

                    # Check if user is a conflicting reviewer
                    reviewer_ids = list(
                        conflict.conflicting_decisions.values_list(
                            "reviewer_id", flat=True
                        )
                    )
                    is_conflicting_reviewer = request.user.id in reviewer_ids

                    # Check if user is admin
                    is_admin = OrganisationMembership.objects.filter(
                        user=request.user,
                        organisation=conflict.organisation,
                        role__in=["SENIOR_RESEARCHER", "INFORMATION_SPECIALIST"],
                        is_active=True,
                    ).exists()

                    if not (is_conflicting_reviewer or is_admin):
                        return (
                            False,
                            None,
                            "Only conflicting reviewers or administrators can view conflict discussions",
                        )

                    return True, conflict, None

                except ConflictResolution.DoesNotExist:
                    return False, None, "Conflict not found"
                except Exception as e:
                    logger.error(f"SSE permission check error: {e}", exc_info=True)
                    return False, None, str(e)

            has_access, conflict, error_msg = await sync_to_async(
                check_permissions, thread_sensitive=True
            )()

            if not has_access:
                yield f'data: {{"type": "error", "message": "{error_msg}"}}\n\n'
                return

            # Send initial connection event
            yield f'data: {{"type": "connected", "conflict_id": "{conflict_id}"}}\n\n'

            # Track last check timestamp
            last_check = datetime.now(timezone.utc)
            consecutive_errors = 0
            max_errors = 3
            max_duration = 600  # 10 minutes

            start_time = datetime.now(timezone.utc)

            while True:
                try:
                    # Check if connection exceeded max duration
                    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                    if elapsed > max_duration:
                        yield 'data: {"type": "timeout", "message": "Connection timeout - please refresh"}\n\n'
                        break

                    # Non-blocking event query with thread-safe database access
                    def get_new_events():
                        """
                        Fetch new events since last check.

                        Returns:
                            dict: Dictionary of event lists by type
                        """
                        events = {
                            "new_comments": [],
                            "revote_proposed": [],
                            "revote_accepted": [],
                            "revote_decisions": [],
                            "consensus_reached": None,
                            "discussion_votes_updated": [],
                        }

                        # Get new comments
                        new_comments = (
                            ConflictComment.objects.filter(
                                conflict_id=conflict_id,
                                created_at__gt=last_check,
                                is_deleted=False,
                            )
                            .select_related("author", "parent")
                            .order_by("created_at")
                        )

                        if new_comments.exists():
                            events["new_comments"] = list(new_comments)

                        # Get new revote proposals
                        new_proposals = (
                            RevoteProposal.objects.filter(
                                conflict_id=conflict_id, proposed_at__gt=last_check
                            )
                            .select_related("proposed_by")
                            .prefetch_related("accepted_by")
                        )

                        for proposal in new_proposals:
                            events["revote_proposed"].append(proposal)

                            # Check if proposal was just accepted (all reviewers accepted)
                            if proposal.all_accepted:
                                events["revote_accepted"].append(proposal)

                        # Check if conflict was just resolved
                        updated_conflict = (
                            ConflictResolution.objects.filter(
                                id=conflict_id,
                                resolved_at__gt=last_check,
                                status="RESOLVED",
                            )
                            .select_related("final_decision")
                            .first()
                        )

                        if updated_conflict:
                            events["consensus_reached"] = updated_conflict

                        # Get updated discussion votes (new votes or new responses)
                        from apps.review_results.models import InDiscussionVote

                        updated_votes = InDiscussionVote.objects.filter(
                            conflict_id=conflict_id,
                            created_at__gt=last_check,
                        ).select_related("proposed_by", "initiating_comment")

                        # Also check for new responses on existing votes
                        votes_with_new_responses = (
                            InDiscussionVote.objects.filter(
                                conflict_id=conflict_id,
                                responses__responded_at__gt=last_check,
                            )
                            .distinct()
                            .select_related("proposed_by", "initiating_comment")
                        )

                        all_updated_vote_ids = set()
                        for v in updated_votes:
                            all_updated_vote_ids.add(v.id)
                            events["discussion_votes_updated"].append(v)
                        for v in votes_with_new_responses:
                            if v.id not in all_updated_vote_ids:
                                events["discussion_votes_updated"].append(v)

                        return events

                    events = await sync_to_async(
                        get_new_events, thread_sensitive=True
                    )()

                    # Broadcast new comment events
                    for comment in events["new_comments"]:
                        # Serialize comment
                        comment_data = ConflictCommentSerializer(comment).data
                        event_data = {"comment": comment_data}
                        yield "event: new_comment\n"
                        yield f"data: {json.dumps(event_data)}\n\n"

                    # Broadcast revote proposed events
                    for proposal in events["revote_proposed"]:
                        proposal_data = RevoteProposalSerializer(proposal).data
                        event_data = {"proposal": proposal_data}
                        yield "event: revote_proposed\n"
                        yield f"data: {json.dumps(event_data)}\n\n"

                    # Broadcast revote accepted events
                    for proposal in events["revote_accepted"]:
                        proposal_data = RevoteProposalSerializer(proposal).data
                        event_data = {"proposal": proposal_data}
                        yield "event: revote_accepted\n"
                        yield f"data: {json.dumps(event_data)}\n\n"

                    # Broadcast discussion vote events
                    for vote in events["discussion_votes_updated"]:
                        from apps.review_results.serializers import (
                            InDiscussionVoteSerializer,
                        )

                        vote_data = InDiscussionVoteSerializer(vote).data
                        event_data = {"vote": vote_data}
                        yield "event: discussion_vote_updated\n"
                        yield f"data: {json.dumps(event_data)}\n\n"

                    # Broadcast consensus reached event
                    if events["consensus_reached"]:
                        resolved_conflict = events["consensus_reached"]
                        event_data = {
                            "conflict_id": str(conflict_id),
                            "final_decision": resolved_conflict.final_decision.decision
                            if resolved_conflict.final_decision
                            else None,
                            "resolved_at": resolved_conflict.resolved_at.isoformat()
                            if resolved_conflict.resolved_at
                            else None,
                        }
                        yield "event: consensus_reached\n"
                        yield f"data: {json.dumps(event_data)}\n\n"

                        # Close connection after consensus reached
                        yield 'data: {"type": "complete", "message": "Consensus reached"}\n\n'
                        break

                    # Update last check timestamp
                    last_check = datetime.now(timezone.utc)
                    consecutive_errors = 0  # Reset error count on success

                    # Send keepalive comment every 30 seconds
                    yield ": keepalive\n\n"

                    # Wait before next check (non-blocking)
                    await asyncio.sleep(2.0)  # Check every 2 seconds

                except Exception as e:
                    consecutive_errors += 1
                    logger.error(
                        f"SSE error for conflict {conflict_id}: {e}",
                        exc_info=True,
                        extra={
                            "conflict_id": str(conflict_id),
                            "user_id": str(request.user.id),
                        },
                    )

                    if consecutive_errors >= max_errors:
                        yield 'data: {"type": "error", "message": "Too many errors, closing connection"}\n\n'
                        break

                    # Brief wait before retry
                    await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            # Client disconnected
            logger.info(
                f"SSE client disconnected for conflict {conflict_id}",
                extra={
                    "conflict_id": str(conflict_id),
                    "user_id": str(request.user.id),
                },
            )
            raise

        except Exception as e:
            logger.error(
                f"SSE generator error for conflict {conflict_id}: {e}",
                exc_info=True,
                extra={
                    "conflict_id": str(conflict_id),
                    "user_id": str(request.user.id),
                },
            )
            yield f'data: {{"type": "error", "message": "Stream error: {str(e)}"}}\n\n'

    # Return streaming response with SSE headers
    response = StreamingHttpResponse(
        event_generator(),
        content_type="text/event-stream",
    )

    # SSE-specific headers
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # Disable Nginx buffering

    return response
