import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import AbstractInvitation, TimeStampedModel

from .managers import SearchSessionManager

# Prometheus metrics integration (Phase 3)
try:
    from apps.core.metrics.session_metrics import (
        calculate_state_duration,
        record_session_transition,
    )

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


class SearchSession(TimeStampedModel):
    """
    Core model representing a grey literature search session.
    Implements a 9-state workflow for systematic literature review.
    """

    # Status choices representing the 9-state workflow
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("defining_search", "Defining Search"),
        ("ready_to_execute", "Ready to Execute"),
        ("executing", "Executing"),
        ("processing_results", "Processing Results"),
        ("ready_for_review", "Ready for Review"),
        ("under_review", "Under Review"),
        ("completed", "Completed"),
        ("archived", "Archived"),
    ]

    # Allowed status transitions
    ALLOWED_TRANSITIONS = {
        "draft": ["defining_search", "archived"],
        "defining_search": ["ready_to_execute", "draft", "archived"],
        "ready_to_execute": ["executing", "defining_search", "archived"],
        "executing": [
            "processing_results",
            "ready_to_execute",
            "defining_search",
            "archived",
        ],
        "processing_results": [
            "ready_for_review",
            "executing",
            "defining_search",
            "completed",
            "archived",
        ],
        "ready_for_review": [
            "under_review",
            "processing_results",
            "defining_search",
            "archived",
        ],
        "under_review": [
            "completed",
            "ready_for_review",
            "defining_search",
            "archived",
        ],
        "completed": ["archived", "under_review"],
        "archived": ["draft"],  # Can only unarchive to draft
    }

    # Core fields
    title = models.CharField(max_length=255, help_text="Title of the search session")
    description = models.TextField(
        blank=True, help_text="Detailed description of the search objectives"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        help_text="Current status in the 9-state workflow",
    )
    status_detail = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Detailed status message for ultra-simple architecture",
    )

    # User relationship
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="search_sessions",
        help_text="User who created this search session",
    )

    # Organisation relationship (multi-tenancy)
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.PROTECT,  # Prevent deletion if reviews exist
        related_name="reviews",
        null=True,  # Allow null during migration
        blank=True,
        help_text="Organisation managing this review",
    )

    # Dual-screening configuration (Phase 5)
    current_configuration = models.ForeignKey(
        "ReviewConfiguration",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="active_sessions",
        help_text="Current active configuration for this review session",
    )

    # Timestamps
    started_at = models.DateTimeField(
        null=True, blank=True, help_text="When search execution started"
    )
    completed_at = models.DateTimeField(
        null=True, blank=True, help_text="When search was completed"
    )

    # Metadata
    notes = models.TextField(
        blank=True, help_text="Internal notes about the search session"
    )

    # Search statistics
    total_queries = models.IntegerField(
        default=0, help_text="Total number of search queries"
    )
    total_results = models.IntegerField(
        default=0, help_text="Total number of results found"
    )
    reviewed_results = models.IntegerField(
        default=0, help_text="Number of results reviewed"
    )
    included_results = models.IntegerField(
        default=0, help_text="Number of results included in final selection"
    )

    # PRISMA 2020 "other methods" data for the two-column flow diagram
    prisma_other_methods = models.JSONField(
        default=dict,
        blank=True,
        help_text="User-overridable data for PRISMA 'other methods' column",
    )

    # Custom manager for optimized queries
    objects = SearchSessionManager()

    class Meta:
        db_table = "search_sessions"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status", "-updated_at"]),  # For monitoring queries
            models.Index(fields=["owner", "status"]),  # For user dashboards
            models.Index(fields=["status"]),  # For status filtering
            models.Index(
                fields=["owner", "-updated_at"]
            ),  # For user session list (prioritise updated_at)
            models.Index(fields=["created_at"]),  # For time-based queries
            models.Index(fields=["updated_at"]),  # For recent activity
            models.Index(fields=["organisation", "status"]),  # For org-level filtering
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def clean(self):
        """Validate status transitions."""
        if self.pk:  # Only validate on updates
            try:
                old_instance = SearchSession.objects.get(pk=self.pk)
                old_status = old_instance.status
                if old_status != self.status:
                    if not self.can_transition_to(self.status):
                        raise ValidationError(
                            f"Cannot transition from '{old_status}' to '{self.status}'"
                        )
            except SearchSession.DoesNotExist:
                pass

    def save(self, *args, **kwargs):
        """Override save to handle status change timestamps and metrics."""
        self.full_clean()

        # Track status changes for signal handlers and metrics
        old_status = None
        if self.pk:
            try:
                old_instance = SearchSession.objects.get(pk=self.pk)
                if old_instance.status != self.status:
                    self._status_changed = True
                    old_status = old_instance.status
                else:
                    self._status_changed = False
            except SearchSession.DoesNotExist:
                self._status_changed = False
        else:
            self._status_changed = False

        # Set started_at when moving to executing
        if self.status == "executing" and not self.started_at:
            self.started_at = timezone.now()

        # Set completed_at when moving to completed
        if self.status == "completed" and not self.completed_at:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

        # Record state transition metrics (Phase 3)
        if METRICS_AVAILABLE and old_status and old_status != self.status:
            duration = calculate_state_duration(self, old_status)
            record_session_transition(
                session=self,
                from_state=old_status,
                to_state=self.status,
                success=True,
                duration_seconds=duration,
            )

    def can_transition_to(self, new_status):
        """Check if transition to new status is allowed."""
        if self.status == new_status:
            return True
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, [])

    def get_allowed_transitions(self):
        """Get list of allowed status transitions from current status."""
        return self.ALLOWED_TRANSITIONS.get(self.status, [])

    @property
    def progress_percentage(self):
        """Calculate review progress as a percentage."""
        if self.total_results == 0:
            return 0
        result = round((self.reviewed_results / self.total_results) * 100, 1)
        return int(result) if result == int(result) else result

    @property
    def inclusion_rate(self):
        """Calculate the rate of included results."""
        if self.reviewed_results == 0:
            return 0
        result = round((self.included_results / self.reviewed_results) * 100, 1)
        return int(result) if result == int(result) else result

    @property
    def is_active(self):
        """Check if session is in an active state."""
        return self.status not in ["completed", "archived"]

    @property
    def can_edit(self):
        """Check if session details can be edited."""
        return self.status in ["draft", "defining_search"]

    @property
    def can_delete(self):
        """Check if session can be deleted."""
        return self.status == "draft"

    @property
    def is_executing_or_processing(self):
        """
        Check if session is in executing or processing_results state.

        Provides cleaner template syntax for checking these related states.
        Used by session_detail.html for conditional rendering of execution monitor.

        Returns:
            bool: True if status is 'executing' or 'processing_results'
        """
        return self.status in ["executing", "processing_results"]

    @property
    def is_reviewable(self):
        """
        Check if session is in a reviewable state.

        Used by API views to validate that reviews can be claimed/submitted.

        Returns:
            bool: True if status allows reviews to be claimed
        """
        return self.status in ["ready_for_review", "under_review"]

    def validate_state_for_review(self):
        """
        Validate that session is in correct state for review operations.

        Raises:
            ValueError: If session is not in reviewable state

        Returns:
            bool: True if state is valid for reviews
        """
        if not self.is_reviewable:
            raise ValueError(
                f"Session must be in ready_for_review or under_review state. "
                f"Current state: {self.status}"
            )
        return True

    def set_status(self, new_status: str, detail: str = "") -> bool:
        """
        Set session status with optional detail message.

        Args:
            new_status: The new status to set
            detail: Optional status detail message

        Returns:
            bool: True if status was successfully set
        """
        try:
            # Validate transition
            if not self.can_transition_to(new_status):
                return False

            # Update status and detail
            self.status = new_status
            if detail:
                self.status_detail = detail

            # Handle timestamp updates
            if new_status == "executing" and not self.started_at:
                self.started_at = timezone.now()
            elif new_status == "completed" and not self.completed_at:
                self.completed_at = timezone.now()

            self.save(
                update_fields=["status", "status_detail", "started_at", "completed_at"]
            )
            return True

        except Exception:
            return False

    def update_status_detail(self, message: str) -> None:
        """
        Update the status detail message without changing the status.

        Args:
            message: The status detail message to set
        """
        try:
            self.status_detail = message
            self.save(update_fields=["status_detail"])
        except Exception:
            pass  # Silent fail for status updates


