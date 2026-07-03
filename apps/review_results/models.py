import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

from .managers import ConflictResolutionQuerySet


class SimpleReviewDecision(models.Model):
    """
    Simple Include/Exclude decision with optional notes.

    Denormalized Fields:
        session: Direct reference to SearchSession for performance.
                Duplicates result.session for faster queries.
                Must match result.session when creating.
    """

    DECISION_CHOICES = [
        ("pending", "Pending Review"),
        ("include", "Include"),
        ("exclude", "Exclude"),
        ("maybe", "Maybe/Uncertain"),
    ]

    EXCLUSION_REASONS = [
        ("not_relevant", "Not relevant to research question"),
        ("not_grey_lit", "Not grey literature"),
        ("duplicate", "Duplicate result"),
        ("no_access", "Full text unavailable"),
        ("wrong_document_type", "Inappropriate document type"),
        ("language", "Language other than English"),
        ("wrong_population", "Wrong population"),
        ("wrong_intervention", "Wrong intervention/interest"),
        ("methodological_quality", "Poor methodological quality"),
        ("not_guideline", "Not a guideline"),
        ("other", "Other reason"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    result = models.OneToOneField(
        "results_manager.ProcessedResult", on_delete=models.CASCADE
    )
    # Denormalized for performance - direct reference to session
    session = models.ForeignKey(
        "review_manager.SearchSession",
        on_delete=models.CASCADE,
        related_name="review_decisions_denorm",
        help_text="Denormalized session reference for performance",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )

    decision = models.CharField(
        max_length=20, choices=DECISION_CHOICES, default="pending"
    )
    exclusion_reason = models.CharField(
        max_length=25, choices=EXCLUSION_REASONS, blank=True
    )
    notes = models.TextField(blank=True, help_text=" reviewer notes")

    reviewed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "simple_review_decisions"
        ordering = ["-reviewed_at"]

    def __str__(self):
        """Return string representation of the review decision.

        Returns:
            str: Decision status and truncated result title.
        """
        return f"{self.get_decision_display()} - {self.result.title[:50]}..."

    def clean(self):
        """Validate exclusion reason is provided when excluding.

        Raises:
            ValidationError: If decision is 'exclude' but no exclusion_reason provided.
        """
        if self.decision == "exclude" and not self.exclusion_reason:
            raise ValidationError(
                "Exclusion reason is required when excluding a result"
            )

    def save(self, *args, **kwargs):
        """Update result review status.

        Args:
            *args: Variable positional arguments passed to parent save method.
            **kwargs: Variable keyword arguments passed to parent save method.
        """
        self.full_clean()
        super().save(*args, **kwargs)

        # Update the processed result's review status
        if self.result:
            self.result.is_reviewed = self.decision != "pending"
            self.result.save(update_fields=["is_reviewed"])


class URLAccessLog(models.Model):
    """
    Track when users click on result URLs for PRISMA reporting.

    Denormalized Fields:
        session: Direct reference to SearchSession for performance.
                Enables fast session-based access log queries.
                Must match result.session when creating.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    result = models.ForeignKey(
        "results_manager.ProcessedResult",
        on_delete=models.CASCADE,
        related_name="access_logs",
    )
    session = models.ForeignKey(
        "review_manager.SearchSession",
        on_delete=models.CASCADE,
        related_name="url_access_logs",
        help_text="Denormalized session reference for performance",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="user_url_access_logs",
    )

    accessed_at = models.DateTimeField(auto_now_add=True)
    access_successful = models.BooleanField(
        default=True, help_text="Whether the URL was successfully accessed"
    )
    failure_reason = models.CharField(
        max_length=100,
        blank=True,
        choices=[
            ("broken_link", "Broken Link"),
            ("access_denied", "Access Denied"),
            ("timeout", "Connection Timeout"),
            ("other", "Other"),
        ],
    )

    class Meta:
        db_table = "url_access_logs"
        ordering = ["-accessed_at"]
        indexes = [
            models.Index(fields=["result", "user"]),
            models.Index(fields=["session", "accessed_at"]),
            models.Index(fields=["access_successful"]),
        ]

    def __str__(self):
        """Return string representation of the URL access log.

        Returns:
            str: User, access status, and truncated result title.
        """
        status = "accessed" if self.access_successful else "failed"
        return f"{self.user} {status} {self.result.title[:50]}..."


# ============================================================================
# BROWSING VISIT MODEL (Phase 0 – browser-extension source capture)
# ============================================================================


class BrowsingVisit(models.Model):
    """
    Stream-1 grey-lit browsing record for the PRISMA other-methods arm.

    Every page load inside the dedicated capture window is a retrieved record.
    `client_capture_id` is assigned by the browser extension for idempotent
    ingestion; NULL until the extension backend is wired in Phase 1.
    """

    VISIT_SOURCE_CHOICES = [
        ("auto", "Auto-logged (capture window)"),
        ("one_click", "One-click add"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    session = models.ForeignKey(
        "review_manager.SearchSession",
        on_delete=models.CASCADE,
        related_name="browsing_visits",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="browsing_visits",
    )

    url = models.URLField(max_length=2048)
    canonical_url = models.URLField(max_length=2048, blank=True)
    title = models.CharField(max_length=512, blank=True)
    document_type = models.CharField(max_length=100, blank=True)
    site_name = models.CharField(max_length=255, blank=True)
    author = models.CharField(max_length=512, blank=True)
    published_date = models.DateField(null=True, blank=True)

    accessed_at = models.DateTimeField(auto_now_add=True)
    access_successful = models.BooleanField(default=True)

    visit_source = models.CharField(
        max_length=20,
        choices=VISIT_SOURCE_CHOICES,
        default="auto",
    )

    captured_incognito = models.BooleanField(
        default=False,
        help_text=(
            "True if captured in an incognito window (de-personalised search). "
            "False covers both 'normal window' and 'incognito unavailable' - the "
            "safe default is to assume searches were NOT de-personalised."
        ),
    )

    promoted_result = models.ForeignKey(
        "results_manager.ProcessedResult",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="browsing_visits",
        help_text="ProcessedResult created via Stream-2 one-click add from this visit",
    )

    client_capture_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        help_text="Opaque ID assigned by the browser extension for idempotent ingestion",
    )

    class Meta:
        db_table = "browsing_visits"
        ordering = ["-accessed_at"]
        indexes = [
            models.Index(fields=["session", "accessed_at"]),
            models.Index(
                fields=["session", "captured_incognito"],
                name="bv_session_incognito_idx",
            ),
        ]

    def __str__(self) -> str:
        label = self.title[:50] if self.title else self.url[:50]
        return f"{label} @ {self.accessed_at.strftime('%Y-%m-%d') if self.accessed_at else '?'}"


# ============================================================================
# DUAL SCREENING MODELS (Phase 2)
# ============================================================================


class ReviewerAssignment(models.Model):
    """
    Tracks which reviewers are assigned to which results.

    Implements atomic work queue with role-based assignments for dual screening.
    Supports PRIMARY/SECONDARY/ARBITRATOR roles for flexible review workflows.
    """

    ROLE_CHOICES = [
        ("PRIMARY", "Primary Reviewer"),
        ("SECONDARY", "Secondary Reviewer"),
        ("ARBITRATOR", "Conflict Arbitrator"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Organisation context (CRITICAL: PROTECT to prevent cascade deletion)
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.PROTECT,
        related_name="reviewer_assignments",
        help_text="Organisation managing this review",
    )

    # Core relationships
    result = models.ForeignKey(
        "results_manager.ProcessedResult",
        on_delete=models.CASCADE,
        related_name="reviewer_assignments",
        help_text="The result being reviewed",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_assignments",
        help_text="The reviewer assigned to this result",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments_made",
        help_text="User who made this assignment (null for auto-assignment)",
    )

    # Assignment details
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        help_text="Reviewer role for this assignment",
    )
    assigned_at = models.DateTimeField(
        auto_now_add=True, help_text="When the assignment was created"
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this assignment is currently active"
    )

    class Meta:
        db_table = "reviewer_assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["result", "reviewer"],
                name="unique_assignment_result_reviewer",
            ),
        ]
        indexes = [
            models.Index(fields=["organisation", "assigned_at"]),
            models.Index(fields=["result", "is_active"]),
            models.Index(fields=["reviewer", "is_active"]),
        ]
        ordering = ["-assigned_at"]

    def __str__(self):
        """Return string representation of the assignment."""
        return f"{self.reviewer.username} ({self.role}) → {self.result.title[:40]}..."


class ReviewerDecisionQuerySet(models.QuerySet):
    """Query helpers for ReviewerDecision."""

    def active(self):
        """Initial-screening decisions only (excludes conflict-resolution re-votes)."""
        return self.filter(is_revote=False)

    def active_for(self, result, reviewer):
        """Active (non-revote) decisions for a given result and reviewer."""
        return self.active().filter(result=result, reviewer=reviewer)


class ReviewerDecision(models.Model):
    """
    Individual reviewer decisions - immutable audit trail.

    CRITICAL: Once created, decisions cannot be modified (audit trail integrity).
    Use version field for optimistic locking. Create new record to change decision.
    """

    DECISION_CHOICES = [
        ("INCLUDE", "Include"),
        ("EXCLUDE", "Exclude"),
        ("MAYBE", "Maybe - needs full report review"),
        ("ABSTAIN", "Abstain"),
    ]

    CONFIDENCE_CHOICES = [
        (1, "Low"),
        (2, "Medium"),
        (3, "High"),
    ]

    SCREENING_STAGE_CHOICES = [
        ("SCREENING", "Grey Literature Screening"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Organisation context (CRITICAL: PROTECT to prevent cascade deletion)
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.PROTECT,
        related_name="reviewer_decisions",
        help_text="Organisation managing this review",
    )

    # Core relationships
    result = models.ForeignKey(
        "results_manager.ProcessedResult",
        on_delete=models.CASCADE,
        related_name="reviewer_decisions",
        help_text="The result being reviewed",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="review_decisions",
        help_text="The reviewer who made this decision",
    )
    assignment = models.ForeignKey(
        ReviewerAssignment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="decisions",
        help_text="The assignment this decision was made under",
    )

    # Decision details
    decision = models.CharField(
        max_length=20, choices=DECISION_CHOICES, help_text="The reviewer's decision"
    )
    exclusion_reason = models.CharField(
        max_length=100,
        blank=True,
        help_text="Reason for exclusion (if decision is EXCLUDE)",
    )
    confidence_level = models.IntegerField(
        choices=CONFIDENCE_CHOICES,
        default=2,
        help_text="Reviewer's confidence in their decision",
    )
    notes = models.TextField(
        blank=True, help_text="Reviewer's notes about this decision"
    )

    # Temporal tracking
    decided_at = models.DateTimeField(
        auto_now_add=True, help_text="When the decision was made"
    )
    time_spent_seconds = models.IntegerField(
        null=True, blank=True, help_text="Time spent reviewing this result (seconds)"
    )

    # Report access tracking (for PRISMA reporting)
    report_accessed = models.BooleanField(
        default=False, help_text="Whether the reviewer accessed the full report"
    )
    report_accessed_at = models.DateTimeField(
        null=True, blank=True, help_text="When the full report was accessed"
    )

    # Stage tracking
    screening_stage = models.CharField(
        max_length=20,
        default="SCREENING",
        choices=SCREENING_STAGE_CHOICES,
        help_text="Single-stage screening for grey literature (no abstract)",
    )

    # Metadata
    is_blinded = models.BooleanField(
        default=True,
        help_text="Whether this decision was made blind to other reviewers",
    )
    version = models.IntegerField(
        default=1, help_text="Version number for optimistic locking"
    )

    # Re-vote tracking (Phase 3: Consensus Discussion)
    is_revote = models.BooleanField(
        default=False,
        help_text="Whether this is a re-vote decision (part of conflict resolution)",
    )
    revote_proposal = models.ForeignKey(
        "RevoteProposal",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="revote_decisions",
        help_text="The re-vote proposal this decision is part of (if is_revote=True)",
    )

    objects = ReviewerDecisionQuerySet.as_manager()

    class Meta:
        db_table = "reviewer_decisions"
        permissions = [
            ("view_reviewer_decision", "Can view reviewer decisions"),
        ]
        indexes = [
            models.Index(fields=["organisation", "decided_at"]),
            models.Index(fields=["result", "screening_stage"]),
            models.Index(fields=["reviewer", "decided_at"]),
            models.Index(fields=["result", "decided_at"]),
            models.Index(
                fields=["revote_proposal", "is_revote"]
            ),  # For re-vote queries
        ]
        # Prevent duplicate decisions per reviewer per stage (allows one initial + one re-vote per stage)
        constraints = [
            models.UniqueConstraint(
                fields=["result", "reviewer", "screening_stage", "is_revote"],
                name="unique_reviewer_decision_per_stage_and_type",
            )
        ]
        ordering = ["-decided_at"]

    def __str__(self):
        """Return string representation of the decision."""
        return (
            f"{self.reviewer.username}: {self.decision} - {self.result.title[:40]}..."
        )

    def save(self, *args, **kwargs):
        """
        Override save to enforce immutability.

        CRITICAL: Once created, decisions cannot be modified to maintain audit trail.
        Use allow_update=True in kwargs to bypass (e.g., for version increment).

        Raises:
            ValueError: If attempting to update an existing decision without allow_update=True
        """
        # Use _state.adding to check if this is a new object (not self.pk, which exists with UUID defaults)
        is_new = self._state.adding

        if not is_new and not kwargs.pop("allow_update", False):
            raise ValueError(
                "ReviewerDecision is immutable. Create a new record instead of updating."
            )

        # Increment version on update (only allowed with allow_update=True)
        if not is_new:
            self.version += 1

        super().save(*args, **kwargs)


class ConflictResolution(models.Model):
    """
    Tracks conflicts and their resolution.

    Automatically detects conflicts when reviewers disagree and tracks
    resolution workflow from detection through to final decision.
    """

    CONFLICT_TYPE_CHOICES = [
        ("INCLUDE_EXCLUDE", "Include vs Exclude"),
        ("EXCLUSION_REASON", "Different exclusion reasons"),
        ("LOW_CONFIDENCE", "Low confidence decisions"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_IN_DISCUSSION = "IN_DISCUSSION"
    STATUS_ESCALATED = "ESCALATED"
    STATUS_RESOLVED = "RESOLVED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Awaiting Resolution"),
        (STATUS_IN_DISCUSSION, "Reviewers Discussing"),
        (STATUS_ESCALATED, "Escalated to Arbitrator"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    RESOLUTION_METHOD_CHOICES = [
        ("CONSENSUS", "Reviewer Consensus"),
        ("ARBITRATION", "Third Party Arbitration"),
        ("MAJORITY", "Majority Vote"),
        ("SENIOR_OVERRIDE", "Senior Reviewer Override"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Organisation context (CRITICAL: PROTECT to prevent cascade deletion)
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.PROTECT,
        related_name="conflict_resolutions",
        help_text="Organisation managing this review",
    )

    # Core relationships
    result = models.ForeignKey(
        "results_manager.ProcessedResult",
        on_delete=models.CASCADE,
        related_name="conflicts",
        help_text="The result with conflicting decisions",
    )
    conflicting_decisions = models.ManyToManyField(
        ReviewerDecision,
        related_name="conflicts",
        help_text="The decisions that are in conflict",
    )

    # Conflict details
    conflict_type = models.CharField(
        max_length=30,
        choices=CONFLICT_TYPE_CHOICES,
        help_text="Type of conflict detected",
    )
    detected_at = models.DateTimeField(
        auto_now_add=True, help_text="When the conflict was detected"
    )

    # Resolution details
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        help_text="Current status of conflict resolution",
    )
    resolution_method = models.CharField(
        max_length=30,
        choices=RESOLUTION_METHOD_CHOICES,
        null=True,
        blank=True,
        help_text="How the conflict was resolved",
    )
    final_decision = models.ForeignKey(
        ReviewerDecision,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_conflicts",
        help_text="The final decision after resolution",
    )
    resolved_at = models.DateTimeField(
        null=True, blank=True, help_text="When the conflict was resolved"
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conflicts_resolved",
        help_text="User who resolved the conflict",
    )
    resolution_notes = models.TextField(
        blank=True, help_text="Notes about the resolution process"
    )
    sla_reminders_sent = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Tracks which SLA reminder thresholds have been sent, "
            "e.g. {'50': '2026-02-27T10:00:00Z', '90': '2026-02-27T18:00:00Z'}"
        ),
    )

    objects = ConflictResolutionQuerySet.as_manager()

    class Meta:
        db_table = "conflict_resolutions"
        indexes = [
            models.Index(fields=["organisation", "detected_at"]),
            models.Index(fields=["result", "status"]),
            models.Index(fields=["status", "detected_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["result"],
                condition=models.Q(
                    status__in=["PENDING", "IN_DISCUSSION", "ESCALATED"]
                ),
                name="unique_active_conflict_per_result",
            ),
        ]
        ordering = ["-detected_at"]

    def __str__(self):
        """Return string representation of the conflict."""
        return f"{self.conflict_type} - {self.result.title[:40]}... ({self.status})"

    def get_discussion_summary(self):
        """
        Get summary of discussion activity.

        Returns:
            dict: Summary containing comment count, participant count,
                  revote count, and last activity timestamp.
        """
        comments = self.comments.filter(is_deleted=False)
        last_comment = comments.order_by("-created_at").first()

        return {
            "comment_count": comments.count(),
            "participant_count": comments.values("author").distinct().count(),
            "revote_count": self.revote_proposals.count(),
            "last_activity": last_comment.created_at if last_comment else None,
        }

    def has_active_revote_proposal(self):
        """
        Check if there's an active re-vote proposal.

        Returns:
            bool: True if there's an active proposal (PROPOSED/ACCEPTED/IN_PROGRESS).
        """
        return self.revote_proposals.filter(
            status__in=["PROPOSED", "ACCEPTED", "IN_PROGRESS"]
        ).exists()

    def can_propose_revote(self, user):
        """
        Check if user can propose a re-vote.

        Args:
            user: The user attempting to propose a re-vote.

        Returns:
            bool: True if user is authorized to propose a re-vote.
        """
        # User must be one of the conflicting reviewers
        reviewer_ids = self.conflicting_decisions.values_list("reviewer_id", flat=True)
        is_conflicting_reviewer = user.id in reviewer_ids

        # No active re-vote proposals
        no_active_proposal = not self.has_active_revote_proposal()

        # Conflict not yet resolved
        not_resolved = self.status != self.STATUS_RESOLVED

        return is_conflicting_reviewer and no_active_proposal and not_resolved

    def get_active_revote_proposal(self):
        """
        Get the currently active re-vote proposal, if any.

        Returns:
            RevoteProposal or None: The active proposal, or None if none exists.
        """
        return self.revote_proposals.filter(
            status__in=["PROPOSED", "ACCEPTED", "IN_PROGRESS"]
        ).first()

    def get_sla_info(self) -> dict | None:
        """Compute SLA deadline info based on current status and session config."""
        if self.status == self.STATUS_RESOLVED:
            return None

        config = self.result.session.current_configuration
        if not config or not config.is_workflow_2:
            return None

        # Determine which SLA applies
        if self.has_active_revote_proposal():
            sla_hours = config.revote_sla_hours
        elif self.status == self.STATUS_ESCALATED:
            sla_hours = config.arbitration_sla_hours
        else:  # PENDING or IN_DISCUSSION
            sla_hours = config.discussion_sla_hours

        deadline = self.detected_at + timedelta(hours=sla_hours)
        elapsed = (timezone.now() - self.detected_at).total_seconds() / 3600
        percent_elapsed = min((elapsed / sla_hours) * 100, 999) if sla_hours > 0 else 0

        return {
            "deadline": deadline,
            "hours_remaining": max(0, sla_hours - elapsed),
            "hours_overdue": max(0, elapsed - sla_hours),
            "percent_elapsed": round(percent_elapsed, 1),
            "is_approaching": percent_elapsed >= 50,
            "is_critical": percent_elapsed >= 90,
            "is_overdue": percent_elapsed > 100,
            "sla_hours": sla_hours,
        }


class ConflictComment(TimeStampedModel):
    """
    Discussion comments for conflict resolution.

    Supports threaded discussions with parent/child relationships.
    Enables reviewers to discuss conflicts and document consensus process.
    """

    CRITERION_TAG_CHOICES = [
        ("relevance", "Relevance to research question"),
        ("grey_lit_classification", "Grey literature classification"),
        ("document_type", "Document type appropriateness"),
        ("population", "Population match"),
        ("intervention_interest", "Intervention/interest match"),
        ("context", "Context appropriateness"),
        ("full_text_availability", "Full text availability"),
        ("language", "Language eligibility"),
        ("other", "Other criterion"),
    ]

    conflict = models.ForeignKey(
        "ConflictResolution",
        on_delete=models.CASCADE,
        related_name="comments",
        help_text="The conflict being discussed",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="conflict_comments",
        help_text="Author of the comment (null if user deleted)",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        help_text="Parent comment for threaded discussions",
    )

    # Content
    content = models.TextField(help_text="Comment text (supports markdown)")
    content_html = models.TextField(
        blank=True, help_text="Rendered HTML from markdown (cached)"
    )

    # Metadata
    is_edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    # Flags
    is_deleted = models.BooleanField(
        default=False, help_text="Soft delete for audit trail"
    )
    is_system_message = models.BooleanField(
        default=False, help_text="System-generated messages (e.g., 'Re-vote proposed')"
    )

    # Optional criterion tag to anchor discussion to a specific screening criterion
    criterion_tag = models.CharField(
        max_length=30, blank=True, choices=CRITERION_TAG_CHOICES
    )

    class Meta:
        db_table = "conflict_comments"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conflict", "created_at"]),
            models.Index(fields=["conflict", "parent"]),
        ]

    def __str__(self):
        """Return string representation of the comment."""
        author_name = self.author.username if self.author else "Unknown"
        return f"Comment by {author_name} on conflict {self.conflict_id}"

    def save(self, *args, **kwargs):
        """Render markdown to HTML on save."""
        import markdown

        self.content_html = markdown.markdown(
            self.content, extensions=["nl2br", "fenced_code"]
        )
        super().save(*args, **kwargs)


class RevoteProposal(models.Model):
    """
    Proposals for re-voting on conflicting results.

    Tracks proposal, acceptance, and completion of re-votes.
    Enables structured workflow for resolving conflicts through re-voting.
    """

    STATUS_CHOICES = [
        ("PROPOSED", "Proposed"),
        ("ACCEPTED", "Accepted"),
        ("IN_PROGRESS", "In Progress"),
        ("COMPLETED", "Completed"),
        ("EXPIRED", "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conflict = models.ForeignKey(
        "ConflictResolution",
        on_delete=models.CASCADE,
        related_name="revote_proposals",
        help_text="The conflict this re-vote proposal addresses",
    )

    # Proposal details
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="revote_proposals_created",
        help_text="Reviewer who proposed the re-vote",
    )
    proposed_at = models.DateTimeField(auto_now_add=True)
    rationale = models.TextField(help_text="Reason for proposing re-vote")

    # Acceptance tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PROPOSED",
        help_text="Current status of the proposal",
    )
    accepted_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="revote_proposals_accepted",
        blank=True,
        help_text="Reviewers who accepted this proposal",
    )
    accepted_at = models.DateTimeField(
        null=True, blank=True, help_text="When all required reviewers accepted"
    )

    # Completion tracking
    completed_at = models.DateTimeField(
        null=True, blank=True, help_text="When the re-vote was completed"
    )
    resulted_in_consensus = models.BooleanField(
        default=False, help_text="Whether re-vote achieved consensus"
    )

    # Expiry
    expires_at = models.DateTimeField(
        help_text="Auto-expire if not accepted by this time"
    )

    class Meta:
        db_table = "revote_proposals"
        ordering = ["-proposed_at"]
        indexes = [
            models.Index(fields=["conflict", "status"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        """Return string representation of the proposal."""
        return f"Re-vote proposal for conflict {self.conflict_id} ({self.status})"

    def is_expired(self):
        """Check if proposal has expired."""
        return timezone.now() > self.expires_at and self.status == "PROPOSED"

    def can_accept(self, user):
        """Check if user can accept this proposal."""
        # User must be one of the conflicting reviewers
        reviewer_ids = self.conflict.conflicting_decisions.values_list(
            "reviewer_id", flat=True
        )
        return (
            user.id in reviewer_ids
            and self.status == "PROPOSED"
            and not self.is_expired()
        )

    def all_accepted(self):
        """Check if all required reviewers have accepted."""
        required_reviewer_ids = set(
            self.conflict.conflicting_decisions.values_list("reviewer_id", flat=True)
        )
        accepted_reviewer_ids = set(self.accepted_by.values_list("id", flat=True))
        return required_reviewer_ids.issubset(accepted_reviewer_ids)


class InterRaterReliability(models.Model):
    """
    Calculated inter-rater reliability metrics.

    Stores Cohen's Kappa and percentage agreement for reviewer pairs.
    Used to track review quality and meet PRISMA reporting requirements.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Organisation context (CRITICAL: PROTECT to prevent cascade deletion)
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.PROTECT,
        related_name="irr_metrics",
        help_text="Organisation managing this review",
    )

    # Core relationships
    search_session = models.ForeignKey(
        "review_manager.SearchSession",
        on_delete=models.CASCADE,
        related_name="irr_metrics",
        help_text="The search session these metrics were calculated for",
    )

    # Reviewer pair (null if Fleiss' kappa for 3+ reviewers)
    reviewer_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="irr_as_a",
        help_text="First reviewer in the pair (null for Fleiss' kappa)",
    )
    reviewer_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="irr_as_b",
        help_text="Second reviewer in the pair (null for Fleiss' kappa)",
    )

    # Metrics
    cohens_kappa = models.FloatField(
        null=True,
        blank=True,
        help_text="Cohen's Kappa score (-1 to 1, ≥0.70 for Cochrane compliance)",
    )
    percentage_agreement = models.FloatField(
        help_text="Percentage agreement (0 to 100)"
    )
    total_comparisons = models.IntegerField(
        help_text="Total number of results both reviewers assessed"
    )
    agreements = models.IntegerField(
        help_text="Number of results where reviewers agreed"
    )
    disagreements = models.IntegerField(
        help_text="Number of results where reviewers disagreed"
    )

    # Context
    screening_stage = models.CharField(
        max_length=20, help_text="Screening stage these metrics apply to"
    )
    calculated_at = models.DateTimeField(
        auto_now_add=True, help_text="When these metrics were calculated"
    )
    calculation_window_start = models.DateTimeField(
        help_text="Start of time window for metric calculation"
    )
    calculation_window_end = models.DateTimeField(
        help_text="End of time window for metric calculation"
    )

    class Meta:
        db_table = "inter_rater_reliability"
        indexes = [
            models.Index(fields=["organisation", "calculated_at"]),
            models.Index(fields=["search_session", "calculated_at"]),
            models.Index(fields=["reviewer_a", "reviewer_b"]),
        ]
        ordering = ["-calculated_at"]

    def __str__(self):
        """Return string representation of the IRR metrics."""
        if self.reviewer_a and self.reviewer_b:
            return (
                f"IRR: {self.reviewer_a.username} & {self.reviewer_b.username} "
                f"- Kappa: {self.cohens_kappa:.3f}"
            )
        return f"IRR: Session {self.search_session_id} - Kappa: {self.cohens_kappa:.3f}"


