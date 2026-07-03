"""
Invitation service for user onboarding to organisations.

Provides:
- Invitation creation and management
- Email sending with magic links
- Invitation acceptance and validation
"""

from datetime import timedelta
from typing import Dict, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.utils import timezone

from apps.accounts.models import User
from apps.core.services.base import BaseService
from apps.organisation.models import (
    Organisation,
    OrganisationInvitation,
    OrganisationMembership,
)


class InvitationService(BaseService):
    """
    Service for managing organisation invitations.

    Following the BaseService pattern from apps/core/services/base.py.
    """

    SERVICE_NAME = "InvitationService"
    SERVICE_VERSION = "1.0.0"

    def _initialize(self) -> None:
        """Initialize invitation service resources."""
        # No special initialization needed
        pass

    def health_check(self) -> bool:
        """
        Check if invitation service is healthy.

        Returns:
            bool: True if service is operational
        """
        try:
            # Simple database connectivity check
            OrganisationInvitation.objects.count()
            return True
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def get_default_config(self) -> Dict:
        """Get default configuration for invitation service."""
        return {
            "cache_timeout": 300,  # 5 minutes
            "send_email": True,  # Enable/disable email sending
            "from_email": settings.DEFAULT_FROM_EMAIL
            if hasattr(settings, "DEFAULT_FROM_EMAIL")
            else "noreply@agentgrey.app",
        }

    def create_invitation(
        self,
        organisation: Organisation,
        email: str,
        role: str,
        invited_by: User,
        name: str = "",
        request=None,
    ) -> OrganisationInvitation:
        """
        Create a new organisation invitation.

        Args:
            organisation: Organisation to invite user to
            email: Email address of invitee
            role: Role to assign (from OrganisationMembership.ROLE_CHOICES)
            invited_by: User who is sending the invitation
            name: Optional display name for invitee
            request: Optional HTTP request for building absolute URLs

        Returns:
            OrganisationInvitation instance

        Raises:
            ValueError: If invitation already exists or invalid role
        """
        with self._measure_performance("create_invitation"):
            try:
                # SECURITY FIX: Rate limiting (configurable via Constance)
                from apps.review_manager.utils import get_invitation_rate_limit

                rate_limit = get_invitation_rate_limit()
                one_hour_ago = timezone.now() - timedelta(hours=1)
                recent_count = OrganisationInvitation.objects.filter(
                    invited_by=invited_by, created_at__gte=one_hour_ago
                ).count()

                if recent_count >= rate_limit:
                    raise ValidationError(
                        f"Rate limit exceeded. Maximum {rate_limit} invitations per hour. "
                        f"You have sent {recent_count} invitations in the last hour."
                    )

                # Validate role
                valid_roles = [
                    choice[0] for choice in OrganisationMembership.ROLE_CHOICES
                ]
                if role not in valid_roles:
                    raise ValueError(
                        f"Invalid role: {role}. Must be one of {valid_roles}"
                    )

                # Check if user already exists and is a member
                existing_user = User.objects.filter(email=email).first()
                if existing_user:
                    existing_membership = OrganisationMembership.objects.filter(
                        user=existing_user, organisation=organisation, is_active=True
                    ).exists()
                    if existing_membership:
                        raise ValueError(
                            f"User {email} is already a member of {organisation.name}"
                        )

                # Check for pending invitations
                existing_invitation = OrganisationInvitation.objects.filter(
                    organisation=organisation,
                    email=email,
                    status=OrganisationInvitation.STATUS_PENDING,
                ).first()

                if existing_invitation and existing_invitation.is_valid():
                    raise ValueError(f"Pending invitation already exists for {email}")

                # Create invitation
                invitation = OrganisationInvitation.objects.create(
                    organisation=organisation,
                    email=email,
                    name=name,
                    role=role,
                    invited_by=invited_by,
                )

                self.logger.info(
                    f"Created invitation for {email} to {organisation.name} as {role}",
                    extra={
                        "invitation_id": str(invitation.id),
                        "organisation_id": str(organisation.id),
                        "invited_by_id": str(invited_by.id),
                    },
                )

                # Send email
                if self.config.get("send_email", True):
                    self.send_invitation_email(invitation, request)

                return invitation

            except Exception as e:
                self._handle_error(
                    e,
                    operation="create_invitation",
                    context={
                        "email": email,
                        "organisation_id": str(organisation.id),
                        "role": role,
                    },
                )
                raise

    def send_invitation_email(
        self, invitation: OrganisationInvitation, request=None
    ) -> bool:
        """
        Send invitation email with magic link.

        Args:
            invitation: OrganisationInvitation instance
            request: Optional HTTP request for building absolute URLs

        Returns:
            bool: True if email sent successfully
        """
        with self._measure_performance("send_invitation_email"):
            try:
                # Generate magic link
                magic_link = invitation.get_magic_link(request)

                # Render email template
                subject = (
                    f"Invitation to join {invitation.organisation.name} on Agent Grey"
                )

                # For now, use a simple text email (HTML template can be added later)
                message = f"""
Hello {invitation.name or invitation.email},

You have been invited to join {invitation.organisation.name} as a {invitation.get_role_display()}.

Click the link below to accept your invitation:
{magic_link}

This invitation will expire in 7 days.

---
Agent Grey - Systematic Review Management
                """.strip()

                # Send email
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=self.config.get("from_email"),
                    recipient_list=[invitation.email],
                    fail_silently=False,
                )

                self.logger.info(
                    f"Sent invitation email to {invitation.email}",
                    extra={"invitation_id": str(invitation.id)},
                )

                return True

            except Exception as e:
                self._handle_error(
                    e,
                    operation="send_invitation_email",
                    context={"invitation_id": str(invitation.id)},
                )
                # Don't raise - email failure shouldn't block invitation creation
                return False

    def accept_invitation(
        self, token: str, user: Optional[User] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Accept an invitation and create organisation membership.

        Args:
            token: Magic link token
            user: Optional existing user (if None, will check by email)

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        with self._measure_performance("accept_invitation"):
            try:
                # Find invitation by token
                invitation = OrganisationInvitation.objects.filter(token=token).first()

                if not invitation:
                    return False, "Invitation not found"

                # Check if valid
                if not invitation.is_valid():
                    return False, f"Invitation {invitation.status.lower()}"

                # Get or create user
                if not user:
                    user = User.objects.filter(email=invitation.email).first()

                if not user:
                    return False, "Please create an account first"

                # SECURITY: enforce email match so a leaked/forwarded magic link
                # cannot grant membership to a different account (mirrors
                # review_manager ReviewInvitationService.accept_invitation)
                if user.email != invitation.email:
                    self.logger.warning(
                        "Email mismatch BLOCKED: user %s tried to accept "
                        "org invitation for %s",
                        user.email,
                        invitation.email,
                        extra={
                            "invitation_id": str(invitation.id),
                            "user_id": str(user.id),
                        },
                    )
                    return False, (
                        f"This invitation was sent to {invitation.email}. "
                        "You must accept it with the account registered to "
                        "that email address."
                    )

                # Create membership
                membership, created = OrganisationMembership.objects.get_or_create(
                    user=user,
                    organisation=invitation.organisation,
                    defaults={
                        "role": invitation.role,
                    },
                )

                if not created:
                    # Reactivate if inactive
                    if not membership.is_active:
                        membership.is_active = True
                        membership.save()

                # Mark invitation as accepted
                invitation.status = OrganisationInvitation.STATUS_ACCEPTED
                invitation.accepted_at = timezone.now()
                invitation.save()

                self.logger.info(
                    f"Accepted invitation for {user.email} to {invitation.organisation.name}",
                    extra={
                        "invitation_id": str(invitation.id),
                        "user_id": str(user.id),
                        "membership_id": str(membership.id),
                    },
                )

                return True, None

            except Exception as e:
                self._handle_error(
                    e, operation="accept_invitation", context={"token": token}
                )
                return False, "An error occurred while accepting invitation"

    def revoke_invitation(self, invitation: OrganisationInvitation) -> bool:
        """
        Revoke a pending invitation.

        Args:
            invitation: OrganisationInvitation instance

        Returns:
            bool: True if successfully revoked
        """
        try:
            if invitation.status != OrganisationInvitation.STATUS_PENDING:
                return False

            invitation.status = OrganisationInvitation.STATUS_REVOKED
            invitation.save()

            self.logger.info(
                f"Revoked invitation for {invitation.email}",
                extra={"invitation_id": str(invitation.id)},
            )

            return True

        except Exception as e:
            self._handle_error(
                e,
                operation="revoke_invitation",
                context={"invitation_id": str(invitation.id)},
            )
            return False
