from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

from .managers import ProcessedResultQuerySet


class ProcessedResult(TimeStampedModel):
    """
    Normalized and processed search result.
    This is the cleaned, deduplicated version of raw results.
    """

    # Relationships
    session = models.ForeignKey(
        "review_manager.SearchSession",
        on_delete=models.CASCADE,
        related_name="processed_results",
        help_text="The search session this result belongs to",
    )
    raw_result = models.ForeignKey(
        "serp_execution.RawSearchResult",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_version",
        help_text="The original raw result this was processed from",
    )

    # Core fields (normalized)
    title = models.TextField(help_text="Cleaned and normalized title")
    url = models.URLField(max_length=2048, help_text="Canonical URL")
    snippet = models.TextField(blank=True, help_text="Cleaned snippet or abstract")

    # Extracted metadata
    authors = models.JSONField(
        default=list,
        blank=True,
        help_text="List of author names. See AuthorListType in model_types.py",
    )
    publication_date = models.DateField(
        null=True, blank=True, help_text="Extracted publication date"
    )
    publication_year = models.IntegerField(
        null=True, blank=True, help_text="Publication year for easier filtering"
    )

    # Document metadata
    document_type = models.CharField(
        max_length=50, blank=True, help_text="Type of document (report, thesis, etc.)"
    )
    language = models.CharField(
        max_length=10, default="en", help_text="Document language code"
    )
    source_organization = models.CharField(
        max_length=255, blank=True, help_text="Publishing organization"
    )
    domain = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Extracted domain from URL for aggregation and filtering",
    )

    # Content indicators
    full_text_url = models.URLField(
        max_length=2048, blank=True, help_text="Direct link to full text (PDF, etc.)"
    )
    is_pdf = models.BooleanField(default=False, help_text="Whether the result is a PDF")

    # Iteration tracking
    execution_round = models.IntegerField(
        default=1,
        help_text="Which search strategy iteration produced this result (1-based)",
    )

    # Hide/exclude support
    is_hidden = models.BooleanField(
        default=False,
        help_text="Whether this result is hidden/excluded from review",
    )
    hidden_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Reason for hiding this result (e.g. 'Excluded: iteration 2 results hidden by user')",
    )

    # Processing metadata
    processed_at = models.DateTimeField(
        auto_now_add=True, help_text="When this result was processed"
    )

    # Processing status constants
    STATUS_SUCCESS = "success"
    STATUS_FILTERED = "filtered"
    STATUS_ERROR = "error"

    PROCESSING_STATUS_CHOICES = [
        (STATUS_SUCCESS, "Successfully Processed"),
        (STATUS_FILTERED, "Filtered Out (Duplicate)"),
        (STATUS_ERROR, "Processing Error"),
    ]

    # Processing status and error tracking (Issue #100) - Simplified
    processing_status = models.CharField(
        max_length=50,
        choices=PROCESSING_STATUS_CHOICES,
        default=STATUS_SUCCESS,
        help_text="Status of the processing attempt",
    )
    processing_error_category = models.CharField(
        max_length=100, blank=True, help_text="Category of processing error if any"
    )
    processing_error_message = models.TextField(
        blank=True, help_text="User-friendly error message if processing failed"
    )

    # Review status
    is_reviewed = models.BooleanField(
        default=False, help_text="Whether this result has been reviewed"
    )
    is_retrieved = models.BooleanField(
        default=False, help_text="Whether the user has clicked to view the source URL"
    )
    retrieved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user first clicked to view the source",
    )
    review_priority = models.IntegerField(
        default=0, help_text="Priority score for manual review (0-10)"
    )

    # Multi-reviewer screening fields (Phase 2)
    review_mode = models.CharField(
        max_length=20,
        default="SINGLE",
        choices=[
            ("SINGLE", "Single Reviewer"),
            ("DUAL", "Dual Independent Reviewers"),
            ("TRIPLE", "Triple Independent Reviewers"),
            ("QUAD", "Quad Independent Reviewers"),
        ],
        help_text="Review mode for this result",
    )
    min_reviewers_required = models.IntegerField(
        default=1, help_text="Minimum number of reviewers required for this result"
    )
    reviewers_completed = models.IntegerField(
        default=0,
        help_text="Number of reviewers who have completed their review (denormalized)",
    )
    consensus_reached = models.BooleanField(
        default=False,
        help_text="Whether reviewers have reached consensus on this result",
    )

    # Manual addition tracking (Issue #76)
    is_manually_added = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this result was manually added during screening",
    )
    manually_added_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manually_added_results",
        help_text="The reviewer who manually added this result",
    )
    manual_addition_justification = models.TextField(
        blank=True,
        help_text="Justification for why this result was manually added",
    )

    objects = ProcessedResultQuerySet.as_manager()

    class Meta:
        db_table = "processed_results"
        ordering = ["-processed_at"]  # Most recently processed first
        indexes = [
            models.Index(fields=["session", "is_reviewed"]),
            models.Index(fields=["url"]),
            models.Index(fields=["publication_year"]),
            models.Index(fields=["document_type"]),
            models.Index(fields=["-processed_at"]),  # For ordering by processing time
            models.Index(fields=["session", "execution_round"]),
            models.Index(fields=["session", "is_hidden"]),
        ]

    def __str__(self):
        """Return string representation of the ProcessedResult.

        Returns:
            Truncated title with publication year or 'Unknown'.
        """
        return f"{self.title[:50]}... ({self.publication_year or 'Unknown'})"

    def save(self, *args, **kwargs):
        """Extract year and domain from data if available.

        Args:
            *args: Variable positional arguments passed to parent save method.
            **kwargs: Variable keyword arguments passed to parent save method.
        """
        # Extract year from date if available
        if self.publication_date and not self.publication_year:
            self.publication_year = self.publication_date.year

        # Extract domain from URL if not set
        if self.url and not self.domain:
            from apps.core.utils import extract_domain

            self.domain = extract_domain(self.url, lowercase=True, strip_www=False)

        super().save(*args, **kwargs)

    def get_display_url(self):
        """Get a shortened display version of the URL.

        Returns:
            The netloc portion of the URL (domain name).
        """
        from urllib.parse import urlparse

        parsed = urlparse(self.url)
        return parsed.netloc

    @property
    def is_duplicate(self) -> bool:
        """Whether this result was filtered as a duplicate."""
        return (
            self.processing_status == "filtered"
            and self.processing_error_category == "duplicate"
        )

    @property
    def has_full_text(self):
        """Check if full text is available based on PDF status or full_text_url.

        Returns:
            True if result is a PDF or has a full text URL, False otherwise.
        """
        return bool(self.is_pdf or self.full_text_url)

    def get_query_metadata(self):
        """Get search query metadata for this result.

        Retrieves detailed information about the search query that found this result,
        including query text, type, domain filters, execution details, and SERP metadata.

        Returns:
            dict: Query metadata containing:
                - query_text: The search query string
                - query_type: Type of query (domain-specific, general, etc.)
                - target_domain: Domain filter if applicable
                - execution_order: Query execution sequence number
                - serp_source: SERP provider name (e.g., 'Serper.dev')
                - search_engine: Search engine used (e.g., 'google')
                - result_position: Position in SERP results
                - found_at: Timestamp when result was discovered
            None: If raw_result or execution is not available
        """
        if not self.raw_result or not self.raw_result.execution:
            return None

        execution = self.raw_result.execution
        query = execution.query if hasattr(execution, "query") else None

        if not query:
            return None

        return {
            "query_text": query.query_text,
            "query_type": (
                query.get_query_type_display()
                if hasattr(query, "get_query_type_display")
                else query.query_type
            ),
            "target_domain": query.target_domain or None,
            "execution_order": query.execution_order,
            "serp_source": getattr(execution, "serp_provider_display", "Serper.dev"),
            "search_engine": execution.search_engine,
            "result_position": (
                self.raw_result.position
                if hasattr(self.raw_result, "position")
                else None
            ),
            "found_at": execution.completed_at,
        }


