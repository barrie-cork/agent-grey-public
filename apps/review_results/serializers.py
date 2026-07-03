"""
DRF Serializers for Dual Screening APIs.

Provides serialization for:
- ProcessedResult (search results for review)
- ReviewerDecision (reviewer decisions with validation)
- ReviewerAssignment (work queue assignments)
- ConflictResolution (conflict tracking and resolution)
- InterRaterReliability (Cohen's Kappa metrics)
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.results_manager.models import ProcessedResult
from apps.review_manager.models import SearchSession
from apps.review_results.models import (
    ConflictComment,
    ConflictResolution,
    InDiscussionVote,
    InDiscussionVoteResponse,
    InterRaterReliability,
    ReviewerAssignment,
    ReviewerDecision,
    RevoteProposal,
    SimpleReviewDecision,
)

User = get_user_model()


# ============================================================================
# SIMPLE/NESTED SERIALIZERS
# ============================================================================


class SimpleUserSerializer(serializers.ModelSerializer):
    """Minimal user representation for nested serialization."""

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]
        read_only_fields = fields


class SimpleSessionSerializer(serializers.ModelSerializer):
    """Minimal session representation for nested serialization."""

    class Meta:
        model = SearchSession
        fields = ["id", "title", "status"]
        read_only_fields = fields


# ============================================================================
# PROCESSED RESULT SERIALIZERS
# ============================================================================


class ProcessedResultSerializer(serializers.ModelSerializer):
    """
    Serializer for ProcessedResult (search results to be reviewed).

    Includes review status indicators and assignment tracking.
    """

    session = SimpleSessionSerializer(read_only=True)
    is_reviewed = serializers.BooleanField(read_only=True)
    reviewers_completed = serializers.IntegerField(read_only=True)
    min_reviewers_required = serializers.IntegerField(read_only=True)
    consensus_reached = serializers.BooleanField(read_only=True)
    review_progress = serializers.SerializerMethodField()
    my_decision = serializers.SerializerMethodField()

    class Meta:
        model = ProcessedResult
        fields = [
            "id",
            "session",
            "title",
            "snippet",
            "url",
            "authors",
            "publication_year",
            "document_type",
            "is_pdf",
            "is_reviewed",
            "review_mode",
            "reviewers_completed",
            "min_reviewers_required",
            "consensus_reached",
            "review_progress",
            "my_decision",
            "processed_at",
        ]
        read_only_fields = [
            "id",
            "session",
            "is_reviewed",
            "reviewers_completed",
            "consensus_reached",
            "processed_at",
        ]

    def get_review_progress(self, obj):
        """Calculate review progress percentage."""
        if obj.min_reviewers_required == 0:
            return 0
        return round((obj.reviewers_completed / obj.min_reviewers_required) * 100, 1)

    def get_my_decision(self, obj) -> str | None:
        """Return the requesting user's existing decision for this result."""
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return None

        # Fast path: a list view (e.g. the WF2 work queue) can pass a prebuilt
        # {result_id: decision} lookup that mirrors active_for semantics
        # (non-revote ReviewerDecision rows), avoiding a per-row query.
        lookup = self.context.get("my_decision_lookup")
        if lookup is not None:
            decision = lookup.get(obj.pk)
            if not decision:
                return None
            # Workflow #2 stores uppercase; this serializer returns lowercase.
            return decision.lower()

        session = obj.session
        config = getattr(session, "current_configuration", None)

        if config and config.is_workflow_2:
            decision = (
                ReviewerDecision.objects.active_for(obj, request.user)
                .values_list("decision", flat=True)
                .first()
            )
            # Workflow #2 stores uppercase (INCLUDE, EXCLUDE, MAYBE)
            return decision.lower() if decision else None
        else:
            decision = (
                SimpleReviewDecision.objects.filter(result=obj)
                .values_list("decision", flat=True)
                .first()
            )
            # Workflow #1 stores lowercase; 'pending' means no decision yet
            if decision and decision != "pending":
                return decision
            return None


