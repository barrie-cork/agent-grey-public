"""
Views for managing review session invitations.

Provides user interface for:
- Viewing pending invitations
- Accepting invitations via magic links
- Declining invitations

Supports the dual-screening workflow by enabling invited reviewers to
accept invitations and gain access to shared review sessions.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.review_manager.services.invitation_service import ReviewInvitationService

logger = logging.getLogger(__name__)


class PendingInvitationsView(LoginRequiredMixin, TemplateView):
    """
    Display all pending invitations for the current user.

    Shows invitations sent to the user's email address that have not yet
    been accepted or declined. Enables users to review and respond to
    review session invitations.
    """

    template_name = "review_manager/pending_invitations.html"

    def get_context_data(self, **kwargs):
        """Add pending invitations to template context."""
        context = super().get_context_data(**kwargs)

        invitation_service = ReviewInvitationService()
        pending_invitations = invitation_service.get_pending_invitations(
            self.request.user
        )

        context["pending_invitations"] = pending_invitations

        return context


class AcceptInvitationView(LoginRequiredMixin, View):
    """
    Accept a review invitation via magic link token.

    Validates the invitation token, verifies the user's email matches,
    and accepts the invitation. On success, redirects to the session
    detail page. On failure, redirects to pending invitations with
    an error message.
    """

    def get(self, request, token):
        """Process invitation acceptance."""
        invitation_service = ReviewInvitationService()

        success, error_message, invitation = invitation_service.accept_invitation(
            token=token, user=request.user
        )

        if success:
            if invitation is None:
                logger.error(
                    "accept_invitation returned success=True but invitation is None "
                    "for token %s",
                    token[:8],
                )
                messages.error(request, "An unexpected error occurred.")
                return redirect("review_manager:pending_invitations")

            messages.success(
                request,
                f"You have successfully joined the review session: {invitation.session.title}",
            )
            logger.info(
                f"User {request.user.id} accepted invitation {invitation.id} "
                f"to session {invitation.session.id}"
            )
            return redirect(
                "review_manager:session_detail", session_id=invitation.session.id
            )
        else:
            # Log the failure
            logger.warning(
                f"User {request.user.id} failed to accept invitation with token {token[:8]}...: "
                f"{error_message}"
            )

            messages.error(
                request,
                error_message
                or "Could not accept invitation. The invitation may be expired or invalid.",
            )
            return redirect("review_manager:pending_invitations")


class DeclineInvitationView(LoginRequiredMixin, View):
    """
    Decline a review invitation.

    Marks the invitation as declined. Requires POST method for CSRF
    protection. Redirects to pending invitations page with confirmation.
    """

    def post(self, request, token):
        """Process invitation decline."""
        invitation_service = ReviewInvitationService()

        success, error_message, invitation = invitation_service.decline_invitation(
            token=token, user=request.user
        )

        if success:
            if invitation is None:
                logger.error(
                    "decline_invitation returned success=True but invitation is None "
                    "for token %s",
                    token[:8],
                )
                messages.error(request, "An unexpected error occurred.")
                return redirect("review_manager:pending_invitations")

            messages.success(request, "Invitation declined successfully.")
            logger.info(f"User {request.user.id} declined invitation {invitation.id}")
        else:
            logger.warning(
                f"User {request.user.id} failed to decline invitation with token {token[:8]}...: "
                f"{error_message}"
            )

            messages.error(request, error_message or "Could not decline invitation.")

        return redirect("review_manager:pending_invitations")