class ProcessingSession(TimeStampedModel):
    """
    Tracks the processing status for a search session.
    Shows progress through various stages of result processing.
    """

    PROCESSING_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("partial", "Partial"),
    ]

    PROCESSING_STAGES = [
        ("initialization", "Initialization"),
        ("url_normalization", "URL Normalization"),
        ("deduplication", "Deduplication"),
        ("finalization", "Finalization"),
    ]

    # Relationship
    search_session = models.OneToOneField(
        "review_manager.SearchSession",
        on_delete=models.CASCADE,
        related_name="processing_session",
        help_text="The search session being processed",
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS_CHOICES,
        default="pending",
        help_text="Current processing status",
    )
    current_stage = models.CharField(
        max_length=30,
        choices=PROCESSING_STAGES,
        blank=True,
        help_text="Current processing stage",
    )
    stage_progress = models.IntegerField(
        default=0, help_text="Progress within current stage (0-100)"
    )

    # Counts
    total_raw_results = models.IntegerField(
        default=0, help_text="Total number of raw results to process"
    )
    processed_count = models.IntegerField(
        default=0, help_text="Number of results processed so far"
    )
    error_count = models.IntegerField(
        default=0, help_text="Number of processing errors encountered"
    )
    duplicate_count = models.IntegerField(
        default=0, help_text="Number of duplicates found"
    )
    unique_count = models.IntegerField(
        default=0, help_text="Number of unique results after deduplication"
    )

    # Timing
    started_at = models.DateTimeField(
        null=True, blank=True, help_text="When processing started"
    )
    completed_at = models.DateTimeField(
        null=True, blank=True, help_text="When processing completed"
    )
    last_heartbeat = models.DateTimeField(
        null=True, blank=True, help_text="Last progress update timestamp"
    )

    # Error tracking
    error_details = models.JSONField(
        default=list,
        blank=True,
        help_text="List of processing errors with details. See ErrorDetailsType in model_types.py",
    )
    retry_count = models.IntegerField(default=0, help_text="Number of retry attempts")

    # Configuration
    processing_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Processing configuration parameters. See ProcessingConfigType in model_types.py",
    )
    celery_task_id = models.CharField(
        max_length=255, blank=True, help_text="Associated Celery task ID"
    )

    class Meta:
        db_table = "processing_sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["search_session", "status"]),
            models.Index(fields=["status", "started_at"]),
        ]

    def __str__(self):
        """Return string representation of the ProcessingSession.

        Returns:
            Description with search session title and current status.
        """
        return f"Processing {self.search_session.title} - {self.get_status_display()}"

    @property
    def progress_percentage(self):
        """Calculate overall progress percentage.

        Returns:
            Integer percentage (0-100) of processing completion.
        """
        if self.total_raw_results == 0:
            return 0
        return min(100, int((self.processed_count / self.total_raw_results) * 100))

    def update_heartbeat(self):
        """Update the last heartbeat timestamp.

        Sets last_heartbeat to current time and saves only that field.
        """
        self.last_heartbeat = timezone.now()
        self.save(update_fields=["last_heartbeat"])

    def start_processing(self, total_raw_results, celery_task_id="", metadata=None):
        """Start the processing session.

        Args:
            total_raw_results: Integer count of raw results to process.
            celery_task_id: String ID of the associated Celery task.
            metadata: Optional dict with additional processing metadata.
        """
        self.status = "in_progress"
        self.current_stage = "initialization"
        self.started_at = timezone.now()
        self.total_raw_results = total_raw_results
        self.celery_task_id = celery_task_id

        # Store metadata if provided and field exists
        if metadata and hasattr(self, "processing_metadata"):
            self.processing_metadata = self.processing_metadata or {}
            self.processing_metadata.update(metadata)
            fields_to_update = [
                "status",
                "current_stage",
                "started_at",
                "total_raw_results",
                "celery_task_id",
                "processing_metadata",
            ]
        else:
            fields_to_update = [
                "status",
                "current_stage",
                "started_at",
                "total_raw_results",
                "celery_task_id",
            ]

        self.save(update_fields=fields_to_update)

    def complete_processing(self):
        """Mark processing as completed.

        Sets status to 'completed', records completion time, and saves.
        """
        self.status = "completed"
        self.current_stage = "finalization"
        self.stage_progress = 100
        self.completed_at = timezone.now()
        self.save(
            update_fields=["status", "current_stage", "stage_progress", "completed_at"]
        )

    def fail_processing(self, error_message, error_details=None):
        """Mark processing as failed with error details.

        Args:
            error_message: String description of the error.
            error_details:  dict with additional error information.
        """
        self.status = "failed"
        self.completed_at = timezone.now()

        # Add error to error_details list
        error_entry = {
            "timestamp": timezone.now().isoformat(),
            "message": error_message,
            "details": error_details or {},
        }
        if not isinstance(self.error_details, list):
            self.error_details = []
        self.error_details.append(error_entry)
        self.error_count += 1

        self.save(
            update_fields=["status", "completed_at", "error_details", "error_count"]
        )

    def update_progress(self, stage, stage_progress, **kwargs):
        """Update processing progress with stage and percentage.

        Session status updates are handled by callers (tasks/batch_processor)
        which already have access to the SearchSession instance.

        Args:
            stage: String identifier of the current processing stage.
            stage_progress: Integer percentage (0-100) of stage completion.
            **kwargs: Additional field updates to apply.
        """
        self.current_stage = stage
        self.stage_progress = max(0, min(100, stage_progress))
        self.last_heartbeat = timezone.now()

        # Update additional fields if provided
        update_fields = ["current_stage", "stage_progress", "last_heartbeat"]
        for field, value in kwargs.items():
            if hasattr(self, field):
                setattr(self, field, value)
                update_fields.append(field)

        self.save(update_fields=update_fields)

    def add_error(self, error_message, error_details=None):
        """Add an error to the error tracking list.

        Args:
            error_message: String description of the error.
            error_details:  dict with additional error information.
        """
        error_entry = {
            "timestamp": timezone.now().isoformat(),
            "message": error_message,
            "details": error_details or {},
        }

        if not isinstance(self.error_details, list):
            self.error_details = []

        self.error_details.append(error_entry)
        self.error_count += 1

        self.save(update_fields=["error_details", "error_count"])

    @property
    def duration_seconds(self):
        """Calculate processing duration in seconds.

        Returns:
            Integer seconds elapsed since processing started, or None if not started.
            Uses completed_at if available, otherwise current time.
        """
        if not self.started_at:
            return None

        end_time = self.completed_at or timezone.now()
        duration = end_time - self.started_at
        return int(duration.total_seconds())

    @property
    def estimated_completion(self):
        """Estimate completion time based on current progress.

        Returns:
            Datetime estimate of when processing will complete, or None if
            processing hasn't started or has no progress yet. Uses linear
            estimation based on current progress rate.
        """
        if (
            not self.started_at
            or self.total_raw_results == 0
            or self.processed_count == 0
        ):
            return None

        # Simple linear estimation based on progress
        elapsed = timezone.now() - self.started_at
        progress_ratio = self.processed_count / self.total_raw_results

        if progress_ratio <= 0:
            return None

        total_estimated_time = elapsed / progress_ratio
        return self.started_at + total_estimated_time
