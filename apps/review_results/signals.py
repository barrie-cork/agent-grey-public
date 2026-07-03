"""
Django signals for dual-screening notifications.

Handles automatic email notifications for:
- Conflict detection
- Low inter-rater reliability
- Review completion

Following the pattern established in apps/accounts/signals.py
"""

import logging

from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.review_manager.models import ReviewInvitation, SearchSession
from apps.review_results.models import (
    ConflictResolution,
    InterRaterReliability,
    ReviewerCompletion,
    ReviewerDecision,
    SimpleReviewDecision,
)
from apps.review_results.services.email_notification_service import (
    EmailNotificationService,
)

logger = logging.getLogger(__name__)


@receiver(
    m2m_changed,
    sender=ConflictResolution.conflicting_decisions.through,
    dispatch_uid="review_results.conflict_detected_handler",
)
def conflict_detected_handler(sender, instance, action, **kwargs):
    """
    Send email notification when conflicting decisions are linked to a conflict.

    Uses m2m_changed instead of post_save because ConflictResolution.create()
    fires post_save before .set()/.add() links the M2M decisions. The email
    service needs those decisions to identify the reviewers to notify.

    Args:
        sender: The M2M through table
        instance: The ConflictResolution instance
        action: The m2m_changed action (pre_add, post_add, etc.)
        **kwargs: Additional signal arguments (pk_set, model, etc.)
    """
    if action != "post_add":
        return

    # Only send notification for PENDING conflicts (newly detected)
    if instance.status != "PENDING":
        return

    try:
        service = EmailNotificationService()
        success = service.send_conflict_notification(str(instance.id))

        if success:
            logger.info(
                f"Conflict notification sent for conflict {instance.id}",
                extra={"conflict_id": str(instance.id)},
            )
        else:
            logger.warning(
                f"Failed to send conflict notification for {instance.id}",
                extra={"conflict_id": str(instance.id)},
            )

    except Exception as e:
        logger.error(
            f"Error sending conflict notification for {instance.id}: {str(e)}",
            extra={"conflict_id": str(instance.id)},
            exc_info=True,
        )


@receiver(
    post_save,
    sender=ConflictResolution,
    dispatch_uid="review_results.consensus_reached_handler",
)
def consensus_reached_handler(sender, instance, created, **kwargs):
    """
    Send email notification when consensus is reached on a conflict.

    This signal fires when a ConflictResolution is updated to RESOLVED status,
    indicating that reviewers have reached consensus or an arbitrator has made
    a final decision.

    Args:
        sender: The ConflictResolution model class
        instance: The ConflictResolution instance that was saved
        created: Boolean indicating if this is a new conflict
        **kwargs: Additional signal arguments
    """
    # Only send notification when status changes to RESOLVED (not on creation)
    if created:
        return

    if instance.status != "RESOLVED":
        return

    # Check if this is a new resolution (not already sent)
    # We rely on the resolved_at timestamp being newly set
    if not instance.resolved_at:
        return

    try:
        service = EmailNotificationService()
        success = service.send_consensus_notification(str(instance.id))

        if success:
            logger.info(
                f"Consensus notification sent for conflict {instance.id}",
                extra={"conflict_id": str(instance.id)},
            )
        else:
            logger.warning(
                f"Failed to send consensus notification for {instance.id}",
                extra={"conflict_id": str(instance.id)},
            )

    except Exception as e:
        logger.error(
            f"Error sending consensus notification for {instance.id}: {str(e)}",
            extra={"conflict_id": str(instance.id)},
            exc_info=True,
        )