class ReviewInvitation(AbstractInvitation):
    """
    Track email invitations to join review sessions for dual screening.

    Inherits token generation, expiry, status tracking, and magic link
    generation from AbstractInvitation. Extends with DECLINED status
    and fallback URL construction.

    Attributes:
        session: FK to SearchSession being shared
        inviter: FK to User who sent invitation (session owner)
        invitee: FK to User who accepted invitation (null until accepted)
        invitee_email: Email address of invitee
        invitee_name: Optional display name of invitee
        invited_at: Timestamp when invitation was created
        responded_at: Timestamp when invitation was accepted/declined
    """

    # Additional status beyond base choices
    STATUS_DECLINED = "DECLINED"

    STATUS_CHOICES = AbstractInvitation.BASE_STATUS_CHOICES + [
        (STATUS_DECLINED, "Declined"),
    ]

    # Relationships
    session = models.ForeignKey(
        "SearchSession",
        on_delete=models.CASCADE,
        related_name="reviewer_invitations",
        help_text="Review session being shared",
    )
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="review_invitations_sent",
        help_text="User who sent the invitation",
    )
    invitee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="review_invitations_received",
        help_text="User who accepted the invitation (null until accepted)",
    )

    # Invitee details
    invitee_email = models.EmailField(help_text="Email address of invitee")
    invitee_name = models.CharField(
        max_length=255, blank=True, help_text="Optional display name of invitee"
    )

    # Override status field to include DECLINED choice
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=AbstractInvitation.STATUS_PENDING,
        help_text="Current status of the invitation",
    )

    # Timestamps
    invited_at = models.DateTimeField(
        auto_now_add=True, help_text="When the invitation was created"
    )
    responded_at = models.DateTimeField(
        null=True, blank=True, help_text="When the invitation was accepted/declined"
    )

    class Meta:
        db_table = "review_invitations"
        verbose_name = "Review Invitation"
        verbose_name_plural = "Review Invitations"
        constraints = [
            models.UniqueConstraint(
                fields=["session", "invitee_email"],
                name="unique_session_invitee_email",
            ),
        ]
        indexes = [
            models.Index(fields=["invitee_email", "status"]),
            models.Index(fields=["session", "status"]),
        ]
        ordering = ["-invited_at"]

    def __str__(self):
        """Return string representation of the invitation."""
        return f"Invitation: {self.invitee_email} to {self.session.title}"

    def get_magic_link_url_name(self) -> str:
        """Return URL pattern name for review invitation acceptance."""
        return "review_manager:accept_invitation"

    def get_magic_link(self, request=None) -> str:
        """Generate magic link URL with fallback to SITE_DOMAIN."""
        if request:
            return super().get_magic_link(request)

        # Fallback: construct URL from settings
        from django.conf import settings
        from django.urls import reverse

        path = reverse(self.get_magic_link_url_name(), kwargs={"token": self.token})
        protocol = (
            "https" if getattr(settings, "SECURE_SSL_REDIRECT", False) else "http"
        )
        domain = getattr(settings, "SITE_DOMAIN", "localhost:8000")
        return f"{protocol}://{domain}{path}"


