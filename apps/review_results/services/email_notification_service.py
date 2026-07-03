"""
Email notification service for dual-reviewer screening.

Provides email notifications for:
- Conflict detection
- Low inter-rater reliability alerts
- Arbitrator invitations
- Consensus reached
- Review completion
"""

import logging
from typing import Optional

from django.db import models
from django.utils import timezone

from apps.core.services.base_email_service import BaseEmailNotificationService
from apps.review_manager.models import SearchSession
from apps.review_results.models import (
    ConflictResolution,
    InterRaterReliability,
    ReviewerDecision,
)

logger = logging.getLogger(__name__)


class EmailNotificationService(BaseEmailNotificationService):
    """Service for sending dual-screening email notifications."""

    SERVICE_NAME = "EmailNotificationService"
    SERVICE_VERSION = "1.0.0"

    def health_check(self) -> bool:
        """Check if email notification service is healthy."""
        try:
            ConflictResolution.objects.count()
            return True
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def send_conflict_notification(self, conflict_id: str) -> bool:
        """Send conflict detection notification to both reviewers."""
        with self._measure_performance("send_conflict_notification"):
            try:
                conflict = (
                    ConflictResolution.objects.select_related(
                        "result", "result__session"
                    )
                    .prefetch_related(
                        "conflicting_decisions", "conflicting_decisions__reviewer"
                    )
                    .get(id=conflict_id)
                )

                decisions = list(conflict.conflicting_decisions.all())
                if len(decisions) != 2:
                    logger.warning(
                        f"Conflict {conflict_id} does not have exactly 2 decisions"
                    )
                    return False

                result = conflict.result
                session = result.session

                success = True
                for i, decision in enumerate(decisions):
                    other_decision = decisions[1 - i]

                    context = {
                        "reviewer_name": decision.reviewer.get_full_name()
                        or decision.reviewer.username,
                        "session_title": session.title,
                        "result_number": result.id,
                        "result_title": result.title,
                        "result_url": result.url,
                        "result_snippet": result.snippet,
                        "reviewer_decision": decision.get_decision_display(),
                        "other_decision": other_decision.get_decision_display(),
                        "conflict_url": f"{self._get_base_url()}/conflicts/{conflict.id}/",
                    }

                    email_success = self._send_email(
                        subject=f"Conflict Detected - {session.title}",
                        html_template="emails/dual_screening/conflict_detected.html",
                        context=context,
                        recipient_list=[decision.reviewer.email],
                    )

                    if not email_success:
                        success = False

                return success

            except ConflictResolution.DoesNotExist:
                logger.error(f"ConflictResolution {conflict_id} does not exist")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="send_conflict_notification",
                    context={"conflict_id": conflict_id},
                )
                return False

    def send_low_irr_alert(self, session_id: str, irr_value: float) -> bool:
        """Send low inter-rater reliability alert to lead reviewer."""
        with self._measure_performance("send_low_irr_alert"):
            try:
                session = SearchSession.objects.select_related("owner").get(
                    id=session_id
                )

                irr_metric = (
                    InterRaterReliability.objects.filter(
                        search_session_id=session_id, cohens_kappa=irr_value
                    )
                    .select_related("reviewer_a", "reviewer_b")
                    .order_by("-calculated_at")
                    .first()
                )

                if not irr_metric:
                    logger.warning(
                        f"No IRR metric found for session {session_id} with kappa {irr_value}"
                    )
                    return False

                percentage_agreement = round(
                    (irr_metric.agreements / irr_metric.total_comparisons * 100)
                    if irr_metric.total_comparisons > 0
                    else 0,
                    1,
                )

                context = {
                    "lead_reviewer_name": session.owner.get_full_name()
                    or session.owner.username,
                    "session_title": session.title,
                    "cohens_kappa": f"{irr_metric.cohens_kappa:.3f}",
                    "reviewer_a": irr_metric.reviewer_a.get_full_name()
                    if irr_metric.reviewer_a
                    else "Unknown",
                    "reviewer_b": irr_metric.reviewer_b.get_full_name()
                    if irr_metric.reviewer_b
                    else "Unknown",
                    "total_comparisons": irr_metric.total_comparisons,
                    "agreements": irr_metric.agreements,
                    "disagreements": irr_metric.disagreements,
                    "percentage_agreement": f"{percentage_agreement:.1f}",
                    "dashboard_url": f"{self._get_base_url()}/sessions/{session.id}/dashboard/",
                }

                return self._send_email(
                    subject=f"IRR Alert - {session.title}",
                    html_template="emails/dual_screening/low_irr_alert.html",
                    context=context,
                    recipient_list=[session.owner.email],
                )

            except SearchSession.DoesNotExist:
                logger.error(f"SearchSession {session_id} does not exist")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="send_low_irr_alert",
                    context={"session_id": session_id, "irr_value": irr_value},
                )
                return False

    def send_arbitrator_invitation(
        self,
        invitee_email: str,
        invitee_name: str,
        session_id: str,
        invited_by_id: str,
        invitation_token: str,
    ) -> bool:
        """Send arbitrator invitation email."""
        with self._measure_performance("send_arbitrator_invitation"):
            try:
                from apps.accounts.models import User

                session = SearchSession.objects.get(id=session_id)
                invited_by = User.objects.get(id=invited_by_id)

                pending_conflicts_count = ConflictResolution.objects.filter(
                    result__session_id=session_id, status="PENDING"
                ).count()

                estimated_time_minutes = pending_conflicts_count * 2

                context = {
                    "invitee_name": invitee_name,
                    "invited_by_name": invited_by.get_full_name()
                    or invited_by.username,
                    "session_title": session.title,
                    "session_description": session.description,
                    "pending_conflicts_count": pending_conflicts_count,
                    "estimated_time_minutes": estimated_time_minutes,
                    "invitation_url": f"{self._get_base_url()}/invitations/accept/{invitation_token}/",
                }

                return self._send_email(
                    subject=f"Invitation to Arbitrate Conflicts - {session.title}",
                    html_template="emails/dual_screening/arbitrator_invitation.html",
                    context=context,
                    recipient_list=[invitee_email],
                )

            except (SearchSession.DoesNotExist, User.DoesNotExist) as e:
                logger.error(f"Resource not found: {str(e)}")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="send_arbitrator_invitation",
                    context={"invitee_email": invitee_email, "session_id": session_id},
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
                    html_template="emails/dual_screening/reviewer_invitation.html",
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

    def send_consensus_notification(self, conflict_id: str) -> bool:
        """Send consensus reached notification to involved reviewers."""
        with self._measure_performance("send_consensus_notification"):
            try:
                conflict = (
                    ConflictResolution.objects.select_related(
                        "result", "result__session", "final_decision", "resolved_by"
                    )
                    .prefetch_related(
                        "conflicting_decisions", "conflicting_decisions__reviewer"
                    )
                    .get(id=conflict_id)
                )

                if conflict.status != "RESOLVED":
                    logger.warning(f"Conflict {conflict_id} is not resolved")
                    return False

                result = conflict.result
                session = result.session

                reviewers = [
                    decision.reviewer
                    for decision in conflict.conflicting_decisions.all()
                ]

                success = True
                for reviewer in reviewers:
                    context = {
                        "reviewer_name": reviewer.get_full_name() or reviewer.username,
                        "session_title": session.title,
                        "result_number": result.id,
                        "result_title": result.title,
                        "result_url": result.url,
                        "final_decision": conflict.final_decision.get_decision_display()
                        if conflict.final_decision
                        else "N/A",
                        "resolution_method": conflict.get_resolution_method_display()
                        if conflict.resolution_method
                        else "N/A",
                        "resolved_by": conflict.resolved_by.get_full_name()
                        if conflict.resolved_by
                        else None,
                        "resolution_notes": conflict.resolution_notes,
                    }

                    email_success = self._send_email(
                        subject=f"Consensus Reached - {session.title}",
                        html_template="emails/dual_screening/consensus_reached.html",
                        context=context,
                        recipient_list=[reviewer.email],
                    )

                    if not email_success:
                        success = False

                return success

            except ConflictResolution.DoesNotExist:
                logger.error(f"ConflictResolution {conflict_id} does not exist")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="send_consensus_notification",
                    context={"conflict_id": conflict_id},
                )
                return False

    def send_review_completion(self, session_id: str) -> bool:
        """Send review completion summary to all reviewers."""
        with self._measure_performance("send_review_completion"):
            try:
                session = SearchSession.objects.select_related("owner").get(
                    id=session_id
                )

                from apps.accounts.models import User

                reviewer_ids = (
                    ReviewerDecision.objects.filter(result__session_id=session_id)
                    .values_list("reviewer_id", flat=True)
                    .distinct()
                )
                reviewers = User.objects.filter(id__in=reviewer_ids)

                from apps.results_manager.models import ProcessedResult

                total_results = ProcessedResult.objects.filter(
                    session_id=session_id
                ).count()

                decisions = ReviewerDecision.objects.filter(
                    result__session_id=session_id
                )
                included_count = decisions.filter(decision="INCLUDE").count() // 2
                excluded_count = decisions.filter(decision="EXCLUDE").count() // 2
                maybe_count = decisions.filter(decision="MAYBE").count() // 2

                included_percentage = round(
                    (included_count / total_results * 100) if total_results > 0 else 0,
                    1,
                )
                excluded_percentage = round(
                    (excluded_count / total_results * 100) if total_results > 0 else 0,
                    1,
                )

                irr_metric = (
                    InterRaterReliability.objects.filter(search_session_id=session_id)
                    .order_by("-calculated_at")
                    .first()
                )

                cohens_kappa = (
                    f"{irr_metric.cohens_kappa:.3f}"
                    if irr_metric and irr_metric.cohens_kappa
                    else "N/A"
                )
                percentage_agreement = f"{round((irr_metric.agreements / irr_metric.total_comparisons * 100) if irr_metric and irr_metric.total_comparisons > 0 else 0, 1):.1f}"

                kappa_interpretation = self._interpret_kappa(
                    irr_metric.cohens_kappa if irr_metric else None
                )

                conflicts_resolved_count = ConflictResolution.objects.filter(
                    result__session_id=session_id, status="RESOLVED"
                ).count()

                reviewer_contributions = []
                for reviewer in reviewers:
                    decisions_count = ReviewerDecision.objects.filter(
                        result__session_id=session_id, reviewer=reviewer
                    ).count()

                    time_spent_data = ReviewerDecision.objects.filter(
                        result__session_id=session_id,
                        reviewer=reviewer,
                        time_spent_seconds__isnull=False,
                    ).aggregate(total_seconds=models.Sum("time_spent_seconds"))

                    total_seconds = time_spent_data.get("total_seconds", 0) or 0
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60

                    time_spent = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

                    reviewer_contributions.append(
                        {
                            "name": reviewer.get_full_name() or reviewer.username,
                            "decisions_count": decisions_count,
                            "time_spent": time_spent,
                        }
                    )

                success = True
                for reviewer in reviewers:
                    context = {
                        "reviewer_name": reviewer.get_full_name() or reviewer.username,
                        "session_title": session.title,
                        "completed_at": timezone.now(),
                        "total_results": total_results,
                        "included_count": included_count,
                        "excluded_count": excluded_count,
                        "maybe_count": maybe_count,
                        "included_percentage": included_percentage,
                        "excluded_percentage": excluded_percentage,
                        "cohens_kappa": cohens_kappa,
                        "kappa_interpretation": kappa_interpretation,
                        "percentage_agreement": percentage_agreement,
                        "conflicts_resolved_count": conflicts_resolved_count,
                        "reviewer_contributions": reviewer_contributions,
                        "prisma_report_url": f"{self._get_base_url()}/sessions/{session.id}/reports/prisma/",
                    }

                    email_success = self._send_email(
                        subject=f"Review Completed - {session.title}",
                        html_template="emails/dual_screening/review_completed.html",
                        context=context,
                        recipient_list=[reviewer.email],
                    )

                    if not email_success:
                        success = False

                return success

            except SearchSession.DoesNotExist:
                logger.error(f"SearchSession {session_id} does not exist")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="send_review_completion",
                    context={"session_id": session_id},
                )
                return False

    def _interpret_kappa(self, kappa_value: Optional[float]) -> str:
        """Interpret Cohen's Kappa value according to Landis & Koch (1977)."""
        if kappa_value is None:
            return "Not Available"
        if kappa_value < 0.20:
            return "Slight Agreement"
        elif kappa_value < 0.40:
            return "Fair Agreement"
        elif kappa_value < 0.60:
            return "Moderate Agreement"
        elif kappa_value < 0.80:
            return "Substantial Agreement"
        else:
            return "Almost Perfect Agreement"

    # ========================================================================
    # Phase 4: Consensus Discussion Email Notifications
    # ========================================================================

    def notify_conflict_comment_added(
        self, conflict_id: str, comment_id: str, commenter_id: str
    ) -> bool:
        """Notify other reviewers when a comment is added to a conflict discussion."""
        with self._measure_performance("notify_conflict_comment_added"):
            try:
                from apps.accounts.models import User
                from apps.review_results.models import ConflictComment

                comment = ConflictComment.objects.select_related(
                    "conflict",
                    "conflict__result",
                    "conflict__result__session",
                    "author",
                ).get(id=comment_id)

                conflict = comment.conflict
                commenter = User.objects.get(id=commenter_id)
                result = conflict.result
                session = result.session

                reviewer_ids = list(
                    conflict.conflicting_decisions.values_list("reviewer_id", flat=True)
                )
                other_reviewers = User.objects.filter(id__in=reviewer_ids).exclude(
                    id=commenter_id
                )

                if not other_reviewers.exists():
                    logger.warning(
                        f"No other reviewers to notify for conflict {conflict_id}"
                    )
                    return True

                comment_preview = (
                    comment.content[:200] + "..."
                    if len(comment.content) > 200
                    else comment.content
                )

                discussion_url = (
                    f"{self._get_base_url()}/conflicts/{conflict.id}/discuss/"
                )

                success = True
                for reviewer in other_reviewers:
                    context = {
                        "reviewer_name": reviewer.get_full_name() or reviewer.username,
                        "commenter_name": commenter.get_full_name()
                        or commenter.username,
                        "comment_preview": comment_preview,
                        "session_title": session.title,
                        "result_title": result.title,
                        "result_url": result.url,
                        "discussion_url": discussion_url,
                        "conflict": conflict,
                    }

                    email_success = self._send_email(
                        subject=f"New Comment on Conflict - {session.title}",
                        html_template="emails/dual_screening/conflict_comment_notification.html",
                        context=context,
                        recipient_list=[reviewer.email],
                    )

                    if not email_success:
                        success = False

                return success

            except (ConflictComment.DoesNotExist, User.DoesNotExist) as e:
                logger.error(f"Resource not found: {str(e)}")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="notify_conflict_comment_added",
                    context={
                        "conflict_id": conflict_id,
                        "comment_id": comment_id,
                        "commenter_id": commenter_id,
                    },
                )
                return False

    def notify_revote_proposed(
        self, conflict_id: str, proposal_id: str, proposer_id: str
    ) -> bool:
        """Notify other reviewers when a re-vote is proposed."""
        with self._measure_performance("notify_revote_proposed"):
            try:
                from apps.accounts.models import User
                from apps.review_results.models import RevoteProposal

                proposal = RevoteProposal.objects.select_related(
                    "conflict",
                    "conflict__result",
                    "conflict__result__session",
                    "proposed_by",
                ).get(id=proposal_id)

                conflict = proposal.conflict
                proposer = User.objects.get(id=proposer_id)
                result = conflict.result
                session = result.session

                reviewer_ids = list(
                    conflict.conflicting_decisions.values_list("reviewer_id", flat=True)
                )
                other_reviewers = User.objects.filter(id__in=reviewer_ids).exclude(
                    id=proposer_id
                )

                if not other_reviewers.exists():
                    logger.warning(
                        f"No other reviewers to notify for re-vote proposal {proposal_id}"
                    )
                    return True

                discussion_url = (
                    f"{self._get_base_url()}/conflicts/{conflict.id}/discuss/"
                )

                from django.utils.dateformat import DateFormat

                expires_at_formatted = DateFormat(proposal.expires_at).format(
                    "F j, Y, g:i A"
                )

                success = True
                for reviewer in other_reviewers:
                    context = {
                        "reviewer_name": reviewer.get_full_name() or reviewer.username,
                        "proposer_name": proposer.get_full_name() or proposer.username,
                        "rationale": proposal.rationale,
                        "session_title": session.title,
                        "result_title": result.title,
                        "result_url": result.url,
                        "discussion_url": discussion_url,
                        "expires_at": expires_at_formatted,
                        "proposal": proposal,
                        "conflict": conflict,
                    }

                    email_success = self._send_email(
                        subject=f"Re-Vote Proposed - {session.title}",
                        html_template="emails/dual_screening/revote_proposed_notification.html",
                        context=context,
                        recipient_list=[reviewer.email],
                    )

                    if not email_success:
                        success = False

                return success

            except (RevoteProposal.DoesNotExist, User.DoesNotExist) as e:
                logger.error(f"Resource not found: {str(e)}")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="notify_revote_proposed",
                    context={
                        "conflict_id": conflict_id,
                        "proposal_id": proposal_id,
                        "proposer_id": proposer_id,
                    },
                )
                return False

    def notify_conflict_escalated(
        self, conflict_id: str, escalated_by_id: str, reason: str = ""
    ) -> bool:
        """Notify the session owner when a conflict is escalated to arbitration."""
        with self._measure_performance("notify_conflict_escalated"):
            try:
                from apps.accounts.models import User

                conflict = ConflictResolution.objects.select_related(
                    "result",
                    "result__session",
                    "result__session__created_by",
                ).get(id=conflict_id)

                escalated_by = User.objects.get(id=escalated_by_id)
                result = conflict.result
                session = result.session
                owner = session.created_by

                if not owner or not owner.email:
                    logger.warning(
                        f"No session owner email for escalation notification (conflict {conflict_id})"
                    )
                    return True

                conflict_url = (
                    f"{self._get_base_url()}/screening/conflicts/{conflict.id}"
                )

                context = {
                    "owner_name": owner.get_full_name() or owner.username,
                    "escalated_by_name": escalated_by.get_full_name()
                    or escalated_by.username,
                    "session_title": session.title,
                    "result_title": result.title,
                    "reason": reason,
                    "conflict_url": conflict_url,
                }

                return self._send_email(
                    subject=f"Conflict Escalated - {session.title}",
                    html_template="emails/dual_screening/conflict_escalated.html",
                    context=context,
                    recipient_list=[owner.email],
                )

            except (ConflictResolution.DoesNotExist, User.DoesNotExist) as e:
                logger.error(f"Resource not found: {str(e)}")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="notify_conflict_escalated",
                    context={
                        "conflict_id": conflict_id,
                        "escalated_by_id": escalated_by_id,
                    },
                )
                return False

    def notify_revote_ready(self, conflict_id: str, proposal_id: str) -> bool:
        """Notify all reviewers when a re-vote proposal has been accepted by all."""
        with self._measure_performance("notify_revote_ready"):
            try:
                from apps.accounts.models import User
                from apps.review_results.models import RevoteProposal

                proposal = RevoteProposal.objects.select_related(
                    "conflict", "conflict__result", "conflict__result__session"
                ).get(id=proposal_id)

                conflict = proposal.conflict
                result = conflict.result
                session = result.session

                reviewer_ids = list(
                    conflict.conflicting_decisions.values_list("reviewer_id", flat=True)
                )
                reviewers = User.objects.filter(id__in=reviewer_ids)

                if not reviewers.exists():
                    logger.warning(
                        f"No reviewers found for re-vote proposal {proposal_id}"
                    )
                    return False

                discussion_url = (
                    f"{self._get_base_url()}/conflicts/{conflict.id}/discuss/"
                )

                success = True
                for reviewer in reviewers:
                    context = {
                        "reviewer_name": reviewer.get_full_name() or reviewer.username,
                        "session_title": session.title,
                        "result_title": result.title,
                        "result_url": result.url,
                        "discussion_url": discussion_url,
                        "proposal": proposal,
                        "conflict": conflict,
                    }

                    email_success = self._send_email(
                        subject=f"Re-Vote Ready - {session.title}",
                        html_template="emails/dual_screening/revote_ready_notification.html",
                        context=context,
                        recipient_list=[reviewer.email],
                    )

                    if not email_success:
                        success = False

                return success

            except RevoteProposal.DoesNotExist:
                logger.error(f"RevoteProposal {proposal_id} does not exist")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="notify_revote_ready",
                    context={"conflict_id": conflict_id, "proposal_id": proposal_id},
                )
                return False

    def notify_consensus_reached_via_revote(
        self, conflict_id: str, proposal_id: str, consensus_decision: str
    ) -> bool:
        """Notify all reviewers when consensus is reached through re-vote."""
        with self._measure_performance("notify_consensus_reached_via_revote"):
            try:
                from apps.accounts.models import User
                from apps.review_results.models import RevoteProposal

                proposal = RevoteProposal.objects.select_related(
                    "conflict", "conflict__result", "conflict__result__session"
                ).get(id=proposal_id)

                conflict = proposal.conflict
                result = conflict.result
                session = result.session

                reviewer_ids = list(
                    conflict.conflicting_decisions.values_list("reviewer_id", flat=True)
                )
                reviewers = User.objects.filter(id__in=reviewer_ids)

                if not reviewers.exists():
                    logger.warning(f"No reviewers found for conflict {conflict_id}")
                    return False

                discussion_url = (
                    f"{self._get_base_url()}/conflicts/{conflict.id}/discuss/"
                )

                decision_display = {
                    "INCLUDE": "Include",
                    "EXCLUDE": "Exclude",
                    "MAYBE": "Maybe",
                }.get(consensus_decision, consensus_decision)

                success = True
                for reviewer in reviewers:
                    context = {
                        "reviewer_name": reviewer.get_full_name() or reviewer.username,
                        "session_title": session.title,
                        "result_title": result.title,
                        "result_url": result.url,
                        "discussion_url": discussion_url,
                        "consensus_decision": decision_display,
                        "proposal": proposal,
                        "conflict": conflict,
                    }

                    email_success = self._send_email(
                        subject=f"Consensus Reached - {session.title}",
                        html_template="emails/dual_screening/consensus_reached_via_revote.html",
                        context=context,
                        recipient_list=[reviewer.email],
                    )

                    if not email_success:
                        success = False

                return success

            except RevoteProposal.DoesNotExist:
                logger.error(f"RevoteProposal {proposal_id} does not exist")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="notify_consensus_reached_via_revote",
                    context={
                        "conflict_id": conflict_id,
                        "proposal_id": proposal_id,
                        "consensus_decision": consensus_decision,
                    },
                )
                return False

    def send_sla_reminder(self, conflict_id: str, threshold: str) -> bool:
        """Send SLA reminder for a conflict at the given threshold (50 or 90)."""
        with self._measure_performance("send_sla_reminder"):
            try:
                conflict = (
                    ConflictResolution.objects.select_related(
                        "result",
                        "result__session",
                        "result__session__owner",
                    )
                    .prefetch_related(
                        "conflicting_decisions",
                        "conflicting_decisions__reviewer",
                    )
                    .get(id=conflict_id)
                )

                result = conflict.result
                session = result.session
                sla_info = conflict.get_sla_info()

                if sla_info is None:
                    logger.warning(
                        f"No SLA info for conflict {conflict_id} (resolved or WF1)"
                    )
                    return False

                conflict_url = (
                    f"{self._get_base_url()}/screening/conflicts/{conflict.id}"
                )

                # Gather all participants (session owner + reviewers)
                recipients: list[str] = []
                if session.owner and session.owner.email:
                    recipients.append(session.owner.email)

                for decision in conflict.conflicting_decisions.all():
                    if (
                        decision.reviewer.email
                        and decision.reviewer.email not in recipients
                    ):
                        recipients.append(decision.reviewer.email)

                if not recipients:
                    logger.warning(
                        f"No recipients for SLA reminder (conflict {conflict_id})"
                    )
                    return True

                is_critical = threshold == "90"

                context = {
                    "session_title": session.title,
                    "result_title": result.title,
                    "conflict_url": conflict_url,
                    "threshold": f"{threshold}%",
                    "hours_remaining": round(sla_info["hours_remaining"], 1),
                    "is_overdue": sla_info["is_overdue"],
                    "hours_overdue": round(sla_info["hours_overdue"], 1),
                    "is_critical": is_critical,
                    "sla_hours": sla_info["sla_hours"],
                }

                subject_prefix = "URGENT: " if is_critical else ""

                return self._send_email(
                    subject=f"{subject_prefix}SLA Reminder - {session.title}",
                    html_template="emails/dual_screening/conflict_sla_reminder.html",
                    context=context,
                    recipient_list=recipients,
                )

            except ConflictResolution.DoesNotExist:
                logger.error(f"ConflictResolution {conflict_id} does not exist")
                return False
            except Exception as e:
                self._handle_error(
                    e,
                    operation="send_sla_reminder",
                    context={
                        "conflict_id": conflict_id,
                        "threshold": threshold,
                    },
                )
                return False
