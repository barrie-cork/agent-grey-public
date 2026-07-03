"""Conflict-resolution API views for the review_results app.

AJAX/JSON endpoints for the Workflow #2 conflict lifecycle: listing conflicts,
conflict detail, discussion comments, resolution, and arbitration.
"""

import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, JsonResponse
from django.views import View

from apps.core.utils.error_responses import error_response as make_error_response
from apps.organisation.models import OrganisationMembership

logger = logging.getLogger(__name__)


class ConflictListAPIView(LoginRequiredMixin, View):
    """
    API endpoint for listing conflicts in a session.

    GET /api/conflicts/?session_id={uuid}

    Response:
        {
            "success": true,
            "conflicts": [
                {
                    "id": "uuid",
                    "result": {...},
                    "conflict_type": "INCLUDE_EXCLUDE",
                    "status": "PENDING",
                    "detected_at": "...",
                    "conflicting_decisions": [...]
                }
            ]
        }
    """

    def get(self, request):
        """List all conflicts for a session."""
        try:
            from apps.review_manager.models import SearchSession
            from apps.review_results.models import ConflictResolution

            session_id = request.GET.get("session_id")

            if not session_id:
                return JsonResponse(
                    {"success": False, "error": "session_id is required"}, status=400
                )

            # Get session
            try:
                session = SearchSession.objects.get(id=session_id)
            except SearchSession.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Session not found"}, status=404
                )

            # Check permissions
            user_membership = OrganisationMembership.objects.filter(
                user=request.user
            ).first()
            user_org = user_membership.organisation if user_membership else None
            if request.user != session.owner and user_org != session.organisation:
                return JsonResponse(
                    {"success": False, "error": "Permission denied"}, status=403
                )

            # Get conflicts
            conflicts = (
                ConflictResolution.objects.filter(result__session=session)
                .select_related("result")
                .prefetch_related(
                    "conflicting_decisions",
                    "conflicting_decisions__reviewer",
                )
                .order_by("-detected_at")
            )

            # Serialize conflicts
            conflicts_data = []
            for conflict in conflicts:
                conflict_data = {
                    "id": str(conflict.id),
                    "conflict_type": conflict.conflict_type,
                    "status": conflict.status,
                    "detected_at": conflict.detected_at.isoformat(),
                    "result": {
                        "id": str(conflict.result.id),
                        "title": conflict.result.title,
                        "snippet": conflict.result.snippet,
                        "url": conflict.result.url,
                    },
                }
                conflicts_data.append(conflict_data)

            return JsonResponse(
                {
                    "success": True,
                    "conflicts": conflicts_data,
                    "total": len(conflicts_data),
                }
            )

        except Exception as e:
            logger.error(f"Conflict list error: {str(e)}")
            return JsonResponse(
                {"success": False, "error": "An internal error occurred"}, status=500
            )

    def dispatch(self, request, *args, **kwargs):
        """Handle GET requests only."""
        if request.method == "GET":
            return self.get(request)
        return make_error_response(Exception("Method not allowed"), status_code=405)


