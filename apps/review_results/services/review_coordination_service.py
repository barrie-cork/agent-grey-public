"""
Review Coordination Service for multi-reviewer workflow orchestration.

Provides conflict detection, decision evaluation, and consensus tracking
for dual screening workflows with automatic conflict resolution triggers.
"""

from collections import Counter
from typing import Any, Dict, List, Literal, Optional

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.services.base import BaseService
from apps.organisation.models import Organisation
from apps.results_manager.models import ProcessedResult
from apps.review_results.models import (
    ConflictResolution,
    ReviewerAssignment,
    ReviewerDecision,
)


def decide_consensus(
    decision_values: list[str],
    criteria: str,
    min_reviewers_required: int,
    reviewers_completed: int,
) -> Literal["consensus", "conflict", "pending"]:
    """
    Determine consensus outcome for a set of reviewer decisions.

    Args:
        decision_values: Non-abstain decision strings already filtered by caller.
        criteria: "MAJORITY" (floor(N/2)+1 agree) or "UNANIMOUS" (all agree).
        min_reviewers_required: Configured panel size N.
        reviewers_completed: Denormalised completion counter (includes abstains).

    Returns:
        "pending"   — panel not yet complete, or all reviewers abstained.
        "consensus" — the configured criteria is satisfied.
        "conflict"  — panel complete but criteria not satisfied.
    """
    if reviewers_completed < min_reviewers_required:
        return "pending"
    if not decision_values:
        return "pending"
    if criteria == "UNANIMOUS":
        return "consensus" if len(set(decision_values)) == 1 else "conflict"
    # MAJORITY: strictly more than 50% → floor(N/2) + 1
    threshold = (min_reviewers_required // 2) + 1
    max_count = max(Counter(decision_values).values())
    return "consensus" if max_count >= threshold else "conflict"


def consensus_value(
    decision_values: list[str],
    criteria: str,
    min_reviewers_required: int,
) -> str | None:
    """
    Return the winning decision string when consensus is reached, else None.

    Treats reviewers_completed == min_reviewers_required (assumes full panel).
    Used by reporting consumers to bucket results without re-querying.
    """
    if not decision_values:
        return None
    outcome = decide_consensus(
        decision_values, criteria, min_reviewers_required, min_reviewers_required
    )
    if outcome != "consensus":
        return None
    if criteria == "UNANIMOUS":
        return decision_values[0]
    # MAJORITY: the decision with the highest vote count wins
    return Counter(decision_values).most_common(1)[0][0]


class ReviewCoordinationService(BaseService):
    """
    Service for orchestrating multi-reviewer workflows.

    Handles decision submission, conflict detection, and resolution
    with automatic triggers for background tasks (IRR calculation).
    """

    SERVICE_NAME = "ReviewCoordinationService"
    SERVICE_VERSION = "1.0.0"

    def _initialize(self) -> None:
        """Initialize review coordination service resources."""
        pass

    def health_check(self) -> bool:
        """
        Check if review coordination service is healthy.

        Returns:
            bool: True if service is operational
        """
        try:
            # Test database connectivity
            ReviewerDecision.objects.count()
            return True
        except Exception as e:
            self._handle_error(e, operation="health_check")
            return False

    def get_default_config(self) -> dict:
        """Get default configuration for review coordination service."""
        return {
            "enable_auto_conflict_detection": True,
            "enable_irr_calculation": True,
            "min_decisions_for_irr": 10,
        }

    @transaction.atomic
    def submit_reviewer_decision(
        self,
        result_id: str,
        reviewer: User,
        decision_data: Dict[str, Any],
        organisation: Organisation,
    ) -> ReviewerDecision:
        """
        Submit a reviewer's decision with concurrency control.

        Args:
            result_id: ID of the result being reviewed
            reviewer: User submitting the decision
            decision_data: Decision details including:
                - decision: INCLUDE, EXCLUDE, MAYBE, ABSTAIN
                - exclusion_reason: Required if decision is EXCLUDE
                - confidence_level: 1-3 (Low/Medium/High)
                - notes: Optional reviewer notes
                - screening_stage: SCREENING (default)
                - time_spent_seconds: Optional time tracking
            organisation: Organisation context

        Returns:
            ReviewerDecision: Created decision record

        Raises:
            ValueError: If organisation is None, active assignment missing,
                       or decision already exists for this reviewer+stage
        """
        if not organisation:
            raise ValueError("Organisation is required for submitting decisions")

        with self._measure_performance("submit_reviewer_decision"):
            try:
                # Lock the result to prevent race conditions
                result = ProcessedResult.objects.select_for_update().get(id=result_id)

                # Verify reviewer has an active assignment
                assignment = ReviewerAssignment.objects.filter(
                    organisation=organisation,
                    result=result,
                    reviewer=reviewer,
                    is_active=True,
                ).first()

                if not assignment:
                    raise ValueError(
                        f"Reviewer {reviewer.username} does not have an active "
                        f"assignment for result {result_id}"
                    )

                # Get screening stage (default to SCREENING)
                screening_stage = decision_data.get("screening_stage", "SCREENING")

                # Check for duplicate decision (UniqueConstraint will catch this,
                # but explicit check provides better error message)
                existing = ReviewerDecision.objects.filter(
                    result=result, reviewer=reviewer, screening_stage=screening_stage
                ).exists()

                if existing:
                    raise ValueError(
                        f"Reviewer {reviewer.username} has already submitted a "
                        f"decision for result {result_id} at stage {screening_stage}"
                    )

                # Create immutable decision record
                decision = ReviewerDecision.objects.create(
                    organisation=organisation,
                    result=result,
                    reviewer=reviewer,
                    assignment=assignment,
                    decision=decision_data["decision"],
                    exclusion_reason=decision_data.get("exclusion_reason", ""),
                    confidence_level=decision_data.get("confidence_level", 2),
                    notes=decision_data.get("notes", ""),
                    screening_stage=screening_stage,
                    is_blinded=True,  # Initial decisions are blinded
                    is_revote=False,  # Initial decision (not a re-vote)
                    time_spent_seconds=decision_data.get("time_spent_seconds"),
                )

                # Update denormalised counter on the locked instance
                # This ensures atomic increment within the locked transaction
                result.reviewers_completed += 1
                result.save(update_fields=["reviewers_completed"])

                # Check if enough reviews have been submitted
                if result.reviewers_completed >= result.min_reviewers_required:
                    self._evaluate_decisions(result, screening_stage)

                self.logger.info(
                    f"Reviewer {reviewer.username} submitted {decision_data['decision']} "
                    f"decision for result {result_id} ({result.reviewers_completed}/"
                    f"{result.min_reviewers_required} reviewers)"
                )

                return decision

            except Exception as e:
                self._handle_error(
                    e,
                    operation="submit_reviewer_decision",
                    context={
                        "reviewer_id": str(reviewer.id),
                        "result_id": result_id,
                        "organisation_id": str(organisation.id),
                        "decision": decision_data.get("decision"),
                    },
                )
                raise

    def detect_conflicts(
        self, session, screening_stage: str = "SCREENING"
    ) -> List[ConflictResolution]:
        """
        Detect all conflicts in a session after all reviewers complete.

        Scans all results in the session and creates ConflictResolution
        records for any disagreements between reviewers.

        Args:
            session: SearchSession instance to detect conflicts for
            screening_stage: Screening stage to evaluate (default: SCREENING)

        Returns:
            List[ConflictResolution]: List of conflicts detected and created

        Conflict types:
            - INCLUDE_EXCLUDE: One reviewer includes, another excludes
            - LOW_CONFIDENCE: Mixed decisions (MAYBE involved, or other non-INCLUDE/EXCLUDE combos)
        """
        with self._measure_performance("detect_conflicts"):
            try:
                conflicts_created = []

                # Read session-level config once — criteria and panel size come
                # from the config (reliable); the per-result denormalised fields may
                # be stale when ReviewerDecision rows are created outside the service.
                cfg = session.current_configuration
                criteria = cfg.consensus_criteria if cfg else "MAJORITY"
                min_req = cfg.min_reviewers_per_result if cfg else 2

                # Get all results in session
                results = ProcessedResult.objects.filter(
                    session=session
                ).prefetch_related("reviewer_decisions")

                for result in results:
                    # Get all submitted decisions for this result. Count ALL
                    # (incl. ABSTAIN) for the completion gate, but tally only
                    # non-ABSTAIN for the consensus decision.
                    all_decisions = list(
                        ReviewerDecision.objects.filter(
                            result=result, screening_stage=screening_stage
                        ).select_related("reviewer")
                    )
                    decisions = [d for d in all_decisions if d.decision != "ABSTAIN"]
                    decision_values = [d.decision for d in decisions]

                    # Completion gate: skip until the configured panel size has
                    # submitted. Derive completion from the actual submitted-
                    # decision count (incl. ABSTAIN), NOT the denormalised
                    # reviewers_completed — that counter is unset when rows are
                    # created outside submit_reviewer_decision (imports, batch
                    # ops, tests). Counting ABSTAIN here keeps a 2-INCLUDE+
                    # 1-ABSTAIN N=3 case in consensus, matching the live
                    # evaluator (#203 / PR #205 CR).
                    outcome = decide_consensus(
                        decision_values,
                        criteria,
                        min_req,
                        len(all_decisions),
                    )
                    if outcome == "pending":
                        continue

                    # Check if conflict already exists for this result
                    existing_conflict = ConflictResolution.objects.filter(
                        result=result
                    ).first()

                    if existing_conflict:
                        continue  # Skip if conflict already detected

                    if outcome == "consensus":
                        # Criteria satisfied — mark result
                        result.consensus_reached = True
                        result.save(update_fields=["consensus_reached"])
                    else:
                        # Conflict detected - create record
                        conflict_type = self._determine_conflict_type(decision_values)

                        conflict = ConflictResolution.objects.create(
                            organisation=session.organisation,
                            result=result,
                            conflict_type=conflict_type,
                            status="PENDING",
                        )

                        # Link conflicting decisions
                        conflict.conflicting_decisions.set(decisions)

                        conflicts_created.append(conflict)

                        self.logger.info(
                            f"Conflict detected for result {result.id}: {conflict_type} "
                            f"(decisions: {decision_values})"
                        )

                self.logger.info(
                    f"Detected {len(conflicts_created)} conflicts in session {session.id}"
                )

                return conflicts_created

            except Exception as e:
                self._handle_error(
                    e,
                    operation="detect_conflicts",
                    context={
                        "session_id": str(session.id),
                        "screening_stage": screening_stage,
                    },
                )
                raise

    def _evaluate_decisions(
        self, result: ProcessedResult, screening_stage: str
    ) -> None:
        """
        Evaluate all decisions for a result and detect conflicts.

        Automatically triggers conflict resolution or marks consensus.

        Args:
            result: ProcessedResult with completed reviews
            screening_stage: Screening stage to evaluate
        """
        # Get all non-abstain decisions for this stage
        decisions = list(
            ReviewerDecision.objects.filter(
                result=result, screening_stage=screening_stage
            )
            .exclude(decision="ABSTAIN")
            .select_related("reviewer")
        )

        if not decisions:
            self.logger.warning(
                f"No non-abstain decisions found for result {result.id} "
                f"at stage {screening_stage}"
            )
            return

        # Skip if an active conflict already exists for this result
        # (prevents duplicates from concurrent submissions)
        if ConflictResolution.objects.filter(
            result=result,
            status__in=["PENDING", "IN_DISCUSSION", "ESCALATED"],
        ).exists():
            self.logger.debug(
                f"Active conflict already exists for result {result.id}, skipping"
            )
            return

        # Extract decision values and read consensus criteria from session config
        decision_values = [d.decision for d in decisions]
        criteria = (
            result.session.current_configuration.consensus_criteria
            if result.session.current_configuration
            else "MAJORITY"
        )

        outcome = decide_consensus(
            decision_values,
            criteria,
            result.min_reviewers_required,
            result.reviewers_completed,
        )

        if outcome == "pending":
            # All reviewers abstained or panel incomplete — nothing to decide yet
            return

        if outcome == "consensus":
            result.consensus_reached = True
            result.save(update_fields=["consensus_reached"])

            self.logger.info(
                f"Consensus reached for result {result.id}: {decision_values}"
            )

            # Trigger IRR calculation if enabled
            if self.config.get("enable_irr_calculation", True):
                self._trigger_irr_calculation(result, decisions)

        else:
            # Conflict detected
            conflict_type = self._determine_conflict_type(decision_values)

            result.consensus_reached = False
            result.save(update_fields=["consensus_reached"])

            # Create conflict record (DB constraint prevents duplicates)
            conflict = ConflictResolution.objects.create(
                organisation=result.session.organisation,
                result=result,
                conflict_type=conflict_type,
                status="PENDING",
            )

            # Link conflicting decisions
            conflict.conflicting_decisions.set(decisions)

            self.logger.warning(
                f"Conflict detected for result {result.id}: {conflict_type} "
                f"(decisions: {decision_values})"
            )

    def _determine_conflict_type(self, decisions: List[str]) -> str:
        """
        Classify the type of conflict based on decision values.

        Args:
            decisions: List of decision strings (INCLUDE, EXCLUDE, MAYBE)

        Returns:
            str: Conflict type (INCLUDE_EXCLUDE or LOW_CONFIDENCE)
        """
        unique_decisions = set(decisions)

        if "INCLUDE" in unique_decisions and "EXCLUDE" in unique_decisions:
            return "INCLUDE_EXCLUDE"
        else:
            return "LOW_CONFIDENCE"

    def _trigger_irr_calculation(
        self, result: ProcessedResult, decisions: List[ReviewerDecision]
    ) -> None:
        """
        Trigger background IRR calculation for reviewer pairs.

        Args:
            result: ProcessedResult with completed reviews
            decisions: List of ReviewerDecision instances
        """
        from itertools import combinations

        # Need at least 2 reviewers for IRR
        if len(decisions) < 2:
            self.logger.debug(
                f"Skipping IRR calculation for result {result.id}: "
                f"requires at least 2 reviewers, got {len(decisions)}"
            )
            return

        # Check if we have enough decisions across session for meaningful IRR
        session = result.session
        total_decisions = (
            ReviewerDecision.objects.filter(
                result__session=session, screening_stage="SCREENING"
            )
            .exclude(decision="ABSTAIN")
            .count()
        )

        min_decisions = self.config.get("min_decisions_for_irr", 10)
        if total_decisions < min_decisions:
            self.logger.debug(
                f"Skipping IRR calculation for session {session.id}: "
                f"requires at least {min_decisions} decisions, got {total_decisions}"
            )
            return

        # Trigger Celery task for IRR calculation for all reviewer pairs
        try:
            from apps.review_results.tasks import calculate_irr_task

            for decision_a, decision_b in combinations(decisions, 2):
                reviewer_a_id = str(decision_a.reviewer.id)
                reviewer_b_id = str(decision_b.reviewer.id)

                calculate_irr_task.delay(
                    session_id=str(session.id),
                    reviewer_a_id=reviewer_a_id,
                    reviewer_b_id=reviewer_b_id,
                )

                self.logger.info(
                    f"Triggered IRR calculation for reviewers "
                    f"{decision_a.reviewer.username} and {decision_b.reviewer.username} "
                    f"in session {session.id}"
                )

        except ImportError:
            self.logger.warning(
                "Cannot trigger IRR calculation: tasks module not yet available"
            )
        except Exception as e:
            self.logger.error(f"Failed to trigger IRR calculation: {e}")

    @transaction.atomic
    def resolve_conflict(
        self,
        conflict_id: str,
        resolver: User,
        resolution_data: Dict[str, Any],
        organisation: Organisation,
    ) -> ConflictResolution:
        """
        Resolve a conflict with a final decision.

        Args:
            conflict_id: ID of the ConflictResolution to resolve
            resolver: User resolving the conflict
            resolution_data: Resolution details including:
                - decision: Final decision (INCLUDE/EXCLUDE)
                - resolution_method: CONSENSUS, ARBITRATION, MAJORITY, SENIOR_OVERRIDE
                - resolution_notes: Notes about the resolution
                - exclusion_reason: Required if decision is EXCLUDE
            organisation: Organisation context

        Returns:
            ConflictResolution: Updated conflict record

        Raises:
            ValueError: If organisation is None or conflict already resolved
        """
        if not organisation:
            raise ValueError("Organisation is required for resolving conflicts")

        with self._measure_performance("resolve_conflict"):
            try:
                # Lock the conflict record
                conflict = ConflictResolution.objects.select_for_update().get(
                    id=conflict_id, organisation=organisation
                )

                if conflict.status == "RESOLVED":
                    raise ValueError(f"Conflict {conflict_id} is already resolved")

                if conflict.status == "ESCALATED":
                    raise ValueError(
                        f"Conflict {conflict_id} is escalated and must be "
                        f"resolved through arbitration"
                    )

                # Create resolution decision (non-blinded)
                # If resolver already voted on this result, mark as revote
                # to avoid unique constraint violation
                already_voted = ReviewerDecision.objects.filter(
                    result=conflict.result,
                    reviewer=resolver,
                    screening_stage="SCREENING",
                    is_revote=False,
                ).exists()

                final_decision = ReviewerDecision.objects.create(
                    organisation=organisation,
                    result=conflict.result,
                    reviewer=resolver,
                    decision=resolution_data["decision"],
                    exclusion_reason=resolution_data.get("exclusion_reason", ""),
                    notes=resolution_data.get("resolution_notes", ""),
                    screening_stage="SCREENING",
                    is_blinded=False,  # Resolver sees previous decisions
                    is_revote=already_voted,  # True if resolver already voted
                )

                # Update conflict record
                conflict.status = "RESOLVED"
                conflict.resolution_method = resolution_data["resolution_method"]
                conflict.final_decision = final_decision
                conflict.resolved_at = timezone.now()
                conflict.resolved_by = resolver
                conflict.resolution_notes = resolution_data.get("resolution_notes", "")
                conflict.save()

                # Mark consensus as reached
                result = conflict.result
                result.consensus_reached = True
                result.save(update_fields=["consensus_reached"])

                self.logger.info(
                    f"Conflict {conflict_id} resolved by {resolver.username} "
                    f"with decision {resolution_data['decision']} "
                    f"(method: {resolution_data['resolution_method']})"
                )

                return conflict

            except Exception as e:
                self._handle_error(
                    e,
                    operation="resolve_conflict",
                    context={
                        "conflict_id": conflict_id,
                        "resolver_id": str(resolver.id),
                        "organisation_id": str(organisation.id),
                    },
                )
                raise

    def get_pending_conflicts(
        self, organisation: Organisation, session_id: Optional[str] = None
    ) -> List[ConflictResolution]:
        """
        Get all pending conflicts for an organisation or session.

        Args:
            organisation: Organisation context
            session_id: Optional session ID to filter by

        Returns:
            List[ConflictResolution]: List of pending conflicts

        Raises:
            ValueError: If organisation is None
        """
        if not organisation:
            raise ValueError("Organisation is required for getting conflicts")

        with self._measure_performance("get_pending_conflicts"):
            try:
                query = (
                    ConflictResolution.objects.filter(
                        organisation=organisation,
                        status__in=["PENDING", "IN_DISCUSSION", "ESCALATED"],
                    )
                    .prefetch_related("conflicting_decisions__reviewer")
                    .select_related("result", "result__session")
                    .order_by("-detected_at")
                )

                if session_id:
                    query = query.filter(result__session_id=session_id)

                conflicts = list(query)

                self.logger.debug(
                    f"Retrieved {len(conflicts)} pending conflicts for "
                    f"organisation {organisation.slug}"
                )

                return conflicts

            except Exception as e:
                self._handle_error(
                    e,
                    operation="get_pending_conflicts",
                    context={
                        "organisation_id": str(organisation.id),
                        "session_id": session_id,
                    },
                )
                raise
