"""
Celery tasks for review results background processing.

Provides asynchronous IRR calculation with Redis distributed locking
to prevent duplicate calculations.
"""

import contextlib
import logging

from celery import shared_task
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def redis_lock(key: str, timeout: int = 60):
    """
    Context manager for Redis distributed lock.

    Prevents duplicate Celery task execution across workers.

    Args:
        key: Lock key (should be unique per operation)
        timeout: Lock timeout in seconds (default: 60)

    Yields:
        bool: True if lock was acquired, False otherwise

    Example:
        with redis_lock("irr_calculation:session_123") as acquired:
            if acquired:
                # Perform work
                pass
            else:
                # Another worker is already processing
                return {"status": "skipped"}
    """
    redis_conn = get_redis_connection("default")
    lock = redis_conn.lock(key, timeout=timeout)
    acquired = lock.acquire(blocking=False)

    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock.release()
            except Exception as e:
                logger.warning(f"Failed to release lock {key}: {e}")


@shared_task(
    name="apps.review_results.tasks.calculate_irr",
    max_retries=3,
    default_retry_delay=60,
)
def calculate_irr_task(session_id: str, reviewer_a_id: str, reviewer_b_id: str) -> dict:
    """
    Calculate Cohen's Kappa for a reviewer pair (background task).

    Uses Redis distributed lock to prevent duplicate calculations
    from concurrent task triggers.

    Args:
        session_id: SearchSession UUID
        reviewer_a_id: First reviewer UUID
        reviewer_b_id: Second reviewer UUID

    Returns:
        dict: Task result with status and IRR metrics

    Example:
        >>> calculate_irr_task.delay(
        ...     session_id="abc-123",
        ...     reviewer_a_id="user-456",
        ...     reviewer_b_id="user-789"
        ... )
    """
    # Create unique lock key for this calculation
    lock_key = f"irr_calculation:{session_id}:{reviewer_a_id}:{reviewer_b_id}"

    with redis_lock(lock_key, timeout=120) as acquired:
        if not acquired:
            logger.info(
                f"IRR calculation already running for session {session_id}, "
                f"reviewers {reviewer_a_id} & {reviewer_b_id}"
            )
            return {"status": "skipped", "reason": "calculation_already_running"}

        try:
            # Import here to avoid circular dependencies
            from apps.accounts.models import User
            from apps.review_manager.models import SearchSession
            from apps.review_results.services.irr_service import (
                InterRaterReliabilityService,
            )

            # Load models
            session = SearchSession.objects.select_related("organisation").get(
                id=session_id
            )
            reviewer_a = User.objects.get(id=reviewer_a_id)
            reviewer_b = User.objects.get(id=reviewer_b_id)
            organisation = session.organisation

            # Calculate IRR
            service = InterRaterReliabilityService()
            irr = service.calculate_cohens_kappa(
                reviewer_a=reviewer_a,
                reviewer_b=reviewer_b,
                organisation=organisation,
                search_session=session,
            )

            if irr is None:
                logger.warning(
                    f"Insufficient data for IRR calculation: session {session_id}, "
                    f"reviewers {reviewer_a.username} & {reviewer_b.username}"
                )
                return {
                    "status": "insufficient_data",
                    "reason": "not_enough_common_results",
                }

            logger.info(
                f"IRR calculated successfully: session {session_id}, "
                f"reviewers {reviewer_a.username} & {reviewer_b.username}, "
                f"kappa={irr.cohens_kappa:.3f}"
            )

            return {
                "status": "success",
                "irr_id": str(irr.id),
                "cohens_kappa": irr.cohens_kappa,
                "percentage_agreement": irr.percentage_agreement,
                "total_comparisons": irr.total_comparisons,
            }

        except Exception as e:
            logger.error(
                f"Failed to calculate IRR for session {session_id}: {e}", exc_info=True
            )
            raise