class ReviewSession(models.Model):
    """
    Track reviewer activity sessions for presence and workload metrics.

    Used to detect concurrent reviewers and calculate workload distribution.
    Supports real-time presence tracking via last_activity_at updates.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Organisation context (CRITICAL: PROTECT to prevent cascade deletion)
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.PROTECT,
        related_name="review_sessions",
        help_text="Organisation managing this review",
    )

    # Core relationships
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_sessions",
        help_text="The reviewer for this session",
    )

    # Session details
    started_at = models.DateTimeField(
        auto_now_add=True, help_text="When the review session started"
    )
    last_activity_at = models.DateTimeField(
        auto_now=True, help_text="When the reviewer last made any action (auto-updated)"
    )
    ended_at = models.DateTimeField(
        null=True, blank=True, help_text="When the review session ended"
    )
    decisions_made = models.IntegerField(
        default=0, help_text="Number of decisions made in this session"
    )

    class Meta:
        db_table = "review_sessions"
        indexes = [
            models.Index(fields=["organisation", "started_at"]),
            models.Index(fields=["reviewer", "started_at"]),
            models.Index(fields=["last_activity_at"]),
        ]
        ordering = ["-started_at"]

    def __str__(self):
        """Return string representation of the review session."""
        return (
            f"{self.reviewer.username} - {self.started_at.strftime('%Y-%m-%d %H:%M')}"
        )


class ResultSkip(models.Model):
    """
    Tracks when reviewers skip results.

    Important for understanding workload distribution and result accessibility.
    Prevents reviewers from being repeatedly assigned results they've skipped.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Organisation context (CRITICAL: PROTECT to prevent cascade deletion)
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.PROTECT,
        related_name="result_skips",
        help_text="Organisation managing this review",
    )

    # Core relationships
    result = models.ForeignKey(
        "results_manager.ProcessedResult",
        on_delete=models.CASCADE,
        related_name="skips",
        help_text="The result that was skipped",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="result_skips",
        help_text="The reviewer who skipped this result",
    )

    # Skip details
    reason = models.TextField(blank=True, help_text="Optional reason for skipping")
    skipped_at = models.DateTimeField(
        auto_now_add=True, help_text="When the result was skipped"
    )

    class Meta:
        db_table = "result_skips"
        constraints = [
            models.UniqueConstraint(
                fields=["result", "reviewer"],
                name="unique_skip_result_reviewer",
            ),
        ]
        indexes = [
            models.Index(fields=["organisation", "skipped_at"]),
            models.Index(fields=["result", "reviewer"]),
            models.Index(fields=["reviewer", "skipped_at"]),
        ]
        ordering = ["-skipped_at"]

    def __str__(self):
        """Return string representation of the skip."""
        return f"{self.reviewer.username} skipped {self.result.title[:40]}..."