class ConflictDetailAPIView(LoginRequiredMixin, View):
    """
    API endpoint for getting detailed conflict information.

    GET /api/conflicts/{id}/

    Response:
        {
            "success": true,
            "conflict": {
                "id": "uuid",
                "result": {...},
                "conflict_type": "INCLUDE_EXCLUDE",
                "status": "PENDING",
                "detected_at": "...",
                "conflicting_decisions": [
                    {
                        "id": "uuid",
                        "reviewer": {...},
                        "decision": "INCLUDE",
                        "notes": "...",
                        "confidence_level": 3
                    }
                ],
                "comments": [...],
                "resolution_method": "CONSENSUS"
            }
        }
    """

    def get(self, request, conflict_id):
        """Get detailed conflict information."""
        try:
            from apps.review_results.models import ConflictComment, ConflictResolution

            # Get conflict
            try:
                conflict = (
                    ConflictResolution.objects.select_related(
                        "result",
                        "organisation",
                    )
                    .prefetch_related(
                        "conflicting_decisions",
                        "conflicting_decisions__reviewer",
                    )
                    .get(id=conflict_id)
                )
            except ConflictResolution.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Conflict not found"}, status=404
                )

            # Check permissions
            user_membership = OrganisationMembership.objects.filter(
                user=request.user
            ).first()
            user_org = user_membership.organisation if user_membership else None
            session_owner = conflict.result.session.owner

            if request.user != session_owner and user_org != conflict.organisation:
                return JsonResponse(
                    {"success": False, "error": "Permission denied"}, status=403
                )

            # Serialize decisions
            decisions_data = []
            for decision in conflict.conflicting_decisions.all():
                decision_data = {
                    "id": str(decision.id),
                    "decision": decision.decision,
                    "exclusion_reason": decision.exclusion_reason,
                    "confidence_level": decision.confidence_level,
                    "notes": decision.notes,
                    "decided_at": decision.decided_at.isoformat(),
                    "reviewer": {
                        "id": str(decision.reviewer.id),
                        "username": decision.reviewer.username,
                        "email": decision.reviewer.email,
                    },
                }
                decisions_data.append(decision_data)

            # Get comments
            comments = (
                ConflictComment.objects.filter(conflict=conflict, is_deleted=False)
                .select_related("author")
                .order_by("created_at")
            )

            comments_data = []
            for comment in comments:
                comment_data = {
                    "id": str(comment.id),
                    "content": comment.content,
                    "content_html": comment.content_html,
                    "created_at": comment.created_at.isoformat(),
                    "updated_at": comment.updated_at.isoformat(),
                    "is_edited": comment.is_edited,
                    "parent_id": str(comment.parent.id) if comment.parent else None,
                    "author": {
                        "id": str(comment.author.id) if comment.author else None,
                        "username": comment.author.username
                        if comment.author
                        else "Deleted User",
                        "email": comment.author.email if comment.author else "",
                    }
                    if comment.author
                    else None,
                }
                comments_data.append(comment_data)

            # Serialize conflict
            conflict_data = {
                "id": str(conflict.id),
                "conflict_type": conflict.conflict_type,
                "status": conflict.status,
                "detected_at": conflict.detected_at.isoformat(),
                "resolution_method": conflict.resolution_method,
                "result": {
                    "id": str(conflict.result.id),
                    "title": conflict.result.title,
                    "snippet": conflict.result.snippet,
                    "url": conflict.result.url,
                    "source_organization": conflict.result.source_organization,
                    "domain": conflict.result.domain,
                },
                "conflicting_decisions": decisions_data,
                "comments": comments_data,
            }

            return JsonResponse({"success": True, "conflict": conflict_data})

        except Exception as e:
            logger.error(f"Conflict detail error: {str(e)}")
            return JsonResponse(
                {"success": False, "error": "An internal error occurred"}, status=500
            )

    def dispatch(self, request, *args, **kwargs):
        """Handle GET requests only."""
        if request.method == "GET":
            return self.get(request, kwargs.get("conflict_id"))
        return make_error_response(Exception("Method not allowed"), status_code=405)