@receiver(
    post_save,
    sender=InterRaterReliability,
    dispatch_uid="review_results.irr_threshold_check",
)
def irr_threshold_check(sender, instance, created, **kwargs):
    """
    Send alert when inter-rater reliability drops below threshold.

    This signal fires when a new InterRaterReliability metric is calculated.
    If Cohen's Kappa is below the Cochrane minimum threshold of 0.70,
    an alert is sent to the lead reviewer.

    Args:
        sender: The InterRaterReliability model class
        instance: The InterRaterReliability instance that was saved
        created: Boolean indicating if this is a new metric
        **kwargs: Additional signal arguments
    """
    # Only check newly created IRR metrics
    if not created:
        return

    # Only alert if kappa is below Cochrane threshold
    if instance.cohens_kappa is None or instance.cohens_kappa >= 0.70:
        return

    try:
        service = EmailNotificationService()
        success = service.send_low_irr_alert(
            str(instance.search_session_id), instance.cohens_kappa
        )

        if success:
            logger.info(
                f"Low IRR alert sent for session {instance.search_session_id}",
                extra={
                    "session_id": str(instance.search_session_id),
                    "cohens_kappa": instance.cohens_kappa,
                },
            )
        else:
            logger.warning(
                f"Failed to send low IRR alert for session {instance.search_session_id}",
                extra={
                    "session_id": str(instance.search_session_id),
                    "cohens_kappa": instance.cohens_kappa,
                },
            )

    except Exception as e:
        logger.error(
            f"Error sending low IRR alert for session {instance.search_session_id}: {str(e)}",
            extra={
                "session_id": str(instance.search_session_id),
                "cohens_kappa": instance.cohens_kappa,
            },
            exc_info=True,
        )


@receiver(
    post_save,
    sender=SearchSession,
    dispatch_uid="review_results.review_completion_handler",
)
def review_completion_handler(sender, instance, created, **kwargs):
    """
    Send completion summary when review session is completed.

    This signal fires when a SearchSession is updated to 'completed' status,
    indicating that the screening phase is finished and ready for PRISMA
    report generation.

    Args:
        sender: The SearchSession model class
        instance: The SearchSession instance that was saved
        created: Boolean indicating if this is a new session
        **kwargs: Additional signal arguments
    """
    # Don't send on creation
    if created:
        return

    # Only send when status changes to 'completed'
    if instance.status != "completed":
        return

    # Check if this is a dual-screening session (has ReviewerDecisions)
    from apps.review_results.models import ReviewerDecision

    has_dual_screening = ReviewerDecision.objects.filter(
        result__session_id=instance.id
    ).exists()

    if not has_dual_screening:
        logger.debug(
            f"Session {instance.id} completed but has no dual screening - skipping email",
            extra={"session_id": str(instance.id)},
        )
        return

    try:
        service = EmailNotificationService()
        success = service.send_review_completion(str(instance.id))

        if success:
            logger.info(
                f"Review completion notification sent for session {instance.id}",
                extra={"session_id": str(instance.id)},
            )
        else:
            logger.warning(
                f"Failed to send review completion notification for session {instance.id}",
                extra={"session_id": str(instance.id)},
            )

    except Exception as e:
        logger.error(
            f"Error sending review completion notification for session {instance.id}: {str(e)}",
            extra={"session_id": str(instance.id)},
            exc_info=True,
        )


@receiver(
    post_save,
    sender=ReviewInvitation,
    dispatch_uid="review_results.create_reviewer_completion_on_acceptance",
)
def create_reviewer_completion_on_acceptance(sender, instance, created, **kwargs):
    """
    Create ReviewerCompletion when ReviewInvitation is accepted.

    This signal fires when a ReviewInvitation is saved. It only creates
    a ReviewerCompletion record when:
    - The invitation status is ACCEPTED
    - A ReviewerCompletion record doesn't already exist
    - The invitation has an invitee (user who accepted)

    Args:
        sender: ReviewInvitation model class
        instance: ReviewInvitation instance that was saved
        created: Boolean indicating if this is a new record
        **kwargs: Additional signal arguments
    """
    # Only process if status is ACCEPTED
    if instance.status != ReviewInvitation.STATUS_ACCEPTED:
        return

    # Skip if no invitee (shouldn't happen for ACCEPTED status)
    if not instance.invitee:
        logger.warning(
            f"ReviewInvitation {instance.id} is ACCEPTED but has no invitee",
            extra={"invitation_id": str(instance.id)},
        )
        return

    # Check if ReviewerCompletion already exists for this session+reviewer pair
    # (hasattr on reverse OneToOne is unreliable -- use direct query)
    if ReviewerCompletion.objects.filter(
        session=instance.session, reviewer=instance.invitee
    ).exists():
        logger.debug(
            f"ReviewerCompletion already exists for invitation {instance.id}",
            extra={"invitation_id": str(instance.id)},
        )
        return

    # Get total results from session
    total_results = instance.session.total_results

    # Create ReviewerCompletion
    try:
        completion = ReviewerCompletion.objects.create(
            invitation=instance,
            session=instance.session,
            reviewer=instance.invitee,
            total_results=total_results,
            reviewed_results=0,
        )
        logger.info(
            f"Created ReviewerCompletion {completion.id} for invitation {instance.id}",
            extra={
                "invitation_id": str(instance.id),
                "completion_id": str(completion.id),
                "reviewer_id": instance.invitee.id,
                "session_id": str(instance.session.id),
            },
        )
    except Exception as e:
        logger.error(
            f"Error creating ReviewerCompletion for invitation {instance.id}: {str(e)}",
            extra={"invitation_id": str(instance.id)},
            exc_info=True,
        )