class SessionActivity(models.Model):
    """
    Audit trail for SearchSession activities.
    Tracks all significant events and changes in a search session.
    """

    ACTIVITY_TYPES = [
        ("created", "Session Created"),
        ("status_changed", "Status Changed"),
        ("search_defined", "Search Defined"),
        ("search_executed", "Search Executed"),
        ("results_processed", "Results Processed"),
        ("review_started", "Review Started"),
        ("review_completed", "Review Completed"),
        ("exported", "Data Exported"),
        ("shared", "Session Shared"),
        ("note_added", "Note Added"),
        ("settings_changed", "Settings Changed"),
        # Added new types for monitoring and recovery
        ("auto_execution", "Automatic Execution"),
        ("execution_started", "Execution Started"),
        ("execution_failed", "Execution Failed"),
        ("processing_failed", "Processing Failed"),
        ("transition_failed", "Transition Failed"),
        ("manual_recovery", "Manual Recovery"),
        ("auto_recovery", "Automatic Recovery"),
        ("api_recovery", "API Recovery"),
        ("recovery_action", "Recovery Action"),
        ("search_started", "Search Started"),
        ("state_change", "State Change"),
        ("state_transition", "State Transition"),
        ("status_change", "Status Change"),
        # New types for enhanced state management
        ("state_reconciliation", "State Reconciliation"),
        ("backwards_transition_blocked", "Backwards Transition Blocked"),
        ("state_recovery", "State Recovery"),
        # Dual-screening configuration tracking (Phase 5)
        ("configuration_saved", "Configuration Saved"),
        ("configuration_changed", "Configuration Changed"),
        # External reviewer approval workflow (Phase G)
        ("external_reviewers_pending_approval", "External Reviewers Pending Approval"),
        ("external_reviewers_approved", "External Reviewers Approved"),
        ("external_reviewers_rejected", "External Reviewers Rejected"),
        # Iterative search audit trail
        ("strategy_modified", "Strategy Modified"),
        ("search_iteration_started", "Search Iteration Started"),
        ("search_iteration_completed", "Search Iteration Completed"),
        ("results_hidden", "Results Hidden"),
        ("results_unhidden", "Results Unhidden"),
        # Manual result addition (Issue #76)
        ("manual_result_added", "Manual Result Added"),
    ]

    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relationships
    session = models.ForeignKey(
        SearchSession,
        on_delete=models.CASCADE,
        related_name="activities",
        help_text="The search session this activity belongs to",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        help_text="User who performed this activity",
    )

    # Activity details
    activity_type = models.CharField(
        max_length=50, choices=ACTIVITY_TYPES, help_text="Type of activity performed"
    )
    description = models.TextField(help_text="Detailed description of the activity")

    # Additional data
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional activity metadata (e.g., old/new values). See ActivityMetadataType in model_types.py",
    )

    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "session_activities"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "-created_at"]),
            models.Index(fields=["activity_type"]),
            models.Index(fields=["created_at"]),
        ]
        verbose_name_plural = "Session activities"

    def __str__(self):
        return f"{self.get_activity_type_display()} - {self.session.title} ({self.created_at})"

    @classmethod
    def log_activity(
        cls,
        session,
        activity_type,
        description,
        user=None,
        metadata=None,
    ):
        """
        Convenience method to log an activity.

        Args:
            session: The SearchSession instance
            activity_type: Type of activity (from ACTIVITY_TYPES)
            description: Description of the activity
            user: User who performed the activity (optional)
            metadata: Additional metadata dict (optional)

        Returns:
            SessionActivity instance
        """
        return cls.objects.create(
            session=session,
            activity_type=activity_type,
            description=description,
            user=user,
            metadata=metadata or {},
        )


