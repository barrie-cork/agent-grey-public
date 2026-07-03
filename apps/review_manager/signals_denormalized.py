"""
Signal handlers for maintaining denormalized field consistency in SearchSession.

These handlers ensure that the denormalized fields (total_results, reviewed_results,
included_results) stay in sync with the actual data in related models.
"""

import logging

from django.db import transaction
from django.db.models import Count, Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def update_session_statistics(session_id):
    """
    Update denormalized statistics for a session.

    This function queries the actual data and updates the denormalized fields
    in the SearchSession model. Handles both WF1 (SimpleReviewDecision) and
    WF2 (ReviewerDecision) workflows.
    """
    from apps.results_manager.models import ProcessedResult
    from apps.results_manager.services.processors.error_handler import ProcessingStatus
    from apps.review_results.models import SimpleReviewDecision

    from .models import SearchSession

    try:
        with transaction.atomic():
            session = SearchSession.objects.select_for_update().get(id=session_id)

            # Get total processed results (only SUCCESS status - available for review)
            # FILTERED (duplicates) and ERROR results are not available for review
            total_results = ProcessedResult.objects.filter(
                session=session, processing_status=ProcessingStatus.SUCCESS
            ).count()

            is_wf2 = (
                session.current_configuration
                and session.current_configuration.is_workflow_2
            )

            if is_wf2:
                reviewed_results, included_results = _calculate_wf2_stats(session)
            else:
                decision_stats = SimpleReviewDecision.objects.filter(
                    session=session
                ).aggregate(
                    total_reviewed=Count("id", filter=~Q(decision="pending")),
                    included=Count("id", filter=Q(decision="include")),
                )
                reviewed_results = decision_stats["total_reviewed"] or 0
                included_results = decision_stats["included"] or 0

            # Update denormalized fields
            session.total_results = total_results
            session.reviewed_results = reviewed_results
            session.included_results = included_results
            session.save(
                update_fields=["total_results", "reviewed_results", "included_results"]
            )

            # Keep ReviewerCompletion.total_results in sync (#82)
            from apps.review_results.models import ReviewerCompletion

            ReviewerCompletion.objects.filter(session=session).exclude(
                total_results=total_results
            ).update(total_results=total_results)

            logger.info(
                f"Updated session {session_id} statistics: "
                f"total={total_results}, reviewed={reviewed_results}, "
                f"included={included_results}"
            )

    except SearchSession.DoesNotExist:
        # Expected during teardown when sessions are deleted while on_commit
        # callbacks are still pending. Debug level to avoid noisy logs.
        logger.debug(f"SearchSession {session_id} not found for statistics update")
    except Exception as e:
        logger.error(f"Error updating session statistics for {session_id}: {str(e)}")


def _calculate_wf2_stats(session) -> tuple[int, int]:
    """
    Calculate reviewed_results and included_results for WF2 sessions.

    reviewed_results: distinct ProcessedResults with at least one non-ABSTAIN decision.
    included_results: results where consensus winner is INCLUDE (no conflict) plus
                      results where conflict was resolved with an INCLUDE decision.

    Mirrors the consensus logic in review_results.internal_api._wf2_progress_counts.
    """
    from apps.review_results.models import ConflictResolution, ReviewerDecision
    from apps.review_results.services.review_coordination_service import consensus_value

    # Read consensus criteria once from session config
    criteria = (
        session.current_configuration.consensus_criteria
        if session.current_configuration
        else "MAJORITY"
    )

    # Count distinct results with at least one screening decision
    reviewed_results = (
        ReviewerDecision.objects.filter(
            result__session=session,
            is_revote=False,
        )
        .exclude(decision="ABSTAIN")
        .values("result")
        .distinct()
        .count()
    )

    # For included_results, count:
    # 1. Results with no conflict whose consensus winner is INCLUDE
    # 2. Results with a resolved conflict where final_decision is INCLUDE
    conflicted_result_ids = ConflictResolution.objects.filter(
        result__session=session,
    ).values_list("result_id", flat=True)

    # Bulk-fetch (result_id, decision, min_reviewers_required) for non-conflicted results.
    # Join through result to get min_reviewers_required in one query (no N+1).
    rows = list(
        ReviewerDecision.objects.filter(
            result__session=session,
            is_revote=False,
        )
        .exclude(decision="ABSTAIN")
        .exclude(result_id__in=conflicted_result_ids)
        .values_list("result_id", "decision", "result__min_reviewers_required")
    )

    # Group decisions and min_req by result_id, then bucket via consensus_value
    decisions_by_result: dict = {}
    min_req_by_result: dict = {}
    for result_id, decision, min_req in rows:
        decisions_by_result.setdefault(result_id, []).append(decision)
        min_req_by_result[result_id] = min_req or 1

    non_conflicted_includes = sum(
        1
        for result_id, values in decisions_by_result.items()
        if consensus_value(values, criteria, min_req_by_result.get(result_id, 1))
        == "INCLUDE"
    )

    # Resolved conflicts where final_decision is INCLUDE
    resolved_includes = ConflictResolution.objects.filter(
        result__session=session,
        status=ConflictResolution.STATUS_RESOLVED,
        final_decision__decision="INCLUDE",
    ).count()

    included_results = non_conflicted_includes + resolved_includes

    return reviewed_results, included_results