class ReviewerCompletion(TimeStampedModel):
    """
    Track invited reviewer completion status for dual-screening workflow.

    Created automatically when ReviewInvitation is accepted (Phase 2).
    Updated via signal when SimpleReviewDecision is saved (Phase 2).
    Queried before allowing "Complete Review" button click (Phase 2).

    Pattern: Follows SimpleReviewDecision (lightweight tracking model).
    """

    # 1:1 with ReviewInvitation
    invitation = models.OneToOneField(
        "review_manager.ReviewInvitation",
        on_delete=models.CASCADE,
        related_name="completion_status",
        null=True,
        blank=True,
        help_text="The invitation that led to this completion tracking. Null for session owners.",
    )

    # Denormalized FKs for performance (match SimpleReviewDecision pattern lines 42-50)
    session = models.ForeignKey(
        "review_manager.SearchSession",
        on_delete=models.CASCADE,
        related_name="reviewer_completions",
        help_text="Denormalized session reference for performance",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_completions",
        help_text="Denormalized reviewer reference for performance",
    )

    # Progress tracking
    total_results = models.IntegerField(
        default=0, help_text="Total results in session when review started"
    )
    reviewed_results = models.IntegerField(
        default=0, help_text="Number of results reviewed by this reviewer"
    )

    # Completion tracking
    completed_at = models.DateTimeField(
        null=True, blank=True, help_text="When reviewer marked their review as complete"
    )

    class Meta:
        db_table = "reviewer_completions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "reviewer"]),
            models.Index(fields=["completed_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "reviewer"],
                name="unique_session_reviewer_completion",
            ),
        ]

    def __str__(self):
        """Return string representation of the completion status."""
        status = (
            "complete"
            if self.completed_at
            else f"{self.reviewed_results}/{self.total_results}"
        )
        return f"{self.reviewer.username} → {self.session.title} ({status})"

    @property
    def is_complete(self):
        """Check if reviewer has marked review as complete."""
        return self.completed_at is not None

    @property
    def progress_percentage(self):
        """Calculate progress as percentage."""
        if self.total_results == 0:
            return 0
        return round((self.reviewed_results / self.total_results) * 100, 1)

    @property
    def is_owner_record(self):
        """Check if this completion record is for the session owner (no invitation)."""
        return self.invitation is None


