"""
Signals for cross-slice communication in the review_manager app.
VSA-compliant event-driven communication.

Also handles automatic reviewer invitation sending when sessions
reach ready_for_review status (after results are available).
"""

import logging

from django.db.models.signals import post_save, pre_delete
from django.dispatch import Signal, receiver

logger = logging.getLogger(__name__)

# Session lifecycle signals
session_created = Signal()
session_status_changed = Signal()
session_deleted = Signal()

# Session data access signals for other slices
session_data_requested = Signal()


def get_session_data(session_id: str):
    """
    Internal API for controlled cross-slice data access.
    Returns session data without exposing internal models.
    """
    from .models import SearchSession

    try:
        session = SearchSession.objects.get(id=session_id)
        return {
            "id": str(session.id),
            "title": session.title,
            "status": session.status,
            "owner_id": str(session.owner.id),
            "created_at": session.created_at.isoformat(),
            "total_queries": session.total_queries,
            "total_results": session.total_results,
            "reviewed_results": session.reviewed_results,
            "included_results": session.included_results,
        }
    except SearchSession.DoesNotExist:
        return {}


def get_sessions_by_status(user_id: str, status: str | None = None) -> list:
    """
    Internal API to get sessions without exposing models.
    """
    from .models import SearchSession

    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = User.objects.get(id=user_id)
        sessions = SearchSession.objects.filter(owner=user)

        if status:
            sessions = sessions.filter(status=status)

        return [
            {
                "id": str(session.id),
                "title": session.title,
                "status": session.status,
                "created_at": session.created_at.isoformat(),
                "total_results": session.total_results,
            }
            for session in sessions
        ]
    except Exception:
        return []


@receiver(
    post_save,
    sender="review_manager.SearchSession",
    dispatch_uid="review_manager.send_invitations_when_ready",
)
def send_invitations_when_ready(sender, instance, created, update_fields, **kwargs):
    """
    Send reviewer invitations when session reaches ready_for_review status.

    This ensures reviewers can ONLY access the session after:
    1. Search strategy has been defined
    2. Search queries have been executed
    3. Results have been processed and are available for review

    This prevents reviewers from seeing or editing the search strategy,
    maintaining blind review integrity per PRISMA 2020 guidelines.

    Args:
        sender: SearchSession model class
        instance: SearchSession instance that was saved
        created: Boolean indicating if this is a new record
        update_fields: Set of field names that were updated (or None)
        **kwargs: Additional keyword arguments

    Returns:
        None
    """
    # Skip if this is a new record (not a status change)
    if created:
        return

    # Only proceed if status was actually updated
    if update_fields and "status" not in update_fields:
        return

    # Only proceed if session has reached ready_for_review status
    if instance.status != "ready_for_review":
        return

    # Check if we have a configuration with invited reviewers
    if not instance.current_configuration:
        logger.debug(
            f"Session {instance.id} has no configuration, skipping invitation sending"
        )
        return

    invited_reviewers = instance.current_configuration.invited_reviewers
    if not invited_reviewers:
        logger.debug(
            f"Session {instance.id} has no invited reviewers, skipping invitation sending"
        )
        return

    # Import here to avoid circular dependency
    from .models import ReviewInvitation
    from .services.invitation_service import ReviewInvitationService

    # Check if invitations have already been sent (avoid duplicates).
    # The invitation_service uses get_or_create as the authoritative atomic guard
    # against the underlying TOCTOU race.
    existing_invitations = ReviewInvitation.objects.filter(session=instance).count()

    if existing_invitations > 0:
        logger.info(
            f"Session {instance.id} already has {existing_invitations} invitation(s), "
            f"skipping duplicate invitation sending"
        )
        return

    # Import classification utilities
    from .utils import classify_invited_reviewers, requires_is_approval_for_external

    # Get the organisation from the session
    organisation = instance.organisation

    # Classify reviewers as internal or external
    classification = classify_invited_reviewers(invited_reviewers, organisation)

    logger.info(
        f"Session {instance.id} reviewer classification: "
        f"{classification['counts']['internal']} internal, "
        f"{classification['counts']['external']} external reviewers"
    )

    # Transform internal reviewers for invitation service
    # Config stores: [{'email': str, 'first_name': str, 'last_name': str}]
    # Service expects: [{'email': str, 'name': str}]
    internal_invitee_data = [
        {
            "email": reviewer.get("email"),
            "name": f"{reviewer.get('first_name', '')} {reviewer.get('last_name', '')}".strip(),
        }
        for reviewer in classification["internal"]
        if reviewer.get("email")  # Skip entries without email
    ]

    external_reviewers = classification["external"]

    # Check if IS approval is required for external reviewers
    if external_reviewers and requires_is_approval_for_external():
        # Store external reviewers for approval
        config = instance.current_configuration
        config.external_reviewers_pending_approval = external_reviewers
        config.save(update_fields=["external_reviewers_pending_approval"])

        logger.info(
            f"Session {instance.id}: {len(external_reviewers)} external reviewer(s) "
            f"pending IS approval. Invitations will be sent after approval."
        )

        # Log activity for audit trail
        from .models import SessionActivity

        SessionActivity.objects.create(
            session=instance,
            user=instance.owner,
            activity_type="external_reviewers_pending_approval",
            description=f"{len(external_reviewers)} external reviewer(s) pending IS approval",
            metadata={
                "external_reviewers": external_reviewers,
                "count": len(external_reviewers),
            },
        )

        # Send notification to IS about pending external reviewers
        from .services.notification_service import NotificationService

        notification_service = NotificationService()
        notification_service.notify_is_approval_needed(instance, external_reviewers)
    elif external_reviewers:
        # IS approval not required - transform external reviewers for immediate invitation
        logger.info(
            f"Session {instance.id}: IS approval not required, "
            f"sending invitations to {len(external_reviewers)} external reviewer(s)"
        )

        external_invitee_data = [
            {
                "email": reviewer.get("email"),
                "name": f"{reviewer.get('first_name', '')} {reviewer.get('last_name', '')}".strip(),
            }
            for reviewer in external_reviewers
            if reviewer.get("email")
        ]

        # Add external reviewers to internal for immediate sending
        internal_invitee_data.extend(external_invitee_data)

    if not internal_invitee_data:
        logger.info(f"Session {instance.id} has no reviewers to invite immediately")
        return

    # Create and send invitations for internal reviewers (and external if approval not required)
    try:
        logger.info(
            f"Session {instance.id} reached ready_for_review status, "
            f"sending invitations to {len(internal_invitee_data)} reviewer(s)"
        )

        invitation_service = ReviewInvitationService()
        created_invitations, error_messages = invitation_service.create_invitations(
            session=instance,
            invitee_data=internal_invitee_data,
            inviter=instance.owner,
            request=None,  # No HTTP request context in signal handler
        )

        # Log results
        if created_invitations:
            logger.info(
                f"Successfully created {len(created_invitations)} invitation(s) "
                f"for session {instance.id}"
            )

        if error_messages:
            for error in error_messages:
                logger.warning(f"Invitation error for session {instance.id}: {error}")

    except Exception as e:
        # Log error but don't raise - invitation sending shouldn't block workflow
        logger.error(
            f"Failed to send invitations for session {instance.id}: {str(e)}",
            exc_info=True,
        )


