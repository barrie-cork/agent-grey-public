"""
Views for external reviewer approval workflow.

Provides Information Specialist interface for:
- Viewing pending external reviewer approvals
- Approving external reviewers
- Rejecting external reviewers with reason
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from apps.organisation.models import OrganisationMembership
from .models import SearchSession, SessionActivity, ReviewConfiguration
from .services.invitation_service import ReviewInvitationService
from .utils import requires_is_approval_for_external

logger = logging.getLogger(__name__)


class PendingExternalReviewerApprovalsView(LoginRequiredMixin, ListView):
    """
    List sessions with pending external reviewer approvals.

    Accessible only by Information Specialists.
    """

    template_name = "review_manager/pending_approvals.html"
    context_object_name = "pending_sessions"
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        """Check user has IS permission."""
        # Get user's organisation memberships
        memberships = OrganisationMembership.objects.filter(
            user=request.user, is_active=True, role="INFORMATION_SPECIALIST"
        )

        if not memberships.exists():
            raise PermissionDenied(
                "You must be an Information Specialist to access this page."
            )

        # Store IS memberships for queryset filtering
        self.is_memberships = memberships
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        """Get sessions with pending external reviewer approvals."""
        # Get organisations where user is IS
        org_ids = self.is_memberships.values_list("organisation_id", flat=True)

        # Find configurations with pending external reviewers
        return (
            ReviewConfiguration.objects.filter(
                organisation__in=org_ids,
                external_reviewers_pending_approval__isnull=False,
                external_reviewers_approved=False,
                session__status__in=["ready_for_review", "under_review"],
            )
            .select_related("session", "session__owner", "organisation")
            .order_by("-effective_from")
        )

    def get_context_data(self, **kwargs):
        """Add additional context."""
        context = super().get_context_data(**kwargs)

        # Process pending sessions to extract reviewer details
        for config in context["pending_sessions"]:
            config.pending_count = len(config.external_reviewers_pending_approval)
            config.pending_emails = [
                reviewer.get("email")
                for reviewer in config.external_reviewers_pending_approval
            ]

        context["approval_required"] = requires_is_approval_for_external()
        return context


class ApproveExternalReviewersView(LoginRequiredMixin, View):
    """
    Approve external reviewers and send invitations.

    POST only, requires IS permission.
    """

    def post(self, request, session_id):
        """Handle approval of external reviewers."""
        session = get_object_or_404(SearchSession, id=session_id)
        config = session.current_configuration

        if not config:
            messages.error(request, "No review configuration found for this session.")
            return redirect("review_manager:session_detail", session_id=session.id)

        # Verify user is IS for this organisation
        if not OrganisationMembership.objects.filter(
            user=request.user,
            organisation=session.organisation,
            is_active=True,
            role="INFORMATION_SPECIALIST",
        ).exists():
            raise PermissionDenied(
                "You must be an Information Specialist for this organisation to approve reviewers."
            )

        # Check there are pending reviewers
        if not config.external_reviewers_pending_approval:
            messages.warning(
                request, "No external reviewers pending approval for this session."
            )
            return redirect("review_manager:session_detail", session_id=session.id)

        external_reviewers = config.external_reviewers_pending_approval

        with transaction.atomic():
            # Update configuration
            config.external_reviewers_approved = True
            config.external_reviewers_approved_by = request.user
            config.external_reviewers_approved_at = timezone.now()
            config.external_reviewers_pending_approval = []  # Clear pending
            config.save()

            # Transform reviewers for invitation service
            invitee_data = [
                {
                    "email": reviewer.get("email"),
                    "name": f"{reviewer.get('first_name', '')} {reviewer.get('last_name', '')}".strip(),
                }
                for reviewer in external_reviewers
                if reviewer.get("email")
            ]

            # Send invitations
            invitation_service = ReviewInvitationService()
            created_invitations, error_messages = invitation_service.create_invitations(
                session=session,
                invitee_data=invitee_data,
                inviter=session.owner,
                request=request,
            )

            # Log activity
            SessionActivity.objects.create(
                session=session,
                user=request.user,
                activity_type="external_reviewers_approved",
                description=f"{len(external_reviewers)} external reviewer(s) approved by {request.user.username}",
                metadata={
                    "approved_by": request.user.username,
                    "external_reviewers": external_reviewers,
                    "count": len(external_reviewers),
                    "invitations_sent": len(created_invitations),
                },
            )

            # Send notification to session owner about approved reviewers
            from .services.notification_service import NotificationService

            notification_service = NotificationService()
            notification_service.notify_external_reviewers_approved(
                session, request.user, external_reviewers
            )

            logger.info(
                f"IS {request.user.username} approved {len(external_reviewers)} external reviewer(s) "
                f"for session {session.id}"
            )

            messages.success(
                request,
                f"Approved {len(external_reviewers)} external reviewer(s). "
                f"{len(created_invitations)} invitation(s) sent.",
            )

            if error_messages:
                for error in error_messages:
                    messages.warning(request, f"Invitation error: {error}")

        # Return appropriate response
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "approved_count": len(external_reviewers),
                    "invitations_sent": len(created_invitations),
                }
            )
        else:
            return redirect("review_manager:pending_approvals")


class RejectExternalReviewersView(LoginRequiredMixin, View):
    """
    Reject external reviewers with reason.

    POST only, requires IS permission.
    """

    def post(self, request, session_id):
        """Handle rejection of external reviewers."""
        session = get_object_or_404(SearchSession, id=session_id)
        config = session.current_configuration

        if not config:
            messages.error(request, "No review configuration found for this session.")
            return redirect("review_manager:session_detail", session_id=session.id)

        # Verify user is IS for this organisation
        if not OrganisationMembership.objects.filter(
            user=request.user,
            organisation=session.organisation,
            is_active=True,
            role="INFORMATION_SPECIALIST",
        ).exists():
            raise PermissionDenied(
                "You must be an Information Specialist for this organisation to reject reviewers."
            )

        # Check there are pending reviewers
        if not config.external_reviewers_pending_approval:
            messages.warning(
                request, "No external reviewers pending approval for this session."
            )
            return redirect("review_manager:session_detail", session_id=session.id)

        # Get rejection reason
        rejection_reason = request.POST.get("rejection_reason", "").strip()
        if not rejection_reason:
            messages.error(request, "Rejection reason is required.")
            return redirect("review_manager:pending_approvals")

        external_reviewers = config.external_reviewers_pending_approval

        with transaction.atomic():
            # Update configuration
            config.external_reviewers_approved = False
            config.external_reviewers_rejected_by = request.user
            config.external_reviewers_rejected_at = timezone.now()
            config.external_reviewers_rejection_reason = rejection_reason
            config.external_reviewers_pending_approval = []  # Clear pending
            config.save()

            # Log activity
            SessionActivity.objects.create(
                session=session,
                user=request.user,
                activity_type="external_reviewers_rejected",
                description=f"{len(external_reviewers)} external reviewer(s) rejected by {request.user.username}: {rejection_reason}",
                metadata={
                    "rejected_by": request.user.username,
                    "external_reviewers": external_reviewers,
                    "count": len(external_reviewers),
                    "rejection_reason": rejection_reason,
                },
            )

            # Send notification to session owner about rejected reviewers
            from .services.notification_service import NotificationService

            notification_service = NotificationService()
            notification_service.notify_external_reviewers_rejected(
                session, request.user, external_reviewers, rejection_reason
            )

            logger.info(
                f"IS {request.user.username} rejected {len(external_reviewers)} external reviewer(s) "
                f"for session {session.id}. Reason: {rejection_reason}"
            )

            messages.success(
                request,
                f"Rejected {len(external_reviewers)} external reviewer(s). "
                f"The session owner has been notified.",
            )

        # Return appropriate response
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "rejected_count": len(external_reviewers),
                    "reason": rejection_reason,
                }
            )
        else:
            return redirect("review_manager:pending_approvals")


class ExternalReviewerDetailsView(LoginRequiredMixin, View):
    """
    Get details of pending external reviewers for a session.

    AJAX endpoint for IS to see reviewer details before approval.
    """

    def get(self, request, session_id):
        """Return external reviewer details as JSON."""
        session = get_object_or_404(SearchSession, id=session_id)
        config = session.current_configuration

        # Verify user is IS for this organisation
        if not OrganisationMembership.objects.filter(
            user=request.user,
            organisation=session.organisation,
            is_active=True,
            role="INFORMATION_SPECIALIST",
        ).exists():
            return JsonResponse({"error": "Permission denied"}, status=403)

        # Get pending reviewers
        external_reviewers = config.external_reviewers_pending_approval or []

        return JsonResponse(
            {
                "session_id": str(session.id),
                "session_title": session.title,
                "session_owner": session.owner.username,
                "organisation": session.organisation.name
                if session.organisation
                else None,
                "pending_reviewers": external_reviewers,
                "count": len(external_reviewers),
            }
        )
