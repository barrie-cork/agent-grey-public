"""
Notification service for external reviewer approval workflow.

Provides email notifications for:
- IS approval needed for external reviewers
- External reviewers approved
- External reviewers rejected
"""

import logging
from typing import Dict, List

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.services.base_email_service import BaseEmailNotificationService
from apps.organisation.models import Organisation
from apps.review_manager.models import SearchSession, ReviewConfiguration

logger = logging.getLogger(__name__)
User = get_user_model()


class NotificationService(BaseEmailNotificationService):
    """Service for sending external reviewer approval notifications."""

    SERVICE_NAME = "NotificationService"
    SERVICE_VERSION = "1.0.0"

    def health_check(self) -> bool:
        """Check if notification service is healthy."""
        try:
            ReviewConfiguration.objects.count()
            return True
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def _get_is_users_for_organisation(self, organisation: Organisation) -> List[User]:
        """Get all Information Specialist users for an organisation."""
        try:
            return User.objects.filter(
                organisation_memberships__organisation=organisation,
                organisation_memberships__role="INFORMATION_SPECIALIST",
                organisation_memberships__is_active=True,
                is_active=True,
            ).distinct()
        except Exception as e:
            logger.error(
                f"Error getting IS users for organisation {organisation.id}: {str(e)}"
            )
            return []

    def notify_is_approval_needed(
        self, session: SearchSession, external_reviewers: List[Dict]
    ) -> bool:
        """Send notification to IS users when external reviewers need approval."""
        with self._measure_performance("notify_is_approval_needed"):
            try:
                is_users = self._get_is_users_for_organisation(session.organisation)

                if not is_users:
                    logger.warning(
                        f"No IS users found for organisation {session.organisation.id}"
                    )
                    return False

                expires_at = timezone.now() + timezone.timedelta(days=7)

                success = True
                for is_user in is_users:
                    context = {
                        "is_name": is_user.get_full_name() or is_user.username,
                        "session_title": session.title,
                        "session_owner_name": session.owner.get_full_name()
                        or session.owner.username,
                        "session_description": session.description
                        or "No description provided",
                        "external_reviewers": external_reviewers,
                        "external_count": len(external_reviewers),
                        "approval_url": f"{self._get_base_url()}/review/approvals/pending/",
                        "expires_at": expires_at,
                    }

                    email_success = self._send_email(
                        subject=f"Approval Needed: External Reviewers - {session.title}",
                        html_template="emails/approval_workflow/approval_needed.html",
                        context=context,
                        recipient_list=[is_user.email],
                    )

                    if not email_success:
                        success = False

                return success

            except Exception as e:
                self._handle_error(
                    e,
                    operation="notify_is_approval_needed",
                    context={
                        "session_id": str(session.id),
                        "external_count": len(external_reviewers),
                    },
                )
                return False

    def notify_external_reviewers_approved(
        self, session: SearchSession, approved_by: User, external_reviewers: List[Dict]
    ) -> bool:
        """Send notification to session owner when external reviewers are approved."""
        with self._measure_performance("notify_external_reviewers_approved"):
            try:
                context = {
                    "owner_name": session.owner.get_full_name()
                    or session.owner.username,
                    "session_title": session.title,
                    "approved_by_name": approved_by.get_full_name()
                    or approved_by.username,
                    "external_reviewers": external_reviewers,
                    "approved_count": len(external_reviewers),
                    "approved_at": timezone.now(),
                    "session_url": f"{self._get_base_url()}/sessions/{session.id}/",
                }

                return self._send_email(
                    subject=f"External Reviewers Approved - {session.title}",
                    html_template="emails/approval_workflow/reviewers_approved.html",
                    context=context,
                    recipient_list=[session.owner.email],
                )

            except Exception as e:
                self._handle_error(
                    e,
                    operation="notify_external_reviewers_approved",
                    context={
                        "session_id": str(session.id),
                        "approved_by": str(approved_by.id),
                        "external_count": len(external_reviewers),
                    },
                )
                return False

    def notify_external_reviewers_rejected(
        self,
        session: SearchSession,
        rejected_by: User,
        external_reviewers: List[Dict],
        reason: str,
    ) -> bool:
        """Send notification to session owner when external reviewers are rejected."""
        with self._measure_performance("notify_external_reviewers_rejected"):
            try:
                context = {
                    "owner_name": session.owner.get_full_name()
                    or session.owner.username,
                    "session_title": session.title,
                    "rejected_by_name": rejected_by.get_full_name()
                    or rejected_by.username,
                    "external_reviewers": external_reviewers,
                    "rejected_count": len(external_reviewers),
                    "rejection_reason": reason,
                    "rejected_at": timezone.now(),
                    "session_url": f"{self._get_base_url()}/sessions/{session.id}/",
                }

                return self._send_email(
                    subject=f"External Reviewers Rejected - {session.title}",
                    html_template="emails/approval_workflow/reviewers_rejected.html",
                    context=context,
                    recipient_list=[session.owner.email],
                )

            except Exception as e:
                self._handle_error(
                    e,
                    operation="notify_external_reviewers_rejected",
                    context={
                        "session_id": str(session.id),
                        "rejected_by": str(rejected_by.id),
                        "external_count": len(external_reviewers),
                        "reason": reason,
                    },
                )
                return False

    def send_reviewer_invitation(self, invitation, request=None) -> bool:
        """Send reviewer invitation email with magic link."""
        with self._measure_performance("send_reviewer_invitation"):
            try:
                session = invitation.session
                inviter = invitation.inviter

                magic_link = invitation.get_magic_link(request)
                days_until_expiry = (invitation.expires_at - timezone.now()).days

                context = {
                    "invitee_name": invitation.invitee_name or invitation.invitee_email,
                    "inviter_name": inviter.get_full_name()
                    if inviter
                    else "A colleague",
                    "session_title": session.title,
                    "session_description": session.description
                    or "No description provided",
                    "total_results": session.total_results or 0,
                    "magic_link": magic_link,
                    "expires_days": days_until_expiry,
                    "expires_at": invitation.expires_at,
                }

                return self._send_email(
                    subject=f"Invitation to Review Session - {session.title}",
                    html_template="emails/review_manager/reviewer_invitation.html",
                    context=context,
                    recipient_list=[invitation.invitee_email],
                )

            except Exception as e:
                self._handle_error(
                    e,
                    operation="send_reviewer_invitation",
                    context={
                        "invitation_id": str(invitation.id) if invitation else None,
                        "invitee_email": invitation.invitee_email
                        if invitation
                        else None,
                    },
                )
                return False