@receiver(
    session_status_changed, dispatch_uid="review_manager.handle_status_change_request"
)
def handle_status_change_request(
    sender, session_id, requested_status, reason, **kwargs
):
    """
    Handle status change requests from other slices.
    """
    from .models import SearchSession
    from .utils import transition_session_status

    try:
        session = SearchSession.objects.get(id=session_id)
        success, error = transition_session_status(
            session, requested_status, description=reason
        )

        if success and requested_status == "ready_to_execute":
            # Update query count from search_strategy slice
            from apps.search_strategy.signals import get_query_count

            session.total_queries = get_query_count(session_id)
            session.save(update_fields=["total_queries", "updated_at"])

    except SearchSession.DoesNotExist:
        pass


# Cache invalidation handlers
@receiver(
    post_save,
    sender="review_manager.SearchSession",
    dispatch_uid="review_manager.invalidate_session_cache_on_save",
)
def invalidate_session_cache_on_save(sender, instance, created, **kwargs):
    """
    Invalidate caches when a session is saved.
    """
    from apps.core.services.cache_service import WorkflowCacheService

    # Invalidate session-specific caches
    WorkflowCacheService.invalidate_session(str(instance.id))

    # Invalidate user dashboard cache
    if instance.owner_id:
        WorkflowCacheService.invalidate_user_dashboard(str(instance.owner_id))

    # If status changed, warm cache for active sessions
    if hasattr(instance, "_status_changed") and instance._status_changed:
        if instance.status in ["executing", "processing_results", "under_review"]:
            from apps.review_manager.tasks.cache import warm_session_cache

            warm_session_cache.delay(str(instance.id))


@receiver(
    pre_delete,
    sender="review_manager.SearchSession",
    dispatch_uid="review_manager.invalidate_session_cache_on_delete",
)
def invalidate_session_cache_on_delete(sender, instance, **kwargs):
    """
    Invalidate caches when a session is deleted.
    """
    from apps.core.services.cache_service import WorkflowCacheService

    # Invalidate session-specific caches
    WorkflowCacheService.invalidate_session(str(instance.id))

    # Invalidate user dashboard cache
    if instance.owner_id:
        WorkflowCacheService.invalidate_user_dashboard(str(instance.owner_id))
