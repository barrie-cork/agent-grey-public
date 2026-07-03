"""
Blinding Service for Dual-Screening Review

Centralizes logic for enforcing blind review compliance per PRISMA 2020 guidelines.
Determines when reviewers can view each other's decisions based on session configuration.

Key Rules:
- When blind_screening_enforced=True:
  - Reviewers can ONLY see their own decisions
  - Other reviewers' decisions hidden until ALL required reviewers complete the result
  - Conflict status shown only after completion (not individual decisions)
  - Arbitrators can always view all decisions
- When blind_screening_enforced=False:
  - All reviewers can see all decisions (single screening mode)

Created: 2025-10-28
Issue: https://github.com/barrie-cork/agent-grey/issues/24
"""

from django.contrib.auth import get_user_model
from django.db.models import QuerySet, Count, Q

User = get_user_model()


class BlindingService:
    """Service for enforcing blind review compliance in dual-screening."""

    @staticmethod
    def should_blind(session) -> bool:
        """
        Determine if blinding should be enforced for this session.

        Args:
            session: SearchSession instance

        Returns:
            bool: True if blinding should be enforced

        Rules:
            - Requires ReviewConfiguration with blind_screening_enforced=True
            - Requires min_reviewers_per_result >= 2 (dual screening)
        """
        config = session.current_configuration
        if not config:
            return False

        return config.blind_screening_enforced and config.min_reviewers_per_result >= 2

    @staticmethod
    def can_view_decision(decision, requesting_user, session) -> bool:
        """
        Check if requesting_user can view a specific ReviewerDecision.

        Args:
            decision: ReviewerDecision instance
            requesting_user: User making the request
            session: SearchSession instance

        Returns:
            bool: True if user is authorized to view this decision

        Permission Logic:
            1. Always allow viewing own decisions
            2. If blinding NOT enforced → allow viewing all decisions
            3. If blinding enforced:
               a. Allow arbitrators to view all decisions
               b. Allow viewing others' decisions ONLY if result is fully reviewed
        """
        # Always allow viewing own decisions
        if decision.reviewer == requesting_user:
            return True

        # If blinding not enforced, allow viewing all
        if not BlindingService.should_blind(session):
            return True

        # Check if user is arbitrator (can always view all decisions)
        from apps.review_results.models import ReviewerAssignment

        is_arbitrator = ReviewerAssignment.objects.filter(
            result__session=session, reviewer=requesting_user, role="ARBITRATOR"
        ).exists()

        if is_arbitrator:
            return True

        # NEW: Check if user is session owner (early conflict access)
        # Session owners can view conflict existence but NOT other decisions
        # UNLESS they are also an arbitrator (handled above)
        if session.owner == requesting_user:
            # Log early access for audit trail (PRISMA compliance)
            BlindingService._log_session_owner_access(decision, requesting_user)

            # Session owners can view:
            # 1. Their own decisions (handled at line 74)
            # 2. Conflict metadata (handled in serializer)
            # But NOT other reviewers' raw decisions unless arbitrator

            # Return False - actual filtering happens at serializer level
            # ConflictResolutionLeadViewSerializer shows blinded view
            return False

        # For blinded sessions: only allow viewing others' decisions if result fully reviewed
        result = decision.result
        return BlindingService.is_result_fully_reviewed(result, session)

    @staticmethod
    def is_result_fully_reviewed(result, session) -> bool:
        """
        Check if all required reviewers have completed their decisions for a result.

        Args:
            result: SearchResult instance
            session: SearchSession instance

        Returns:
            bool: True if all required reviewers have submitted decisions
        """
        config = session.current_configuration
        if not config:
            return False

        from apps.review_results.models import ReviewerDecision

        # Count non-ABSTAIN decisions for this result
        decision_count = (
            ReviewerDecision.objects.filter(result=result)
            .exclude(decision="ABSTAIN")
            .count()
        )

        return decision_count >= config.min_reviewers_per_result

    @staticmethod
    def filter_decisions_for_user(
        queryset: QuerySet, requesting_user, session
    ) -> QuerySet:
        """
        Filter ReviewerDecision queryset based on blinding rules.

        Args:
            queryset: Base ReviewerDecision queryset
            requesting_user: User making the request
            session: SearchSession instance

        Returns:
            QuerySet: Filtered decisions the user is authorized to view

        Filtering Logic:
            - If NOT blinded → return all decisions
            - If blinded:
              - Always include user's own decisions
              - Include others' decisions only for fully reviewed results
              - Include all decisions if user is arbitrator
        """
        if not BlindingService.should_blind(session):
            return queryset

        from apps.review_results.models import ReviewerAssignment, ReviewerDecision

        # Check if user is arbitrator
        is_arbitrator = ReviewerAssignment.objects.filter(
            result__session=session, reviewer=requesting_user, role="ARBITRATOR"
        ).exists()

        if is_arbitrator:
            return queryset

        # Get result IDs that are fully reviewed
        config = session.current_configuration
        fully_reviewed_results = (
            ReviewerDecision.objects.filter(result__session=session)
            .exclude(decision="ABSTAIN")
            .values("result")
            .annotate(decision_count=Count("id"))
            .filter(decision_count__gte=config.min_reviewers_per_result)
            .values_list("result", flat=True)
        )

        # Filter: own decisions OR decisions for fully reviewed results
        return queryset.filter(
            Q(reviewer=requesting_user) | Q(result__id__in=fully_reviewed_results)
        )

    @staticmethod
    def get_blinding_status(session) -> dict:
        """
        Get comprehensive blinding status for a session.

        Args:
            session: SearchSession instance

        Returns:
            dict: {
                'is_blinded': bool,
                'min_reviewers': int,
                'reason': str (explanation)
            }
        """
        config = session.current_configuration

        if not config:
            return {
                "is_blinded": False,
                "min_reviewers": 1,
                "reason": "No review configuration found",
            }

        is_blinded = BlindingService.should_blind(session)

        if not is_blinded and config.min_reviewers_per_result < 2:
            reason = "Single screening mode (min_reviewers < 2)"
        elif not is_blinded and not config.blind_screening_enforced:
            reason = "Blinding disabled in configuration"
        elif is_blinded:
            reason = "Blind screening enforced per PRISMA 2020"
        else:
            reason = "Unknown configuration state"

        return {
            "is_blinded": is_blinded,
            "min_reviewers": config.min_reviewers_per_result,
            "reason": reason,
        }

    @staticmethod
    def should_show_conflict_details(result, requesting_user, session) -> bool:
        """
        Determine if conflict details (individual decisions) should be shown.

        Args:
            result: SearchResult instance
            requesting_user: User making the request
            session: SearchSession instance

        Returns:
            bool: True if conflict details can be shown

        Rules:
            - Always show if NOT blinded
            - If blinded: only show after result is fully reviewed
            - Arbitrators can always view details
        """
        if not BlindingService.should_blind(session):
            return True

        # Check if user is arbitrator
        from apps.review_results.models import ReviewerAssignment

        is_arbitrator = ReviewerAssignment.objects.filter(
            result=result, reviewer=requesting_user, role="ARBITRATOR"
        ).exists()

        if is_arbitrator:
            return True

        # Only show details if result fully reviewed
        return BlindingService.is_result_fully_reviewed(result, session)

    @staticmethod
    def get_reviewer_display_name(
        reviewer_user, requesting_user, session, assignment=None
    ) -> str:
        """
        Get appropriate display name for a reviewer based on blinding rules.

        Args:
            reviewer_user: User object for the reviewer
            requesting_user: User making the request
            session: SearchSession instance
            assignment: Optional ReviewerAssignment to determine role label

        Returns:
            str: Display name (actual name or blinded placeholder)

        Display Logic:
            - If NOT blinded OR viewing own name → return actual username
            - If blinded and viewing others → return role-based placeholder
              (e.g., "Primary Reviewer", "Secondary Reviewer", "Reviewer")
        """
        # Always show own name
        if reviewer_user == requesting_user:
            return reviewer_user.username

        # If not blinded, show actual name
        if not BlindingService.should_blind(session):
            return reviewer_user.username

        # Blinded: return role-based placeholder
        if assignment:
            role_labels = {
                "PRIMARY": "Primary Reviewer",
                "SECONDARY": "Secondary Reviewer",
                "ARBITRATOR": "Arbitrator",
            }
            return role_labels.get(assignment.role, "Reviewer")

        return "Blinded Reviewer"

    @staticmethod
    def _log_session_owner_access(decision, requesting_user) -> None:
        """
        Create audit log entry for session owner early conflict access.

        Args:
            decision: ReviewerDecision instance being accessed
            requesting_user: Session owner accessing the conflict

        Creates ConflictAccessLog entry for PRISMA compliance auditing.
        Only logs if a conflict exists for the result.

        Related: PRP Lead Reviewer Conflict Access (2025-11-02)
        """
        from apps.review_results.models import ConflictResolution, ConflictAccessLog

        # Check if conflict exists for this result
        conflict = ConflictResolution.objects.filter(result=decision.result).first()

        if conflict:
            # Create audit log entry
            ConflictAccessLog.objects.create(
                organisation=decision.organisation,
                conflict=conflict,
                accessed_by=requesting_user,
                access_type="LIST_VIEW",
                is_session_owner=True,
            )