class ConflictAccessLog(models.Model):
    """
    Audit log for early conflict access during review phase.

    Tracks when session owners view conflicts before all reviewers complete.
    Provides compliance audit trail for PRISMA reporting.
    """

    ACCESS_TYPE_CHOICES = [
        ("LIST_VIEW", "Viewed conflict list"),
        ("DETAIL_VIEW", "Viewed conflict detail"),
        ("ARBITRATION", "Arbitrator full access"),
    ]

    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Organisation context (multi-tenancy)
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        related_name="conflict_access_logs",
        help_text="Organisation managing this review",
    )

    # Conflict reference
    conflict = models.ForeignKey(
        "ConflictResolution",
        on_delete=models.CASCADE,
        related_name="access_logs",
        help_text="The conflict that was accessed",
    )

    # User who accessed
    accessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conflict_accesses",
        help_text="User who accessed the conflict",
    )

    # Access metadata
    accessed_at = models.DateTimeField(
        auto_now_add=True, help_text="When the conflict was accessed"
    )

    access_type = models.CharField(
        max_length=20, choices=ACCESS_TYPE_CHOICES, help_text="Type of conflict access"
    )

    is_session_owner = models.BooleanField(
        default=False, help_text="True if accessor is session owner (early access)"
    )

    class Meta:
        db_table = "conflict_access_logs"
        ordering = ["-accessed_at"]
        indexes = [
            models.Index(fields=["conflict", "accessed_by"], name="idx_conflict_user"),
            models.Index(fields=["organisation", "accessed_at"], name="idx_org_time"),
            models.Index(fields=["is_session_owner"], name="idx_session_owner"),
        ]
        verbose_name = "Conflict Access Log"
        verbose_name_plural = "Conflict Access Logs"

    def __str__(self):
        """Return string representation of the access log."""
        owner_flag = " (session owner)" if self.is_session_owner else ""
        return f"{self.accessed_by.username} → {self.get_access_type_display()}{owner_flag} @ {self.accessed_at.strftime('%Y-%m-%d %H:%M')}"