class ConflictDiscussAPIView(LoginRequiredMixin, View):
    """
    API endpoint for adding comments to a conflict discussion.

    POST /api/conflicts/{id}/discuss/
    Request Body:
        {
            "content": "Comment text (markdown supported)",
            "parent_id": "uuid" # optional, for threaded replies
        }

    Response:
        {
            "success": true,
            "comment": {
                "id": "uuid",
                "content": "...",
                "content_html": "...",
                "created_at": "...",
                "author": {...}
            }
        }
    """

    def post(self, request, conflict_id):
        """Add a comment to conflict discussion."""
        try:
            import json

            from apps.review_results.models import ConflictComment, ConflictResolution

            # Parse request body
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse(
                    {"success": False, "error": "Invalid JSON in request body"},
                    status=400,
                )

            content = body.get("content", "").strip()
            parent_id = body.get("parent_id")

            if not content:
                return JsonResponse(
                    {"success": False, "error": "content is required"}, status=400
                )

            # Get conflict
            try:
                conflict = ConflictResolution.objects.select_related(
                    "organisation"
                ).get(id=conflict_id)
            except ConflictResolution.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Conflict not found"}, status=404
                )

            # Check permissions
            user_membership = OrganisationMembership.objects.filter(
                user=request.user
            ).first()
            user_org = user_membership.organisation if user_membership else None
            session_owner = conflict.result.session.owner

            if request.user != session_owner and user_org != conflict.organisation:
                return JsonResponse(
                    {"success": False, "error": "Permission denied"}, status=403
                )

            # Get parent comment if specified
            parent = None
            if parent_id:
                try:
                    parent = ConflictComment.objects.get(
                        id=parent_id, conflict=conflict
                    )
                except ConflictComment.DoesNotExist:
                    return JsonResponse(
                        {"success": False, "error": "Parent comment not found"},
                        status=404,
                    )

            # Render markdown to HTML (server-side for security)
            import markdown

            md = markdown.Markdown(extensions=["extra", "nl2br"])
            content_html = md.convert(content)

            # Create comment
            comment = ConflictComment.objects.create(
                conflict=conflict,
                author=request.user,
                parent=parent,
                content=content,
                content_html=content_html,
            )

            # Serialize comment
            comment_data = {
                "id": str(comment.id),
                "content": comment.content,
                "content_html": comment.content_html,
                "created_at": comment.created_at.isoformat(),
                "updated_at": comment.updated_at.isoformat(),
                "is_edited": comment.is_edited,
                "parent_id": str(comment.parent.id) if comment.parent else None,
                "author": {
                    "id": str(comment.author.id),
                    "username": comment.author.username,
                    "email": comment.author.email,
                },
            }

            return JsonResponse(
                {
                    "success": True,
                    "comment": comment_data,
                    "message": "Comment added successfully",
                }
            )

        except Exception as e:
            logger.error(f"Add comment error: {str(e)}")
            return JsonResponse(
                {"success": False, "error": "An internal error occurred"}, status=500
            )

    def dispatch(self, request, *args, **kwargs):
        """Handle POST requests only."""
        if request.method == "POST":
            return self.post(request, kwargs.get("conflict_id"))
        return make_error_response(Exception("Method not allowed"), status_code=405)