# ============================================================================
# REVIEWER DECISION SERIALIZERS
# ============================================================================


class ReviewerDecisionInputSerializer(serializers.Serializer):
    """
    Input serializer for submitting reviewer decisions.

    Validates decision data before passing to service layer.
    """

    decision = serializers.ChoiceField(
        choices=["INCLUDE", "EXCLUDE", "MAYBE", "ABSTAIN"],
        required=True,
    )
    exclusion_reason = serializers.CharField(
        max_length=100,
        allow_blank=True,
        required=False,
    )
    confidence_level = serializers.IntegerField(
        min_value=1,
        max_value=3,
        default=2,
    )
    notes = serializers.CharField(
        allow_blank=True,
        required=False,
    )
    time_spent_seconds = serializers.IntegerField(
        min_value=0,
        required=False,
        allow_null=True,
    )
    screening_stage = serializers.CharField(
        default="SCREENING",
        required=False,
    )

    def validate(self, attrs):
        """Validate that exclusion_reason is provided when decision is EXCLUDE."""
        if attrs.get("decision") == "EXCLUDE" and not attrs.get("exclusion_reason"):
            raise serializers.ValidationError(
                {"exclusion_reason": "This field is required when decision is EXCLUDE."}
            )
        return attrs


class ReviewerDecisionOutputSerializer(serializers.ModelSerializer):
    """
    Output serializer for ReviewerDecision instances.

    READ-ONLY: Decisions are immutable after creation.
    Enforces blinding rules per PRISMA 2020 compliance.
    """

    reviewer = SimpleUserSerializer(read_only=True)
    result = ProcessedResultSerializer(read_only=True)
    decision_display = serializers.CharField(
        source="get_decision_display", read_only=True
    )
    confidence_display = serializers.CharField(
        source="get_confidence_level_display", read_only=True
    )

    class Meta:
        model = ReviewerDecision
        fields = [
            "id",
            "result",
            "reviewer",
            "decision",
            "decision_display",
            "exclusion_reason",
            "confidence_level",
            "confidence_display",
            "notes",
            "decided_at",
            "time_spent_seconds",
            "screening_stage",
            "is_blinded",
            "is_revote",
            "revote_proposal",
            "version",
        ]
        read_only_fields = fields  # All fields read-only (immutable)

    def to_representation(self, instance):
        """
        Override to enforce blinding rules.

        Redacts reviewer information if:
        - Blind screening is enforced for the session
        - Requesting user is not the decision's reviewer
        - Result is not fully reviewed by all required reviewers
        """
        data = super().to_representation(instance)

        # Get context for blinding check
        request = self.context.get("request")
        session = self.context.get("session") or instance.result.session

        if not request or not request.user:
            return data

        # Import here to avoid circular dependency
        from apps.review_results.services.blinding_service import BlindingService

        # Check if this decision can be viewed by requesting user
        can_view = BlindingService.can_view_decision(
            decision=instance, requesting_user=request.user, session=session
        )

        # Redact reviewer information if not authorized
        if not can_view:
            # Get assignment for role-based label
            from apps.review_results.models import ReviewerAssignment

            assignment = ReviewerAssignment.objects.filter(
                result=instance.result, reviewer=instance.reviewer
            ).first()

            blinded_name = BlindingService.get_reviewer_display_name(
                reviewer_user=instance.reviewer,
                requesting_user=request.user,
                session=session,
                assignment=assignment,
            )

            # Replace reviewer with blinded placeholder
            data["reviewer"] = {
                "id": "blinded",
                "username": blinded_name,
                "email": "blinded@reviewer.local",
            }

        return data


