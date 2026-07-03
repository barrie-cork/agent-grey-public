"""
Review invitation service for sharing sessions with external reviewers.

Provides functionality for:
- Creating and sending reviewer invitations via magic links
- Accepting and declining invitations
- Managing invitation lifecycle (expiry, revocation)
- Tracking pending invitations per user

Follows the BaseService pattern from apps/core/services/base.py.
"""

import logging
from typing import Dict, List, Optional, Tuple

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.core.services.base import BaseService
from apps.review_manager.models import ReviewInvitation, SearchSession, SessionActivity

User = get_user_model()
logger = logging.getLogger(__name__)


class ReviewInvitationService(BaseService):
    """
    Service for managing review session invitations.

    Enables session owners to invite external reviewers via email magic links.
    Handles invitation creation, acceptance, decline, and expiry.
    """

    SERVICE_NAME = "ReviewInvitationService"
    SERVICE_VERSION = "1.0.0"

    def _initialize(self) -> None:
        """Initialise review invitation service resources."""
        # No special initialisation needed
        pass

    def health_check(self) -> bool:
        """
        Check if review invitation service is healthy.

        Returns:
            bool: True if service is operational
        """
        try:
            # Verify we can access the database
            ReviewInvitation.objects.count()
            return True
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def get_default_config(self) -> Dict:
        """Get default configuration for review invitation service."""
        return {
            "cache_timeout": 300,  # 5 minutes
            "max_invitations_per_session": 10,
            "invitation_expiry_days": 7,
        }

    def create_invitations(
        self,
        session: SearchSession,
        invitee_data: List[Dict[str, str]],
        inviter: User,
        request: Optional[HttpRequest] = None,
    ) -> Tuple[List[ReviewInvitation], List[str]]:
        """
        Create and send invitations to multiple reviewers.

        Args:
            session: SearchSession to share
            invitee_data: List of dictionaries with 'email' and 'name' keys
            inviter: User who is sending the invitations
            request: Optional HttpRequest for generating absolute URLs

        Returns:
            Tuple of (created_invitations, error_messages)

        Example:
            invitee_data = [
                {'email': 'reviewer@example.com', 'name': 'Dr. Smith'},
                {'email': 'expert@university.edu', 'name': 'Prof. Jones'}
            ]
        """
        created_invitations = []
        error_messages = []

        # Validate max invitations limit
        existing_count = session.reviewer_invitations.filter(
            status=ReviewInvitation.STATUS_PENDING
        ).count()

        max_invitations = self.config.get("max_invitations_per_session", 10)
        if existing_count + len(invitee_data) > max_invitations:
            error_messages.append(
                f"Cannot create invitations: Would exceed maximum of {max_invitations} "
                f"pending invitations per session"
            )
            return (created_invitations, error_messages)

        for invitee in invitee_data:
            email = invitee.get("email")
            name = invitee.get("name", "")

            if not email:
                error_messages.append("Skipping invitee without email")
                continue

            # Use get_or_create to atomically guard against TOCTOU races where
            # two concurrent signal handlers both pass a prior existence check.
            try:
                with transaction.atomic():
                    invitation, created = ReviewInvitation.objects.get_or_create(
                        session=session,
                        invitee_email=email,
                        defaults={
                            "inviter": inviter,
                            "invitee_name": name,
                        },
                    )

                    if not created:
                        if invitation.status == ReviewInvitation.STATUS_PENDING:
                            error_messages.append(
                                f"Pending invitation already exists for {email}"
                            )
                        elif invitation.status == ReviewInvitation.STATUS_ACCEPTED:
                            error_messages.append(
                                f"{email} has already accepted an invitation"
                            )
                        continue

                    # Send invitation email for newly created invitation
                    self.send_invitation_email(invitation, request)

                    created_invitations.append(invitation)
                    logger.info(
                        f"Created invitation {invitation.id} for {email} to session {session.id}"
                    )

            except IntegrityError:
                # Concurrent handler created the invitation first — not an error
                logger.info(
                    f"Invitation for {email} in session {session.id} already created "
                    f"by a concurrent request — skipping"
                )
            except Exception as e:
                error_message = f"Failed to create invitation for {email}: {str(e)}"
                error_messages.append(error_message)
                self._handle_error(
                    e, context={"email": email}, operation="create_invitation"
                )

        return (created_invitations, error_messages)

    def send_invitation_email(
        self, invitation: ReviewInvitation, request: Optional[HttpRequest] = None
    ) -> bool:
        """
        Send invitation email with magic link.

        Args:
            invitation: ReviewInvitation instance
            request: Optional HttpRequest for generating absolute URLs

        Returns:
            bool: True if email sent successfully
        """
        try:
            from apps.review_results.services.email_notification_service import (
                EmailNotificationService,
            )

            email_service = EmailNotificationService()
            return email_service.send_reviewer_invitation(invitation, request)

        except Exception as e:
            self._handle_error(
                e,
                context={"invitation_id": str(invitation.id)},
                operation="send_invitation_email",
            )
            return False

    def accept_invitation(
        self, token: str, user: User
    ) -> Tuple[bool, Optional[str], Optional[ReviewInvitation]]:
        """
        Accept a review invitation.

        Args:
            token: Magic link token
            user: User accepting the invitation

        Returns:
            Tuple of (success, error_message, invitation)
        """
        try:
            invitation = ReviewInvitation.objects.filter(token=token).first()

            if not invitation:
                return (False, "Invalid invitation link", None)

            if not invitation.is_valid():
                if invitation.status == ReviewInvitation.STATUS_EXPIRED:
                    return (False, "This invitation has expired", invitation)
                elif invitation.status == ReviewInvitation.STATUS_REVOKED:
                    return (False, "This invitation has been revoked", invitation)
                elif invitation.status == ReviewInvitation.STATUS_ACCEPTED:
                    return (
                        False,
                        "This invitation has already been accepted",
                        invitation,
                    )
                elif invitation.status == ReviewInvitation.STATUS_DECLINED:
                    return (False, "This invitation has been declined", invitation)
                else:
                    return (False, "This invitation is no longer valid", invitation)

            # SECURITY FIX: ENFORCE email match (no exceptions)
            if user.email != invitation.invitee_email:
                error_msg = (
                    f"Invitation was sent to {invitation.invitee_email}. "
                    f"You must accept with the account registered to that email address. "
                    f"Your current account email is {user.email}."
                )
                logger.warning(
                    f"Email mismatch BLOCKED: User {user.email} tried to accept invitation "
                    f"for {invitation.invitee_email}"
                )
                return (False, error_msg, invitation)

            with transaction.atomic():
                invitation.status = ReviewInvitation.STATUS_ACCEPTED
                invitation.invitee = user
                invitation.responded_at = timezone.now()
                invitation.save(update_fields=["status", "invitee", "responded_at"])

                # SECURITY FIX: Add audit trail logging
                SessionActivity.objects.create(
                    session=invitation.session,
                    user=user,
                    activity_type="INVITATION_ACCEPTED",
                    description=f"{user.username} accepted review invitation",
                    metadata={
                        "invitation_id": str(invitation.id),
                        "inviter": invitation.inviter.username
                        if invitation.inviter
                        else None,
                        "accepted_at": timezone.now().isoformat(),
                    },
                )

                logger.info(
                    f"User {user.id} accepted invitation {invitation.id} "
                    f"to session {invitation.session.id}"
                )

            return (True, None, invitation)

        except Exception as e:
            error_message = "Failed to accept invitation"
            self._handle_error(
                e, context={"token": token[:8]}, operation="accept_invitation"
            )
            return (False, error_message, None)

    def decline_invitation(
        self, token: str, user: User
    ) -> Tuple[bool, Optional[str], Optional[ReviewInvitation]]:
        """
        Decline a review invitation.

        Args:
            token: Magic link token
            user: User declining the invitation

        Returns:
            Tuple of (success, error_message, invitation)
        """
        try:
            invitation = ReviewInvitation.objects.filter(token=token).first()

            if not invitation:
                return (False, "Invalid invitation link", None)

            if invitation.status != ReviewInvitation.STATUS_PENDING:
                return (False, "This invitation cannot be declined", invitation)

            with transaction.atomic():
                invitation.status = ReviewInvitation.STATUS_DECLINED
                invitation.responded_at = timezone.now()
                invitation.save(update_fields=["status", "responded_at"])

                logger.info(
                    f"User {user.id} declined invitation {invitation.id} "
                    f"to session {invitation.session.id}"
                )

            return (True, None, invitation)

        except Exception as e:
            error_message = "Failed to decline invitation"
            self._handle_error(
                e, context={"token": token[:8]}, operation="decline_invitation"
            )
            return (False, error_message, None)

    def get_pending_invitations(self, user: User) -> List[ReviewInvitation]:
        """
        Get all pending invitations for a user.

        Args:
            user: User to get invitations for

        Returns:
            List of pending ReviewInvitation objects
        """
        try:
            invitations = ReviewInvitation.objects.filter(
                invitee_email=user.email, status=ReviewInvitation.STATUS_PENDING
            ).select_related("session", "inviter")

            # Mark expired invitations
            for invitation in invitations:
                if not invitation.is_valid():
                    # is_valid() updates status to EXPIRED if needed
                    pass

            # Re-fetch to get updated statuses
            return list(
                ReviewInvitation.objects.filter(
                    invitee_email=user.email, status=ReviewInvitation.STATUS_PENDING
                ).select_related("session", "inviter")
            )

        except Exception as e:
            self._handle_error(
                e,
                context={"user_id": str(user.id)},
                operation="get_pending_invitations",
            )
            return []

    def revoke_invitation(self, invitation: ReviewInvitation) -> bool:
        """
        Revoke a pending invitation.

        Args:
            invitation: ReviewInvitation to revoke

        Returns:
            bool: True if revoked successfully
        """
        try:
            if invitation.status != ReviewInvitation.STATUS_PENDING:
                logger.warning(
                    f"Cannot revoke invitation {invitation.id} with status {invitation.status}"
                )
                return False

            invitation.status = ReviewInvitation.STATUS_REVOKED
            invitation.save(update_fields=["status"])

            logger.info(f"Revoked invitation {invitation.id}")
            return True

        except Exception as e:
            self._handle_error(
                e,
                context={"invitation_id": str(invitation.id)},
                operation="revoke_invitation",
            )
            return False