@receiver(
    post_save,
    sender=SearchSession,
    dispatch_uid="review_results.create_owner_completion_on_ready_for_review",
)
def create_owner_completion_on_ready_for_review(
    sender, instance, created, update_fields, **kwargs
):
    """
    Create ReviewerCompletion for session owner when session reaches ready_for_review.

    Only applies to Workflow #2 (is_workflow_2=True). Session owners don't have
    invitations, so we create a completion record with invitation=None when the
    session transitions to ready_for_review state.

    Args:
        sender: SearchSession model class
        instance: SearchSession instance that was saved
        created: Boolean indicating if this is a new record
        update_fields: Fields that were explicitly updated (if any)
        **kwargs: Additional signal arguments
    """
    # Skip if this is a new session being created
    if created:
        return

    # Skip if status wasn't in the update_fields
    if update_fields and "status" not in update_fields:
        return

    # Only process when transitioning to ready_for_review
    if instance.status != "ready_for_review":
        return

    # Only for Workflow #2
    config = instance.current_configuration
    if not config or not config.is_workflow_2:
        return

    # Check if owner already has completion record
    if ReviewerCompletion.objects.filter(
        session=instance, reviewer=instance.owner
    ).exists():
        return

    # Create completion record for owner
    try:
        completion = ReviewerCompletion.objects.create(
            invitation=None,
            session=instance,
            reviewer=instance.owner,
            total_results=instance.total_results,
            reviewed_results=0,
        )
        logger.info(
            f"Created owner ReviewerCompletion {completion.id} for session {instance.id}",
            extra={
                "completion_id": str(completion.id),
                "owner_id": instance.owner.id,
                "session_id": str(instance.id),
            },
        )
    except Exception as e:
        logger.error(
            f"Error creating owner ReviewerCompletion for session {instance.id}: {str(e)}",
            extra={"session_id": str(instance.id)},
            exc_info=True,
        )