class ReviewerDecisionMinimalSerializer(serializers.ModelSerializer):
    """
    Minimal decision serializer for nested use (e.g., in conflicts).
    Enforces blinding rules per PRISMA 2020 compliance.
    """

    reviewer = SimpleUserSerializer(read_only=True)

    class Meta:
        model = ReviewerDecision
        fields = [
            "id",
            "reviewer",
            "decision",
            "exclusion_reason",
            "confidence_level",
            "decided_at",
        ]

    def to_representation(self, instance):
        """Override to enforce blinding rules (same as full serializer)."""
        data = super().to_representation(instance)

        # Get context for blinding check
        request = self.context.get("request")
        session = self.context.get("session") or instance.result.session

        if not request or not request.user:
            return data

        # Import here to avoid circular dependency
        from apps.review_results.services.blinding_service import BlindingService

        # Check if this decision can be viewed by requesting user
        can_view = BlindingService.can_view_decision(
            decision=instance, requesting_user=request.user, session=session
        )

        # Redact reviewer information if not authorized
        if not can_view:
            # Get assignment for role-based label
            from apps.review_results.models import ReviewerAssignment

            assignment = ReviewerAssignment.objects.filter(
                result=instance.result, reviewer=instance.reviewer
            ).first()

            blinded_name = BlindingService.get_reviewer_display_name(
                reviewer_user=instance.reviewer,
                requesting_user=request.user,
                session=session,
                assignment=assignment,
            )

            # Replace reviewer with blinded placeholder
            data["reviewer"] = {
                "id": "blinded",
                "username": blinded_name,
                "email": "blinded@reviewer.local",
            }

        return data


# ============================================================================
# REVIEWER ASSIGNMENT SERIALIZERS
# ============================================================================


class ReviewerAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for ReviewerAssignment (work queue tracking)."""

    reviewer = SimpleUserSerializer(read_only=True)
    result = ProcessedResultSerializer(read_only=True)
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = ReviewerAssignment
        fields = [
            "id",
            "result",
            "reviewer",
            "role",
            "role_display",
            "assigned_at",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "result",
            "reviewer",
            "role",
            "assigned_at",
        ]


# ============================================================================
# CONFLICT RESOLUTION SERIALIZERS
# ============================================================================


class ConflictResolutionListSerializer(serializers.ModelSerializer):
    """
    List serializer for ConflictResolution (for list views).

    Includes minimal nested data for performance.
    """

    result = ProcessedResultSerializer(read_only=True)
    conflict_type_display = serializers.CharField(
        source="get_conflict_type_display",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    conflicting_decision_count = serializers.SerializerMethodField()
    time_pending_hours = serializers.SerializerMethodField()
    sla_info = serializers.SerializerMethodField()

    class Meta:
        model = ConflictResolution
        fields = [
            "id",
            "result",
            "conflict_type",
            "conflict_type_display",
            "status",
            "status_display",
            "detected_at",
            "conflicting_decision_count",
            "time_pending_hours",
            "sla_info",
        ]
        read_only_fields = fields

    def get_conflicting_decision_count(self, obj):
        """
        Count of conflicting decisions (uses prefetched data).

        IMPORTANT: Uses len() instead of count() to avoid N+1 query.
        The view MUST prefetch 'conflicting_decisions' for this to work.
        """
        return len(obj.conflicting_decisions.all())

    def get_time_pending_hours(self, obj):
        """Calculate hours since conflict detection."""
        if obj.status == "RESOLVED":
            return None
        from django.utils import timezone

        delta = timezone.now() - obj.detected_at
        return round(delta.total_seconds() / 3600, 1)

    def get_sla_info(self, obj) -> dict | None:
        """Compute SLA deadline info for the conflict."""
        info = obj.get_sla_info()
        if info is None:
            return None
        return {
            "deadline": info["deadline"].isoformat(),
            "hours_remaining": round(info["hours_remaining"], 1),
            "hours_overdue": round(info["hours_overdue"], 1),
            "percent_elapsed": info["percent_elapsed"],
            "is_approaching": info["is_approaching"],
            "is_critical": info["is_critical"],
            "is_overdue": info["is_overdue"],
            "sla_hours": info["sla_hours"],
        }


class ConflictResolutionDetailSerializer(serializers.ModelSerializer):
    """
    Detail serializer for ConflictResolution (for detail/resolve views).

    Includes full nested decision data for conflict resolution.
    Extended in Phase 2 to include discussion summary and active revote proposal.
    """

    result = ProcessedResultSerializer(read_only=True)
    conflicting_decisions = ReviewerDecisionMinimalSerializer(many=True, read_only=True)
    final_decision = ReviewerDecisionOutputSerializer(read_only=True)
    resolved_by = SimpleUserSerializer(read_only=True)
    conflict_type_display = serializers.CharField(
        source="get_conflict_type_display",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    resolution_method_display = serializers.CharField(
        source="get_resolution_method_display",
        read_only=True,
    )
    discussion_summary = serializers.SerializerMethodField()
    active_revote_proposal = serializers.SerializerMethodField()
    sla_info = serializers.SerializerMethodField()

    class Meta:
        model = ConflictResolution
        fields = [
            "id",
            "result",
            "conflicting_decisions",
            "conflict_type",
            "conflict_type_display",
            "status",
            "status_display",
            "detected_at",
            "resolution_method",
            "resolution_method_display",
            "final_decision",
            "resolved_at",
            "resolved_by",
            "resolution_notes",
            "discussion_summary",
            "active_revote_proposal",
            "sla_info",
        ]
        read_only_fields = [
            "id",
            "result",
            "conflicting_decisions",
            "conflict_type",
            "detected_at",
        ]

    def get_discussion_summary(self, obj):
        """Get discussion summary using model method."""
        return obj.get_discussion_summary()

    def get_active_revote_proposal(self, obj):
        """Get the active revote proposal if one exists."""
        active_proposal = obj.get_active_revote_proposal()
        if active_proposal:
            # Import here to avoid circular import
            from apps.review_results.serializers import RevoteProposalSerializer

            return RevoteProposalSerializer(active_proposal, context=self.context).data
        return None

    def get_sla_info(self, obj) -> dict | None:
        """Compute SLA deadline info for the conflict."""
        info = obj.get_sla_info()
        if info is None:
            return None
        return {
            "deadline": info["deadline"].isoformat(),
            "hours_remaining": round(info["hours_remaining"], 1),
            "hours_overdue": round(info["hours_overdue"], 1),
            "percent_elapsed": info["percent_elapsed"],
            "is_approaching": info["is_approaching"],
            "is_critical": info["is_critical"],
            "is_overdue": info["is_overdue"],
            "sla_hours": info["sla_hours"],
        }


class ConflictResolutionLeadViewSerializer(serializers.ModelSerializer):
    """
    Blinded serializer for session owner viewing conflicts during review phase.

    Shows:
    - Conflict metadata (type, status, created date)
    - Result title
    - Session owner's own decision (if they reviewed this result)
    - Decision count (e.g., "2 reviewers decided")

    Hides:
    - Other reviewers' decisions
    - Other reviewers' names
    - Detailed notes (unless owner is arbitrator)

    Purpose: Enable lead reviewers to identify calibration needs early while
    maintaining PRISMA blinding compliance.

    Related: PRP Lead Reviewer Conflict Access (2025-11-02)
    """

    result_title = serializers.CharField(source="result.title", read_only=True)
    result_url = serializers.CharField(source="result.url", read_only=True)
    own_decision = serializers.SerializerMethodField()
    decision_count = serializers.SerializerMethodField()
    can_view_details = serializers.SerializerMethodField()

    class Meta:
        model = ConflictResolution
        fields = [
            "id",
            "result_title",
            "result_url",
            "conflict_type",
            "status",
            "detected_at",
            "own_decision",
            "decision_count",
            "can_view_details",
        ]
        read_only_fields = fields

    def get_own_decision(self, obj):
        """
        Return requesting user's decision if they reviewed this result.

        Returns:
            dict: User's decision data (decision, confidence, timestamp)
            None: If user has not reviewed this result
        """
        request = self.context.get("request")
        if not request:
            return None

        from apps.review_results.models import ReviewerDecision

        own_decision = ReviewerDecision.objects.filter(
            result=obj.result, reviewer=request.user
        ).first()

        if own_decision:
            return {
                "decision": own_decision.decision,
                "confidence_level": own_decision.confidence_level,
                "decided_at": own_decision.decided_at.isoformat()
                if own_decision.decided_at
                else None,
            }

        return None

    def get_decision_count(self, obj):
        """
        Return count of decisions without revealing reviewers.

        Returns:
            int: Number of decisions for this result
        """
        return obj.conflicting_decisions.count()

    def get_can_view_details(self, obj):
        """
        Check if user is arbitrator (can see full details).

        Returns:
            bool: True if user is arbitrator for this result
        """
        request = self.context.get("request")
        if not request:
            return False

        from apps.review_results.models import ReviewerAssignment

        # Check if user is arbitrator for this result
        is_arbitrator = ReviewerAssignment.objects.filter(
            result=obj.result, reviewer=request.user, role="ARBITRATOR", is_active=True
        ).exists()

        return is_arbitrator


class ConflictResolutionInputSerializer(serializers.Serializer):
    """Input serializer for resolving conflicts."""

    decision = serializers.ChoiceField(
        choices=["INCLUDE", "EXCLUDE", "MAYBE"],
        required=True,
    )
    exclusion_reason = serializers.CharField(
        max_length=100,
        allow_blank=True,
        required=False,
    )
    resolution_notes = serializers.CharField(
        allow_blank=True,
        required=False,
    )

    def validate(self, attrs):
        """Validate exclusion_reason is provided for EXCLUDE decisions.

        Falls back to resolution_notes if exclusion_reason is not provided,
        since conflict resolution rationale serves the same purpose.
        """
        if attrs.get("decision") == "EXCLUDE" and not attrs.get("exclusion_reason"):
            if attrs.get("resolution_notes"):
                attrs["exclusion_reason"] = attrs["resolution_notes"]
            else:
                raise serializers.ValidationError(
                    {
                        "exclusion_reason": "This field is required when decision is EXCLUDE."
                    }
                )
        return attrs


# ============================================================================
# INTER-RATER RELIABILITY SERIALIZERS
# ============================================================================


class InterRaterReliabilitySerializer(serializers.ModelSerializer):
    """Serializer for InterRaterReliability metrics."""

    reviewer_a = SimpleUserSerializer(read_only=True)
    reviewer_b = SimpleUserSerializer(read_only=True)
    search_session = SimpleSessionSerializer(read_only=True)
    meets_cochrane_threshold = serializers.SerializerMethodField()

    class Meta:
        model = InterRaterReliability
        fields = [
            "id",
            "search_session",
            "reviewer_a",
            "reviewer_b",
            "cohens_kappa",
            "percentage_agreement",
            "total_comparisons",
            "agreements",
            "disagreements",
            "screening_stage",
            "calculated_at",
            "calculation_window_start",
            "calculation_window_end",
            "meets_cochrane_threshold",
        ]
        read_only_fields = fields

    def get_meets_cochrane_threshold(self, obj):
        """Check if kappa meets Cochrane minimum threshold (≥0.70)."""
        if obj.cohens_kappa is None:
            return None
        return obj.cohens_kappa >= 0.70


# ============================================================================
# CLAIM RESULT SERIALIZERS
# ============================================================================


class ClaimResultInputSerializer(serializers.Serializer):
    """Input serializer for claiming next result."""

    session_id = serializers.UUIDField(required=False, allow_null=True)
    screening_stage = serializers.CharField(default="SCREENING", required=False)


class ClaimResultOutputSerializer(serializers.Serializer):
    """Output serializer for claim result response."""

    result = ProcessedResultSerializer(read_only=True)
    assignment = ReviewerAssignmentSerializer(read_only=True)
    message = serializers.CharField(read_only=True)


# ============================================================================
# CONSENSUS DISCUSSION SERIALIZERS (Phase 2)
# ============================================================================


class ConflictCommentSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for ConflictComment with nested author and replies.

    Supports threaded comment display with recursive reply serialization.
    Excludes soft-deleted comments from replies.
    """

    author = SimpleUserSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    discussion_vote = serializers.SerializerMethodField()
    criterion_tag_display = serializers.SerializerMethodField()

    class Meta:
        model = ConflictComment
        fields = [
            "id",
            "conflict",
            "author",
            "parent",
            "content",
            "content_html",
            "created_at",
            "updated_at",
            "is_edited",
            "edited_at",
            "is_deleted",
            "is_system_message",
            "criterion_tag",
            "criterion_tag_display",
            "replies",
            "discussion_vote",
        ]
        read_only_fields = fields

    def get_criterion_tag_display(self, obj: ConflictComment) -> str:
        """Return human-readable criterion tag label."""
        return obj.get_criterion_tag_display() or ""

    def get_replies(self, obj):
        """
        Recursively serialize child comments.

        Excludes soft-deleted comments to maintain clean thread view.
        """
        if obj.is_deleted:
            return []

        # Get non-deleted replies
        active_replies = obj.replies.filter(is_deleted=False).order_by("created_at")

        # Recursively serialize replies
        return ConflictCommentSerializer(
            active_replies, many=True, context=self.context
        ).data

    def get_discussion_vote(self, obj) -> dict | None:
        """Return vote data if this comment initiated a straw poll."""
        try:
            vote = obj.discussion_vote
        except InDiscussionVote.DoesNotExist:
            return None
        return InDiscussionVoteSerializer(vote, context=self.context).data


