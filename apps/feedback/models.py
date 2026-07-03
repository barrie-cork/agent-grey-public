"""
Models for user feedback system.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TimeStampedModel

SEVERITY_CHOICES = [
    ("must_have", "Must Have"),
    ("should_have", "Should Have"),
    ("nice_to_have", "Nice To Have"),
]

FREQUENCY_CHOICES = [
    ("always", "Always"),
    ("sometimes", "Sometimes"),
    ("once", "Once"),
]

DECISION_CHOICES = [
    ("pending", "Pending"),
    ("accepted", "Accepted"),
    ("rejected", "Rejected"),
    ("deferred", "Deferred"),
    ("completed", "Completed"),
    ("duplicate", "Duplicate"),
    ("needs_info", "Needs Info"),
]


class UserFeedback(TimeStampedModel):
    """
    Model for storing user feedback about specific pages.

    Allows both authenticated and anonymous users to provide feedback
    about their experience on different pages of the application.
    """

    FEEDBACK_TYPES = [
        ("bug", "Bug Report"),
        ("idea", "Feature Idea"),
        ("suggestion", "Suggestion"),
        ("general", "General Feedback"),
    ]

    STATUS_CHOICES = [
        ("new", "New"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("dismissed", "Dismissed"),
    ]

    RATING_CHOICES = [
        (1, "1 Star - Poor"),
        (2, "2 Stars - Fair"),
        (3, "3 Stars - Good"),
        (4, "4 Stars - Very Good"),
        (5, "5 Stars - Excellent"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_submissions",
        help_text="User who submitted this feedback (optional for anonymous feedback)",
    )

    email = models.EmailField(
        null=True,
        blank=True,
        help_text="Email address for anonymous feedback follow-up",
    )

    page_path = models.CharField(
        max_length=500, help_text="URL path of the page where feedback was submitted"
    )

    page_title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Title of the page where feedback was submitted",
    )

    feedback_type = models.CharField(
        max_length=20,
        choices=FEEDBACK_TYPES,
        default="general",
        help_text="Category of feedback",
    )

    subject = models.CharField(
        max_length=200, blank=True, help_text="Brief subject line for the feedback"
    )

    message = models.TextField(help_text="Detailed feedback message")

    rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        null=True,
        blank=True,
        help_text="Optional rating (1-5 stars)",
    )

    browser_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="Browser and technical information for debugging",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new",
        help_text="Current status of this feedback",
    )

    admin_notes = models.TextField(
        blank=True, help_text="Internal notes for administrators"
    )

    # --- Voice ---
    transcription = models.TextField(
        blank=True, default="", help_text="Transcribed text from voice recording"
    )
    audio_file = models.FileField(
        upload_to="feedback/audio/%Y/%m/", null=True, blank=True
    )
    audio_duration_ms = models.PositiveIntegerField(
        null=True, blank=True, help_text="Recording duration in milliseconds"
    )
    voice_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="recording_stopped_by, transcription_service, confidence",
    )

    # --- Screenshot ---
    screenshot = models.ImageField(
        upload_to="feedback/screenshots/%Y/%m/", null=True, blank=True
    )

    # --- Enhanced categorisation ---
    severity = models.CharField(
        max_length=20, choices=SEVERITY_CHOICES, blank=True, default=""
    )
    expected_behaviour = models.TextField(blank=True, default="")
    actual_behaviour = models.TextField(blank=True, default="")
    frequency = models.CharField(
        max_length=20, choices=FREQUENCY_CHOICES, blank=True, default=""
    )

    # --- Rich context ---
    interaction_context = models.JSONField(
        default=dict,
        blank=True,
        help_text="pages_visited, recent_clicks, js_errors",
    )
    screen_category = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Auto-categorised from page_path",
    )

    # --- GitHub issue linking ---
    github_issue_url = models.URLField(blank=True, default="")
    github_issue_number = models.PositiveIntegerField(null=True, blank=True)
    github_issue_state = models.CharField(max_length=20, blank=True, default="")
    github_issue_resolution = models.CharField(max_length=20, blank=True, default="")
    github_issue_closed_at = models.DateTimeField(null=True, blank=True)

    # --- Triage ---
    team_decision = models.CharField(
        max_length=20, choices=DECISION_CHOICES, blank=True, default=""
    )
    team_decision_notes = models.TextField(blank=True, default="")
    team_decision_at = models.DateTimeField(null=True, blank=True)

    # --- Contact ---
    contact_email = models.EmailField(blank=True, default="")

    class Meta:
        db_table = "feedback_userfeedback"
        ordering = ["-created_at"]
        verbose_name = "User Feedback"
        verbose_name_plural = "User Feedback"
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["page_path"]),
            models.Index(fields=["feedback_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["user"]),
            models.Index(fields=["severity"]),
            models.Index(fields=["team_decision"]),
            models.Index(fields=["github_issue_number"]),
        ]

    def __str__(self):
        user_display = self.user.username if self.user else "Anonymous"
        return (
            f"{user_display} - {self.get_feedback_type_display()} on {self.page_path}"
        )

    def get_absolute_url(self):
        return reverse("admin:feedback_userfeedback_change", args=[self.pk])

    @property
    def is_anonymous(self):
        """Check if this feedback was submitted anonymously."""
        return self.user is None

    @property
    def submitter_display(self):
        """Get display name for the feedback submitter."""
        if self.user:
            return self.user.username
        elif self.email:
            return f"Anonymous ({self.email})"
        else:
            return "Anonymous"

    @property
    def is_critical(self):
        """Check if this feedback should be considered critical."""
        return self.feedback_type == "bug" and self.rating and self.rating <= 2

    def categorize_screen(self) -> str:
        """Auto-categorize screen from page_path for clustering."""
        SCREEN_MAP = {
            "/search": "Search",
            "/results": "Results",
            "/review": "Review",
            "/admin": "Admin",
            "/profile": "Profile",
            "/api": "API",
        }
        if not self.page_path:
            return "Other"
        for prefix, category in SCREEN_MAP.items():
            if self.page_path.startswith(prefix):
                return category
        return "Other"

    def save(self, *args, **kwargs):
        if not self.screen_category and self.page_path:
            self.screen_category = self.categorize_screen()
        super().save(*args, **kwargs)

    def mark_as_resolved(self, admin_user=None, notes=""):
        """Mark this feedback as resolved."""
        self.status = "resolved"
        if notes:
            self.admin_notes = f"{self.admin_notes}\n\n[{timezone.now()}] Resolved by {admin_user}: {notes}".strip()
        self.save()

    def mark_as_dismissed(self, admin_user=None, notes=""):
        """Mark this feedback as dismissed."""
        self.status = "dismissed"
        if notes:
            self.admin_notes = f"{self.admin_notes}\n\n[{timezone.now()}] Dismissed by {admin_user}: {notes}".strip()
        self.save()