class InDiscussionVote(TimeStampedModel):
    """
    Straw poll initiated during conflict discussion.

    Allows reviewers to gauge alignment before formal resolution.
    Linked to a ConflictComment that serves as the initiating message.
    """

    conflict = models.ForeignKey(
        "ConflictResolution",
        on_delete=models.CASCADE,
        related_name="discussion_votes",
        help_text="The conflict this vote belongs to",
    )
    initiating_comment = models.OneToOneField(
        "ConflictComment",
        on_delete=models.CASCADE,
        related_name="discussion_vote",
        help_text="The system comment that initiated this vote",
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="proposed_discussion_votes",
        help_text="The reviewer who proposed this straw poll",
    )
    rationale = models.TextField(
        help_text="Why this straw poll was proposed",
    )
    is_closed = models.BooleanField(
        default=False,
        help_text="Whether this vote is closed",
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the vote was closed",
    )

    class Meta:
        db_table = "in_discussion_votes"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return string representation of the discussion vote."""
        return (
            f"Straw poll by {self.proposed_by.username} on conflict {self.conflict_id}"
        )


class InDiscussionVoteResponse(models.Model):
    """
    Individual response to an in-discussion straw poll.

    Each reviewer can respond once per vote.
    """

    DECISION_CHOICES = [
        ("INCLUDE", "Include"),
        ("EXCLUDE", "Exclude"),
        ("MAYBE", "Maybe"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vote = models.ForeignKey(
        "InDiscussionVote",
        on_delete=models.CASCADE,
        related_name="responses",
        help_text="The straw poll being responded to",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="discussion_vote_responses",
        help_text="The reviewer responding",
    )
    decision = models.CharField(
        max_length=10,
        choices=DECISION_CHOICES,
        help_text="The reviewer's straw poll response",
    )
    responded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the response was submitted",
    )

    class Meta:
        db_table = "in_discussion_vote_responses"
        unique_together = [("vote", "reviewer")]
        ordering = ["responded_at"]

    def __str__(self) -> str:
        """Return string representation of the vote response."""
        return f"{self.reviewer.username} voted {self.decision} on vote {self.vote_id}"