@receiver(
    post_save,
    sender="results_manager.ProcessedResult",
    dispatch_uid="review_manager.update_total_results_on_save",
)
def update_total_results_on_save(sender, instance, created, **kwargs):
    """Update total_results when ProcessedResult is created."""
    if created and instance.session_id:
        # Use a delayed task to avoid blocking the request
        from django.db import connection

        if connection.in_atomic_block:
            # Register to run after transaction commit
            transaction.on_commit(
                lambda: update_session_statistics(instance.session_id)
            )
        else:
            update_session_statistics(instance.session_id)


@receiver(
    post_delete,
    sender="results_manager.ProcessedResult",
    dispatch_uid="review_manager.update_total_results_on_delete",
)
def update_total_results_on_delete(sender, instance, **kwargs):
    """Update total_results when ProcessedResult is deleted."""
    if instance.session_id:
        # Use a delayed task to avoid blocking the request
        from django.db import connection

        if connection.in_atomic_block:
            # Register to run after transaction commit
            transaction.on_commit(
                lambda: update_session_statistics(instance.session_id)
            )
        else:
            update_session_statistics(instance.session_id)


@receiver(
    post_save,
    sender="review_results.SimpleReviewDecision",
    dispatch_uid="review_manager.update_review_stats_on_save",
)
def update_review_stats_on_save(sender, instance, **kwargs):
    """Update reviewed_results and included_results when review decision changes."""
    if instance.session_id:
        # Check if decision changed
        if kwargs.get("update_fields"):
            if "decision" in kwargs["update_fields"]:
                # Decision was updated
                from django.db import connection

                if connection.in_atomic_block:
                    transaction.on_commit(
                        lambda: update_session_statistics(instance.session_id)
                    )
                else:
                    update_session_statistics(instance.session_id)
        elif kwargs.get("created"):
            # New decision created
            from django.db import connection

            if connection.in_atomic_block:
                transaction.on_commit(
                    lambda: update_session_statistics(instance.session_id)
                )
            else:
                update_session_statistics(instance.session_id)


@receiver(
    post_delete,
    sender="review_results.SimpleReviewDecision",
    dispatch_uid="review_manager.update_review_stats_on_delete",
)
def update_review_stats_on_delete(sender, instance, **kwargs):
    """Update review statistics when review decision is deleted."""
    if instance.session_id:
        from django.db import connection

        if connection.in_atomic_block:
            transaction.on_commit(
                lambda: update_session_statistics(instance.session_id)
            )
        else:
            update_session_statistics(instance.session_id)


def _get_session_id_from_reviewer_decision(instance):
    """Get session_id from a ReviewerDecision via its result FK."""
    try:
        return instance.result.session_id
    except AttributeError:
        return None


@receiver(
    post_save,
    sender="review_results.ReviewerDecision",
    dispatch_uid="review_manager.update_wf2_review_stats_on_save",
)
def update_wf2_review_stats_on_save(sender, instance, created, **kwargs):
    """Update reviewed_results and included_results when a WF2 decision is made."""
    session_id = _get_session_id_from_reviewer_decision(instance)
    if not session_id:
        return

    from django.db import connection

    if connection.in_atomic_block:
        transaction.on_commit(lambda: update_session_statistics(session_id))
    else:
        update_session_statistics(session_id)


@receiver(
    post_delete,
    sender="review_results.ReviewerDecision",
    dispatch_uid="review_manager.update_wf2_review_stats_on_delete",
)
def update_wf2_review_stats_on_delete(sender, instance, **kwargs):
    """Update review statistics when a WF2 decision is deleted."""
    session_id = _get_session_id_from_reviewer_decision(instance)
    if not session_id:
        return

    from django.db import connection

    if connection.in_atomic_block:
        transaction.on_commit(lambda: update_session_statistics(session_id))
    else:
        update_session_statistics(session_id)


@receiver(
    post_save,
    sender="review_results.ConflictResolution",
    dispatch_uid="review_manager.update_stats_on_conflict_resolution",
)
def update_stats_on_conflict_resolution(sender, instance, **kwargs):
    """Update included_results when a conflict is resolved."""
    if kwargs.get("update_fields") and "status" not in kwargs["update_fields"]:
        return

    session_id = None
    try:
        session_id = instance.result.session_id
    except AttributeError:
        return

    if not session_id:
        return

    from django.db import connection

    if connection.in_atomic_block:
        transaction.on_commit(lambda: update_session_statistics(session_id))
    else:
        update_session_statistics(session_id)


def register_denormalized_signals():
    """
    Register all denormalized field signals.
    This should be called from the app's ready() method.
    """
    # Signals are automatically registered when this module is imported
    logger.info("Denormalized field signals registered for SearchSession")