class ReviewConfiguration(models.Model):
    """
    Versioned snapshot of review configuration for dual-screening methodology.

    Stores the review methodology settings configured by the lead reviewer before
    search execution. Supports versioning for mid-review configuration changes
    with complete audit trail for PRISMA 2020 compliance.

    Related Models:
        - SearchSession: Parent review session (many configurations per session)
        - ConfigurationChange: Audit trail of configuration modifications
        - Organisation: Organisation-level defaults
    """

    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relationships
    session = models.ForeignKey(
        "SearchSession",
        on_delete=models.CASCADE,
        related_name="configurations",
        help_text="Search session this configuration applies to",
    )

    # Version tracking
    version = models.IntegerField(
        default=1, help_text="Configuration version number (increments on changes)"
    )

    # Review methodology
    min_reviewers_per_result = models.IntegerField(
        default=2,
        choices=[
            (1, "1 Reviewer (Single Screening)"),
            (2, "2 Reviewers (Dual Screening)"),
            (3, "3 Reviewers (Triple Screening)"),
            (4, "4 Reviewers (Multiple Screening)"),
        ],
        help_text="Number of independent reviewers required per result",
    )

    # Conflict resolution method choices (for Workflow #2)
    RESOLUTION_METHOD_CHOICES = [
        ("CONSENSUS", "Consensus Discussion"),
        ("LEAD_ARBITRATION", "Lead Reviewer Arbitration"),
        ("DESIGNATED_ARBITRATOR", "Designated Arbitrator"),
        ("MAJORITY", "Majority Vote (3+ reviewers)"),
    ]

    conflict_resolution_method = models.CharField(
        max_length=30,
        choices=RESOLUTION_METHOD_CHOICES,
        default="LEAD_ARBITRATION",
        help_text="How conflicts between reviewers are resolved",
    )
    consensus_criteria = models.CharField(
        max_length=20,
        choices=[
            ("MAJORITY", "Simple Majority (>50%)"),
            ("UNANIMOUS", "Unanimous Agreement (100%)"),
        ],
        default="MAJORITY",
        help_text="What defines agreement when reviewers vote",
    )
    blind_screening_enforced = models.BooleanField(
        default=True,
        help_text="Whether reviewers can see others' decisions (always True for PRISMA compliance)",
    )

    # Inter-rater reliability threshold (PRISMA 2020 compliance)
    irr_threshold = models.FloatField(
        default=0.70,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Minimum Cohen's Kappa for acceptable IRR (PRISMA 2020 guideline: 0.70)",
    )

    # Invited reviewers (captured during review setup)
    invited_reviewers = models.JSONField(
        default=list,
        blank=True,
        help_text="List of reviewers invited to participate (stores email, first_name, last_name)",
    )

    # Arbitrator details (conditional on conflict_resolution_method)
    designated_arbitrator_email = models.EmailField(
        blank=True, help_text="Email address of designated arbitrator"
    )
    designated_arbitrator_name = models.CharField(
        max_length=255, blank=True, help_text="Full name of designated arbitrator"
    )
    designated_arbitrator_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="arbitrated_reviews",
        help_text="User account of arbitrator (if registered)",
    )

    # Versioning timestamps
    effective_from = models.DateTimeField(
        auto_now_add=True, help_text="When this configuration version became active"
    )
    effective_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this configuration version was superseded (null = current)",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_configurations",
        help_text="User who created this configuration",
    )

    # Organisation context (multi-tenancy)
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.PROTECT,
        related_name="review_configurations",
        null=True,
        blank=True,
        help_text="Organisation managing this review configuration (optional for personal reviews)",
    )

    # External Reviewer Approval Tracking (Phase B)
    external_reviewers_pending_approval = models.JSONField(
        default=list,
        blank=True,
        help_text="External reviewers awaiting IS approval. Format: [{email, first_name, last_name}, ...]",
    )

    external_reviewers_approved = models.BooleanField(
        default=False,
        help_text="Whether Information Specialist has approved external reviewers",
    )

    external_reviewers_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_external_reviewers_configs",
        help_text="Information Specialist who approved external reviewers",
    )

    external_reviewers_approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when external reviewers were approved",
    )

    external_reviewers_rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_external_reviewers_configs",
        help_text="Information Specialist who rejected external reviewers",
    )

    external_reviewers_rejected_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when external reviewers were rejected",
    )

    external_reviewers_rejection_reason = models.TextField(
        blank=True, help_text="Reason provided by IS for rejecting external reviewers"
    )

    # SLA time-boxing fields (nudge-style, not enforced)
    discussion_sla_hours = models.PositiveIntegerField(
        default=72,
        help_text="SLA hours for discussion phase (nudge, not enforced)",
    )
    revote_sla_hours = models.PositiveIntegerField(
        default=24,
        help_text="SLA hours for re-vote phase (nudge, not enforced)",
    )
    arbitration_sla_hours = models.PositiveIntegerField(
        default=48,
        help_text="SLA hours for arbitration/escalation phase (nudge, not enforced)",
    )

    class Meta:
        db_table = "review_configurations"
        ordering = ["-version"]
        indexes = [
            models.Index(fields=["session", "version"]),
            models.Index(fields=["session", "effective_from"]),
            models.Index(fields=["organisation"]),
            models.Index(
                fields=["external_reviewers_approved"], name="idx_ext_rev_approved"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "version"],
                name="unique_session_configuration_version",
            )
        ]

    def __str__(self):
        return f"{self.session.title} - Config v{self.version} ({self.min_reviewers_per_result} reviewers)"

    REVIEW_MODE_BY_REVIEWERS = {1: "SINGLE", 2: "DUAL", 3: "TRIPLE", 4: "QUAD"}

    @property
    def is_workflow_2(self):
        """
        Detect if this configuration uses Workflow #2 (Independent Screening).

        Returns:
            bool: True if min_reviewers_per_result >= 2 (Workflow #2 with conflict detection)
        """
        return self.min_reviewers_per_result >= 2

    @property
    def review_mode_defaults(self) -> tuple[str, int]:
        """(review_mode, min_reviewers_required) implied by this config.

        WF2+ maps the reviewer count to its review mode; WF1 is SINGLE/1.
        Single source of truth for ProcessedResult review-mode fields.
        """
        if self.is_workflow_2:
            n = self.min_reviewers_per_result
            return self.REVIEW_MODE_BY_REVIEWERS.get(n, "DUAL"), n
        return "SINGLE", 1

    @property
    def workflow_name(self):
        """
        Get human-readable workflow name.

        Returns:
            str: 'Work Distribution' or 'Independent Screening' based on min_reviewers_per_result
        """
        if self.is_workflow_2:
            return "Independent Screening"
        return "Work Distribution"

    def clean(self):
        """Validate configuration consistency."""
        # Validate min_reviewers is in valid range
        if self.min_reviewers_per_result not in [1, 2, 3, 4]:
            raise ValidationError("min_reviewers_per_result must be between 1 and 4")

        # Validate arbitrator details if designated arbitrator method
        if self.conflict_resolution_method == "DESIGNATED_ARBITRATOR":
            if not self.designated_arbitrator_email:
                raise ValidationError(
                    "designated_arbitrator_email required for DESIGNATED_ARBITRATOR method"
                )
            if not self.designated_arbitrator_name:
                raise ValidationError(
                    "designated_arbitrator_name required for DESIGNATED_ARBITRATOR method"
                )

        # Validate consensus criteria makes sense with reviewer count
        if self.consensus_criteria == "UNANIMOUS" and self.min_reviewers_per_result < 2:
            raise ValidationError("Unanimous agreement requires at least 2 reviewers")

        # Validate MAJORITY resolution requires 3+ reviewers
        if (
            self.conflict_resolution_method == "MAJORITY"
            and self.min_reviewers_per_result < 3
        ):
            raise ValidationError("MAJORITY resolution requires at least 3 reviewers")