@shared_task(
    name="apps.review_results.tasks.calculate_session_irr",
    max_retries=3,
)
def calculate_session_irr_task(session_id: str) -> dict:
    """
    Calculate IRR for all reviewer pairs in a session (batch operation).

    Useful for end-of-review IRR calculation or periodic recalculation.

    Args:
        session_id: SearchSession UUID

    Returns:
        dict: Task result with status and summary

    Example:
        >>> calculate_session_irr_task.delay(session_id="abc-123")
    """
    try:
        from itertools import combinations

        from apps.review_manager.models import SearchSession
        from apps.review_results.models import ReviewerDecision

        session = SearchSession.objects.select_related("organisation").get(
            id=session_id
        )

        # Get all reviewers who made decisions in this session.
        # .order_by() clears default model ordering which breaks .distinct()
        reviewers = list(
            ReviewerDecision.objects.filter(
                result__session=session, screening_stage="SCREENING"
            )
            .exclude(decision="ABSTAIN")
            .order_by()
            .values_list("reviewer_id", flat=True)
            .distinct()
        )

        if len(reviewers) < 2:
            logger.warning(
                f"Cannot calculate session IRR: only {len(reviewers)} reviewer(s) "
                f"in session {session_id}"
            )
            return {
                "status": "insufficient_reviewers",
                "reviewer_count": len(reviewers),
            }

        # Calculate IRR for all pairs
        pairs_calculated = 0
        pairs_failed = 0

        for reviewer_a_id, reviewer_b_id in combinations(reviewers, 2):
            try:
                # Trigger individual IRR calculation
                calculate_irr_task.delay(
                    session_id=session_id,
                    reviewer_a_id=str(reviewer_a_id),
                    reviewer_b_id=str(reviewer_b_id),
                )
                pairs_calculated += 1
            except Exception as e:
                logger.error(
                    f"Failed to trigger IRR for pair ({reviewer_a_id}, {reviewer_b_id}): {e}"
                )
                pairs_failed += 1

        logger.info(
            f"Triggered IRR calculation for {pairs_calculated} pairs in session {session_id} "
            f"({pairs_failed} failed)"
        )

        return {
            "status": "success",
            "pairs_calculated": pairs_calculated,
            "pairs_failed": pairs_failed,
            "total_pairs": pairs_calculated + pairs_failed,
        }

    except Exception as e:
        logger.error(
            f"Failed to calculate session IRR for {session_id}: {e}", exc_info=True
        )
        raise


@shared_task(
    name="apps.review_results.tasks.check_conflict_sla_reminders",
    queue="monitoring",
    max_retries=2,
    default_retry_delay=120,
)
def check_conflict_sla_reminders() -> dict:
    """Hourly task: send SLA reminder emails at 50% and 90% thresholds."""
    with redis_lock("check_conflict_sla_reminders", timeout=300) as acquired:
        if not acquired:
            logger.info("SLA reminder check already running, skipping")
            return {"status": "skipped", "reason": "lock_not_acquired"}

        try:
            from django.utils import timezone as tz

            from apps.review_results.models import ConflictResolution
            from apps.review_results.services.email_notification_service import (
                EmailNotificationService,
            )

            email_service = EmailNotificationService()
            sent_50 = 0
            sent_90 = 0
            errors = 0

            # Group by session to mitigate N+1 on current_configuration
            conflicts = (
                ConflictResolution.objects.exclude(status="RESOLVED")
                .select_related("result__session")
                .only(
                    "id",
                    "status",
                    "detected_at",
                    "sla_reminders_sent",
                    "result__session__id",
                )
            )

            # Cache configs per session to avoid N+1
            config_cache: dict = {}

            for conflict in conflicts:
                try:
                    session = conflict.result.session
                    session_id = str(session.id)

                    if session_id not in config_cache:
                        config_cache[session_id] = session.current_configuration

                    config = config_cache[session_id]
                    if not config or not config.is_workflow_2:
                        continue

                    sla_info = conflict.get_sla_info()
                    if sla_info is None:
                        continue

                    reminders = conflict.sla_reminders_sent or {}

                    # Check 50% threshold
                    if sla_info["is_approaching"] and "50" not in reminders:
                        if email_service.send_sla_reminder(str(conflict.id), "50"):
                            reminders["50"] = tz.now().isoformat()
                            sent_50 += 1

                    # Check 90% threshold
                    if sla_info["is_critical"] and "90" not in reminders:
                        if email_service.send_sla_reminder(str(conflict.id), "90"):
                            reminders["90"] = tz.now().isoformat()
                            sent_90 += 1

                    # Save if any reminders were sent
                    if reminders != (conflict.sla_reminders_sent or {}):
                        conflict.sla_reminders_sent = reminders
                        conflict.save(update_fields=["sla_reminders_sent"])

                except Exception as e:
                    logger.error(
                        f"Error processing SLA for conflict {conflict.id}: {e}",
                        exc_info=True,
                    )
                    errors += 1

            logger.info(
                f"SLA reminder check complete: sent_50={sent_50}, "
                f"sent_90={sent_90}, errors={errors}"
            )

            return {
                "status": "success",
                "sent_50": sent_50,
                "sent_90": sent_90,
                "errors": errors,
            }

        except Exception as e:
            logger.error(f"Failed SLA reminder check: {e}", exc_info=True)
            raise