@receiver(
    post_save,
    sender=SimpleReviewDecision,
    dispatch_uid="review_results.update_completion_progress_simple",
)
@receiver(
    post_save,
    sender=ReviewerDecision,
    dispatch_uid="review_results.update_completion_progress_reviewer",
)
def update_reviewer_completion_progress(sender, instance, created, **kwargs):
    """
    Update ReviewerCompletion progress when reviewer makes a decision.

    Supports both workflows:
    - Workflow #1 (Work Distribution): SimpleReviewDecision (OneToOne with result)
    - Workflow #2 (Independent Screening): ReviewerDecision (ForeignKey, many per result)

    The signal fires on .save() for either model and updates the reviewer's
    progress tracking record (ReviewerCompletion).

    Args:
        sender: Model class that triggered signal (SimpleReviewDecision or ReviewerDecision)
        instance: The saved model instance
        created: Boolean indicating if this is a new record
        **kwargs: Additional signal arguments

    Returns:
        None

    Side Effects:
        - Updates ReviewerCompletion.reviewed_results count
        - Sets ReviewerCompletion.completed_at when all results reviewed
    """
    try:
        # Step 1: Detect which model sent the signal and extract common fields
        if sender.__name__ == "SimpleReviewDecision":
            # Workflow #1: OneToOne relationship
            # SimpleReviewDecision has direct FK to session and reviewer
            session = instance.session
            reviewer = instance.reviewer

            # Skip if no reviewer (shouldn't happen)
            if not reviewer:
                return

            # Count total decisions made by this reviewer in this session
            # Since OneToOne, each result can only have one decision
            reviewed_count = SimpleReviewDecision.objects.filter(
                session=session, reviewer=reviewer
            ).count()

            logger.debug(
                f"Workflow #1: {reviewer.username} reviewed {reviewed_count} results in {session.id}"
            )

        elif sender.__name__ == "ReviewerDecision":
            # Workflow #2: ForeignKey relationship (many decisions per reviewer per result)
            # ReviewerDecision links to result, which links to session
            session = instance.result.session  # FK traversal: result → session
            reviewer = instance.reviewer

            # Skip if no reviewer (shouldn't happen)
            if not reviewer:
                return

            # CRITICAL: Count DISTINCT results reviewed, not total decision count
            # A reviewer may make multiple decisions on same result (revote scenario)
            # We want: "How many results has this reviewer voted on during initial screening?"
            # Not: "How many total votes has this reviewer made?"
            # Filter by is_revote=False to exclude re-vote decisions (conflict resolution phase)
            # Filter by processing_status/is_hidden to match the total_results denominator (#82)
            reviewed_count = (
                ReviewerDecision.objects.filter(
                    result__session=session,  # FK traversal for filtering
                    result__processing_status="success",
                    result__is_hidden=False,
                    reviewer=reviewer,
                    is_revote=False,  # Only count initial screening decisions
                )
                .values("result")
                .distinct()
                .count()
            )  # Distinct result IDs

            logger.debug(
                f"Workflow #2: {reviewer.username} reviewed {reviewed_count} distinct results in {session.id}"
            )

        else:
            # Unexpected sender model
            logger.warning(
                f"update_reviewer_completion_progress received signal from unexpected model: {sender.__name__}"
            )
            return

        # Step 2: Find ReviewerCompletion for this (session, reviewer) pair
        # This record should already exist (created by signal when ReviewInvitation accepted)
        try:
            completion = ReviewerCompletion.objects.get(
                session=session, reviewer=reviewer
            )
        except ReviewerCompletion.DoesNotExist:
            # No completion tracking for this reviewer (not invited, or session owner)
            logger.debug(
                f"No ReviewerCompletion found for reviewer {reviewer.id} "
                f"in session {session.id}",
                extra={"reviewer_id": reviewer.id, "session_id": str(session.id)},
            )
            return

        # Step 3: Update progress count
        old_count = completion.reviewed_results
        completion.reviewed_results = reviewed_count

        # Step 4: Auto-mark complete if all results reviewed
        if (
            completion.reviewed_results >= completion.total_results
            and completion.total_results > 0
        ):
            if not completion.completed_at:
                completion.completed_at = timezone.now()
                logger.info(
                    f"Auto-completed: {reviewer.username} finished all {completion.total_results} results in {session.id}",
                    extra={
                        "completion_id": str(completion.id),
                        "reviewer_id": reviewer.id,
                        "session_id": str(session.id),
                        "reviewed_results": reviewed_count,
                        "total_results": completion.total_results,
                    },
                )

        # Save changes
        completion.save(
            update_fields=["reviewed_results", "completed_at", "updated_at"]
        )

        logger.debug(
            f"Updated progress: {reviewer.username} at {reviewed_count}/{completion.total_results} in {session.id}",
            extra={
                "completion_id": str(completion.id),
                "reviewer_id": reviewer.id,
                "session_id": str(session.id),
                "old_count": old_count,
                "new_count": reviewed_count,
            },
        )

    except Exception as e:
        # CRITICAL: Never let signal handlers crash
        # Log exception with full traceback and continue
        logger.error(
            f"Error updating reviewer completion progress: {e}",
            exc_info=True,  # Include traceback
            extra={
                "sender": sender.__name__,
                "instance_id": getattr(instance, "id", None),
                "session_id": getattr(session, "id", None)
                if "session" in locals()
                else None,
                "reviewer_id": getattr(reviewer, "id", None)
                if "reviewer" in locals()
                else None,
            },
        )