class ConflictCommentCreateSerializer(serializers.Serializer):
    """
    Write serializer for creating new conflict comments with validation.

    Validates content length and parent comment existence.
    """

    content = serializers.CharField(
        min_length=1,
        max_length=5000,
        required=True,
        trim_whitespace=True,
        help_text="Comment text (supports markdown, 1-5000 chars)",
    )
    parent_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Parent comment ID for threaded replies",
    )
    criterion_tag = serializers.ChoiceField(
        choices=ConflictComment.CRITERION_TAG_CHOICES,
        required=False,
        allow_blank=True,
    )

    def validate_content(self, value):
        """Validate content is not empty after stripping whitespace."""
        if not value or not value.strip():
            raise serializers.ValidationError("Comment content cannot be empty.")
        return value.strip()

    def validate_parent_id(self, value):
        """Validate parent comment exists and belongs to the same conflict."""
        if value is None:
            return None

        try:
            ConflictComment.objects.get(id=value)
        except ConflictComment.DoesNotExist:
            raise serializers.ValidationError("Parent comment does not exist.")

        # Additional validation: parent must belong to same conflict
        # This will be checked in the view using the conflict context
        return value

    def validate(self, attrs):
        """Cross-field validation."""
        # If parent_id provided, ensure it's from the same conflict
        # This requires conflict context from the view
        parent_id = attrs.get("parent_id")
        if parent_id and hasattr(self, "conflict"):
            try:
                parent_comment = ConflictComment.objects.get(id=parent_id)
                if parent_comment.conflict_id != self.conflict.id:
                    raise serializers.ValidationError(
                        {
                            "parent_id": "Parent comment must belong to the same conflict."
                        }
                    )
            except ConflictComment.DoesNotExist:
                raise serializers.ValidationError(
                    {"parent_id": "Parent comment does not exist."}
                )

        return attrs


class RevoteProposalSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for RevoteProposal with acceptance tracking.

    Includes computed fields for expiry status and human-readable display values.
    """

    proposed_by = SimpleUserSerializer(read_only=True)
    accepted_by = SimpleUserSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = RevoteProposal
        fields = [
            "id",
            "conflict",
            "proposed_by",
            "proposed_at",
            "rationale",
            "status",
            "status_display",
            "accepted_by",
            "accepted_at",
            "completed_at",
            "resulted_in_consensus",
            "expires_at",
            "is_expired",
        ]
        read_only_fields = fields

    def get_is_expired(self, obj):
        """Compute whether the proposal has expired."""
        return obj.is_expired()


class InDiscussionVoteResponseSerializer(serializers.ModelSerializer):
    """Serializer for individual straw poll responses."""

    reviewer = SimpleUserSerializer(read_only=True)

    class Meta:
        model = InDiscussionVoteResponse
        fields = [
            "id",
            "reviewer",
            "decision",
            "responded_at",
        ]
        read_only_fields = fields


class InDiscussionVoteSerializer(serializers.ModelSerializer):
    """Serializer for straw poll votes with nested responses."""

    proposed_by = SimpleUserSerializer(read_only=True)
    responses = InDiscussionVoteResponseSerializer(many=True, read_only=True)
    results_summary = serializers.SerializerMethodField()

    class Meta:
        model = InDiscussionVote
        fields = [
            "id",
            "conflict",
            "proposed_by",
            "rationale",
            "is_closed",
            "closed_at",
            "created_at",
            "responses",
            "results_summary",
        ]
        read_only_fields = fields

    def get_results_summary(self, obj: InDiscussionVote) -> dict:
        """Aggregate vote counts."""
        responses = obj.responses.all()
        return {
            "total": responses.count(),
            "include": responses.filter(decision="INCLUDE").count(),
            "exclude": responses.filter(decision="EXCLUDE").count(),
            "maybe": responses.filter(decision="MAYBE").count(),
        }


class ReviewerDecisionCreateSerializer(serializers.Serializer):
    """
    Write serializer for submitting re-vote decisions.

    Validates decision choices and enforces exclusion_reason requirement
    for EXCLUDE decisions.
    """

    decision = serializers.ChoiceField(
        choices=["INCLUDE", "EXCLUDE", "MAYBE"],
        required=True,
        help_text="Re-vote decision (INCLUDE/EXCLUDE/MAYBE)",
    )
    exclusion_reason = serializers.CharField(
        max_length=100,
        allow_blank=True,
        required=False,
        help_text="Required when decision is EXCLUDE",
    )
    notes = serializers.CharField(
        max_length=1000,
        allow_blank=True,
        required=False,
        help_text="Optional notes explaining the decision",
    )

    def validate(self, attrs):
        """
        Cross-field validation.

        Ensures exclusion_reason is provided for EXCLUDE decisions,
        and not provided for INCLUDE/MAYBE decisions.
        """
        decision = attrs.get("decision")
        exclusion_reason = attrs.get("exclusion_reason", "").strip()

        if decision == "EXCLUDE":
            if not exclusion_reason:
                raise serializers.ValidationError(
                    {
                        "exclusion_reason": "This field is required when decision is EXCLUDE."
                    }
                )
        else:
            # INCLUDE or MAYBE should not have exclusion_reason
            if exclusion_reason:
                raise serializers.ValidationError(
                    {
                        "exclusion_reason": "This field should only be set when decision is EXCLUDE."
                    }
                )

        return attrs


# ============================================================================
# MANUAL RESULT ADDITION (Issue #76)
# ============================================================================


class ManualResultInputSerializer(serializers.Serializer):
    """Input serializer for manually adding a result discovered during screening."""

    session_id = serializers.UUIDField()
    url = serializers.URLField(max_length=2048)
    title = serializers.CharField(max_length=500)
    justification = serializers.CharField(max_length=1000)
    snippet = serializers.CharField(max_length=2000, required=False, default="")