class ConflictResolveAPIView(LoginRequiredMixin, View):
    """
    API endpoint for marking a conflict as resolved.

    POST /api/conflicts/{id}/resolve/
    Request Body:
        {
            "resolution_notes": "optional notes about resolution"
        }

    Response:
        {
            "success": true,
            "conflict": {
                "id": "uuid",
                "status": "RESOLVED",
                "resolved_at": "...",
                "resolved_by": {...}
            }
        }
    """

    def post(self, request, conflict_id):
        """Mark conflict as resolved (CONSENSUS method only)."""
        try:
            import json

            from django.utils import timezone

            from apps.review_results.models import ConflictResolution

            # Parse request body
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                body = {}

            resolution_notes = body.get("resolution_notes", "")

            # Get conflict
            try:
                conflict = ConflictResolution.objects.select_related(
                    "organisation"
                ).get(id=conflict_id)
            except ConflictResolution.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Conflict not found"}, status=404
                )

            # Check permissions
            user_membership = OrganisationMembership.objects.filter(
                user=request.user
            ).first()
            user_org = user_membership.organisation if user_membership else None
            session_owner = conflict.result.session.owner

            if request.user != session_owner and user_org != conflict.organisation:
                return JsonResponse(
                    {"success": False, "error": "Permission denied"}, status=403
                )

            # Check if conflict can be resolved via consensus
            if conflict.resolution_method not in ["CONSENSUS", None]:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Cannot resolve via discussion - resolution method is {conflict.resolution_method}",
                    },
                    status=400,
                )

            if conflict.status == "RESOLVED":
                return JsonResponse(
                    {"success": False, "error": "Conflict already resolved"}, status=400
                )

            # Mark as resolved
            conflict.status = "RESOLVED"
            conflict.resolved_at = timezone.now()
            conflict.resolved_by = request.user
            conflict.resolution_notes = resolution_notes
            conflict.save(
                update_fields=[
                    "status",
                    "resolved_at",
                    "resolved_by",
                    "resolution_notes",
                ]
            )

            # Serialize conflict
            conflict_data = {
                "id": str(conflict.id),
                "status": conflict.status,
                "resolved_at": conflict.resolved_at.isoformat(),
                "resolved_by": {
                    "id": str(conflict.resolved_by.id),
                    "username": conflict.resolved_by.username,
                    "email": conflict.resolved_by.email,
                },
                "resolution_notes": conflict.resolution_notes,
            }

            return JsonResponse(
                {
                    "success": True,
                    "conflict": conflict_data,
                    "message": "Conflict marked as resolved",
                }
            )

        except Exception as e:
            logger.error(f"Resolve conflict error: {str(e)}")
            return JsonResponse(
                {"success": False, "error": "An internal error occurred"}, status=500
            )

    def dispatch(self, request, *args, **kwargs):
        """Handle POST requests only."""
        if request.method == "POST":
            return self.post(request, kwargs.get("conflict_id"))
        return make_error_response(Exception("Method not allowed"), status_code=405)


