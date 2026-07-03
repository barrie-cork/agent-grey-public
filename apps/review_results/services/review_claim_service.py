"""
Review Claim Service for atomic work queue claiming.

Provides race-condition-free result assignment for dual screening workflows
using SELECT FOR UPDATE SKIP LOCKED pattern.
"""

from typing import Optional

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.services.base import BaseService
from apps.organisation.models import Organisation
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import ResultSkip, ReviewerAssignment
from apps.accounts.models import User


class ReviewClaimService(BaseService):
    """
    Service for atomic work queue claiming with concurrency control.

    Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions when
    multiple reviewers claim results simultaneously.
    """

    SERVICE_NAME = "ReviewClaimService"
    SERVICE_VERSION = "1.0.0"

    def _initialize(self) -> None:
        """Initialize review claim service resources."""
        pass

    def health_check(self) -> bool:
        """
        Check if review claim service is healthy.

        Returns:
            bool: True if service is operational
        """
        try:
            # Test database connectivity
            ReviewerAssignment.objects.count()
            return True
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def get_default_config(self) -> dict:
        """Get default configuration for review claim service."""
        return {
            "claim_timeout_minutes": 30,  # Auto-release after 30 min inactivity
            "enable_role_assignment": True,
        }

    @transaction.atomic
    def claim_next_result(
        self,
        reviewer: User,
        organisation: Organisation,
        session_id: Optional[str] = None,
    ) -> Optional[ProcessedResult]:
        """
        Atomically claim next available result for review.

        Uses SELECT FOR UPDATE SKIP LOCKED to prevent race conditions.
        Skips results already reviewed or skipped by this reviewer.

        Args:
            reviewer: User claiming the result
            organisation: Organisation context for scoping
            session_id: Optional session ID to scope results to specific session

        Returns:
            ProcessedResult: Claimed result, or None if no results available

        Raises:
            ValueError: If organisation is None
        """
        if not organisation:
            raise ValueError("Organisation is required for claiming results")

        with self._measure_performance("claim_next_result"):
            try:
                # Build query for available results
                query = (
                    ProcessedResult.objects.filter(
                        session__organisation=organisation,
                        reviewers_completed__lt=F("min_reviewers_required"),
                        is_hidden=False,
                    )
                    .exclude(
                        # Exclude results this reviewer already reviewed
                        reviewer_assignments__reviewer=reviewer,
                        reviewer_assignments__is_active=True,
                    )
                    .exclude(
                        # Exclude results this reviewer previously skipped
                        skips__reviewer=reviewer
                    )
                    .select_for_update(skip_locked=True)
                )

                # Scope to specific session if provided
                if session_id:
                    query = query.filter(session_id=session_id)

                # Order by creation to ensure fairness (FIFO)
                result = query.order_by("created_at").first()

                if not result:
                    self.logger.info(
                        f"No results available for reviewer {reviewer.username} "
                        f"in organisation {organisation.slug}"
                    )
                    return None

                # Determine reviewer role based on how many reviewers already assigned
                role = self._determine_reviewer_role(result)

                # Create assignment
                ReviewerAssignment.objects.create(
                    organisation=organisation,
                    result=result,
                    reviewer=reviewer,
                    role=role,
                    is_active=True,
                )

                self.logger.info(
                    f"Reviewer {reviewer.username} claimed result {result.id} "
                    f"as {role} for organisation {organisation.slug}"
                )

                return result

            except Exception as e:
                self._handle_error(
                    e,
                    operation="claim_next_result",
                    context={
                        "reviewer_id": str(reviewer.id),
                        "organisation_id": str(organisation.id),
                        "session_id": session_id,
                    },
                )
                raise

    def _determine_reviewer_role(self, result: ProcessedResult) -> str:
        """
        Determine the role for the next reviewer.

        Args:
            result: ProcessedResult being assigned

        Returns:
            str: Role (PRIMARY, SECONDARY, or ARBITRATOR)
        """
        active_assignments = result.reviewer_assignments.filter(is_active=True).count()

        if active_assignments == 0:
            return "PRIMARY"
        elif active_assignments == 1:
            return "SECONDARY"
        else:
            return "ARBITRATOR"

    @transaction.atomic
    def release_claim(
        self, result_id: str, reviewer: User, organisation: Organisation
    ) -> bool:
        """
        Release a claimed result (reviewer un-assigns themselves).

        Args:
            result_id: ID of the result to release
            reviewer: User releasing the claim
            organisation: Organisation context

        Returns:
            bool: True if claim was released, False if no active claim existed

        Raises:
            ValueError: If organisation is None
        """
        if not organisation:
            raise ValueError("Organisation is required for releasing claims")

        with self._measure_performance("release_claim"):
            try:
                # Find active assignment
                assignment = ReviewerAssignment.objects.filter(
                    organisation=organisation,
                    result_id=result_id,
                    reviewer=reviewer,
                    is_active=True,
                ).first()

                if not assignment:
                    self.logger.warning(
                        f"No active assignment found for reviewer {reviewer.username} "
                        f"on result {result_id}"
                    )
                    return False

                # Deactivate assignment
                assignment.is_active = False
                assignment.save(update_fields=["is_active"])

                self.logger.info(
                    f"Reviewer {reviewer.username} released claim on result {result_id}"
                )

                return True

            except Exception as e:
                self._handle_error(
                    e,
                    operation="release_claim",
                    context={
                        "reviewer_id": str(reviewer.id),
                        "result_id": result_id,
                        "organisation_id": str(organisation.id),
                    },
                )
                raise

    @transaction.atomic
    def skip_result(
        self,
        result_id: str,
        reviewer: User,
        organisation: Organisation,
        reason: str = "",
    ) -> ResultSkip:
        """
        Skip a result permanently (reviewer won't be assigned this result again).

        Args:
            result_id: ID of the result to skip
            reviewer: User skipping the result
            organisation: Organisation context
            reason: Optional reason for skipping

        Returns:
            ResultSkip: Created skip record

        Raises:
            ValueError: If organisation is None
        """
        if not organisation:
            raise ValueError("Organisation is required for skipping results")

        with self._measure_performance("skip_result"):
            try:
                # Create skip record
                skip, created = ResultSkip.objects.get_or_create(
                    organisation=organisation,
                    result_id=result_id,
                    reviewer=reviewer,
                    defaults={"reason": reason},
                )

                if not created:
                    self.logger.info(
                        f"Result {result_id} already skipped by {reviewer.username}"
                    )
                else:
                    self.logger.info(
                        f"Reviewer {reviewer.username} skipped result {result_id}: {reason}"
                    )

                # Release any active claim on this result
                self.release_claim(result_id, reviewer, organisation)

                return skip

            except Exception as e:
                self._handle_error(
                    e,
                    operation="skip_result",
                    context={
                        "reviewer_id": str(reviewer.id),
                        "result_id": result_id,
                        "organisation_id": str(organisation.id),
                    },
                )
                raise

    def get_assigned_results(self, reviewer: User, organisation: Organisation) -> list:
        """
        Get all results actively assigned to a reviewer.

        Args:
            reviewer: User to get assignments for
            organisation: Organisation context

        Returns:
            list: List of ProcessedResult instances

        Raises:
            ValueError: If organisation is None
        """
        if not organisation:
            raise ValueError("Organisation is required for getting assignments")

        with self._measure_performance("get_assigned_results"):
            try:
                assignments = (
                    ReviewerAssignment.objects.filter(
                        organisation=organisation, reviewer=reviewer, is_active=True
                    )
                    .select_related("result", "result__session")
                    .order_by("-assigned_at")
                )

                results = [assignment.result for assignment in assignments]

                self.logger.debug(
                    f"Retrieved {len(results)} assigned results for {reviewer.username}"
                )

                return results

            except Exception as e:
                self._handle_error(
                    e,
                    operation="get_assigned_results",
                    context={
                        "reviewer_id": str(reviewer.id),
                        "organisation_id": str(organisation.id),
                    },
                )
                raise

    def check_claim_timeout(
        self,
        result_id: str,
        organisation: Organisation,
        timeout_minutes: Optional[int] = None,
    ) -> bool:
        """
        Check if a result claim has timed out and auto-release if needed.

        Args:
            result_id: ID of the result to check
            organisation: Organisation context
            timeout_minutes: Timeout in minutes (default from config)

        Returns:
            bool: True if claim was timed out and released

        Raises:
            ValueError: If organisation is None
        """
        if not organisation:
            raise ValueError("Organisation is required for checking claim timeout")

        timeout = timeout_minutes or self.config.get("claim_timeout_minutes", 30)
        cutoff_time = timezone.now() - timezone.timedelta(minutes=timeout)

        with self._measure_performance("check_claim_timeout"):
            try:
                # Find assignments that haven't been updated recently
                stale_assignments = ReviewerAssignment.objects.filter(
                    organisation=organisation,
                    result_id=result_id,
                    is_active=True,
                    assigned_at__lt=cutoff_time,
                )

                count = stale_assignments.count()
                if count > 0:
                    # Deactivate stale assignments
                    stale_assignments.update(is_active=False)

                    self.logger.warning(
                        f"Auto-released {count} stale claims for result {result_id} "
                        f"(timeout: {timeout} minutes)"
                    )
                    return True

                return False

            except Exception as e:
                self._handle_error(
                    e,
                    operation="check_claim_timeout",
                    context={
                        "result_id": result_id,
                        "organisation_id": str(organisation.id),
                        "timeout_minutes": timeout,
                    },
                )
                raise