class ConfigurationChange(models.Model):
    """
    Audit trail for mid-review configuration changes.

    Tracks when and why review configuration was modified after results have
    been reviewed. Critical for PRISMA 2020 reporting requirements to document
    deviations from original methodology.

    Related Models:
        - SearchSession: Review session that was reconfigured
        - ReviewConfiguration: The old and new configuration versions
    """

    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relationships
    session = models.ForeignKey(
        "SearchSession",
        on_delete=models.CASCADE,
        related_name="configuration_changes",
        help_text="Session that was reconfigured",
    )
    from_configuration = models.ForeignKey(
        "ReviewConfiguration",
        on_delete=models.PROTECT,
        related_name="changes_from",
        help_text="Previous configuration version",
    )
    to_configuration = models.ForeignKey(
        "ReviewConfiguration",
        on_delete=models.PROTECT,
        related_name="changes_to",
        help_text="New configuration version",
    )

    # Change metadata
    change_reason = models.TextField(help_text="Justification for configuration change")
    changed_fields = models.JSONField(
        default=dict, help_text="Fields changed: {'field_name': {'old': X, 'new': Y}}"
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        help_text="User who made the configuration change",
    )
    changed_at = models.DateTimeField(
        auto_now_add=True, help_text="When configuration was changed"
    )

    # Impact tracking
    results_affected_count = models.IntegerField(
        default=0,
        help_text="Number of results already reviewed under old configuration",
    )
    deviation_tag_applied = models.BooleanField(
        default=False,
        help_text="Whether affected results were tagged as configuration deviations",
    )

    class Meta:
        db_table = "configuration_changes"
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["session", "-changed_at"]),
            models.Index(fields=["changed_by"]),
        ]

    def __str__(self):
        return f"{self.session.title} - v{self.from_configuration.version} → v{self.to_configuration.version}"