class ConflictArbitrateAPIView(LoginRequiredMixin, View):
    """
    API endpoint for arbitration-based conflict resolution.

    POST /api/conflicts/{id}/arbitrate/
    Request Body:
        {
            "final_decision": "INCLUDE" | "EXCLUDE" | "MAYBE",
            "resolution_notes": "optional notes about arbitration"
        }

    Response:
        {
            "success": true,
            "conflict": {
                "id": "uuid",
                "status": "RESOLVED",
                "final_decision": "INCLUDE",
                "resolved_at": "...",
                "resolved_by": {...}
            }
        }

    Permissions:
        - LEAD_ARBITRATION: Session owner (lead reviewer) can arbitrate
        - DESIGNATED_ARBITRATOR: Only assigned arbitrator can arbitrate
        - MAJORITY: Session owner or arbitrator can apply majority decision
    """

    def post(self, request: HttpRequest, conflict_id: str) -> JsonResponse:
        """Handle arbitration submission."""
        try:
            import json

            from django.utils import timezone

            from apps.review_results.models import (
                ConflictResolution,
                ReviewerAssignment,
            )

            # Parse request body
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse(
                    {"success": False, "error": "Invalid JSON in request body"},
                    status=400,
                )

            final_decision = body.get("final_decision")
            resolution_notes = body.get("resolution_notes", "")

            # Validate final_decision
            if not final_decision or final_decision not in [
                "INCLUDE",
                "EXCLUDE",
                "MAYBE",
            ]:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "final_decision must be INCLUDE, EXCLUDE, or MAYBE",
                    },
                    status=400,
                )

            # Validate resolution_notes type and length
            if resolution_notes is not None and not isinstance(resolution_notes, str):
                return JsonResponse(
                    {"success": False, "error": "resolution_notes must be a string"},
                    status=400,
                )
            if resolution_notes and len(resolution_notes) > 5000:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "resolution_notes exceeds maximum length (5000 characters)",
                    },
                    status=400,
                )

            # Get conflict
            try:
                conflict = ConflictResolution.objects.select_related(
                    "organisation", "result", "result__session"
                ).get(id=conflict_id)
            except ConflictResolution.DoesNotExist:
                return JsonResponse(
                    {"success": False, "error": "Conflict not found"}, status=404
                )

            # Check if already resolved
            if conflict.status == "RESOLVED":
                return JsonResponse(
                    {"success": False, "error": "Conflict already resolved"}, status=400
                )

            # Get resolution method from session configuration
            session = conflict.result.session
            resolution_method = (
                session.current_configuration.conflict_resolution_method
                if hasattr(session, "current_configuration")
                else "LEAD_ARBITRATION"
            )

            # Permission checks based on resolution method
            is_session_owner = session.owner == request.user

            # Check if user is designated arbitrator for this result
            is_designated_arbitrator = ReviewerAssignment.objects.filter(
                result=conflict.result,
                reviewer=request.user,
                role="ARBITRATOR",
                is_active=True,
            ).exists()

            # Check permissions based on resolution method
            can_arbitrate = False

            if resolution_method == "LEAD_ARBITRATION":
                # Only session owner (lead reviewer) can arbitrate
                can_arbitrate = is_session_owner
            elif resolution_method == "DESIGNATED_ARBITRATOR":
                # Only designated arbitrator can arbitrate
                can_arbitrate = is_designated_arbitrator
            elif resolution_method == "MAJORITY":
                # Session owner or arbitrator can apply majority decision
                can_arbitrate = is_session_owner or is_designated_arbitrator
            else:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Arbitration not supported for resolution method: {resolution_method}",
                    },
                    status=400,
                )

            if not can_arbitrate:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Permission denied: You are not authorized to arbitrate this conflict",
                    },
                    status=403,
                )

            # Check organisation membership for non-owner arbitrators
            if not is_session_owner:
                user_membership = OrganisationMembership.objects.filter(
                    user=request.user
                ).first()
                user_org = user_membership.organisation if user_membership else None
                if user_org != conflict.organisation:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Permission denied: Organisation mismatch",
                        },
                        status=403,
                    )

            # Create resolution decision (link to one of the conflicting decisions or create new one)
            # For simplicity, we'll just store the final_decision in the conflict record
            # In a full implementation, you might want to create a new ReviewerDecision record

            # Mark as resolved
            conflict.status = "RESOLVED"
            conflict.resolution_method = resolution_method
            conflict.resolved_at = timezone.now()
            conflict.resolved_by = request.user
            conflict.resolution_notes = resolution_notes

            # Store final decision (we'll add this as a text field since final_decision FK expects ReviewerDecision)
            # For now, store in resolution_notes if not already present
            if resolution_notes:
                conflict.resolution_notes = (
                    f"Final Decision: {final_decision}\n\n{resolution_notes}"
                )
            else:
                conflict.resolution_notes = f"Final Decision: {final_decision}"

            conflict.save(
                update_fields=[
                    "status",
                    "resolution_method",
                    "resolved_at",
                    "resolved_by",
                    "resolution_notes",
                ]
            )

            # Serialize conflict
            conflict_data = {
                "id": str(conflict.id),
                "status": conflict.status,
                "resolution_method": conflict.resolution_method,
                "final_decision": final_decision,
                "resolved_at": conflict.resolved_at.isoformat(),
                "resolved_by": {
                    "id": str(conflict.resolved_by.id),
                    "username": conflict.resolved_by.username,
                    "email": conflict.resolved_by.email,
                },
                "resolution_notes": conflict.resolution_notes,
            }

            logger.info(
                f"Conflict {conflict.id} resolved via {resolution_method} by {request.user.username} "
                f"with decision: {final_decision}"
            )

            return JsonResponse(
                {
                    "success": True,
                    "conflict": conflict_data,
                    "message": f"Conflict resolved successfully via {resolution_method}",
                }
            )

        except Exception as e:
            logger.error(f"Arbitrate conflict error: {str(e)}", exc_info=True)
            return JsonResponse(
                {"success": False, "error": "An internal error occurred"}, status=500
            )

    def dispatch(self, request, *args, **kwargs):
        """Handle POST requests only."""
        if request.method == "POST":
            return self.post(request, kwargs.get("conflict_id") or "")
        return make_error_response(Exception("Method not allowed"), status_code=405)
