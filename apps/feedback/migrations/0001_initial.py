# Generated migration for feedback app

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FeedbackStatistics",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "date",
                    models.DateField(
                        help_text="Date for these statistics", unique=True
                    ),
                ),
                (
                    "total_feedback",
                    models.PositiveIntegerField(
                        default=0, help_text="Total feedback submissions for this date"
                    ),
                ),
                (
                    "bug_reports",
                    models.PositiveIntegerField(
                        default=0, help_text="Number of bug reports"
                    ),
                ),
                (
                    "suggestions",
                    models.PositiveIntegerField(
                        default=0, help_text="Number of feature suggestions"
                    ),
                ),
                (
                    "compliments",
                    models.PositiveIntegerField(
                        default=0, help_text="Number of compliments"
                    ),
                ),
                (
                    "average_rating",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Average rating for this date",
                        max_digits=3,
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Feedback Statistics",
                "verbose_name_plural": "Feedback Statistics",
                "db_table": "feedback_statistics",
                "ordering": ["-date"],
            },
        ),
        migrations.CreateModel(
            name="UserFeedback",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Unique identifier for this feedback",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        blank=True,
                        help_text="Email address for anonymous feedback follow-up",
                        max_length=254,
                        null=True,
                    ),
                ),
                (
                    "page_path",
                    models.CharField(
                        help_text="URL path of the page where feedback was submitted",
                        max_length=500,
                    ),
                ),
                (
                    "page_title",
                    models.CharField(
                        blank=True,
                        help_text="Title of the page where feedback was submitted",
                        max_length=200,
                    ),
                ),
                (
                    "feedback_type",
                    models.CharField(
                        choices=[
                            ("bug", "Bug Report"),
                            ("suggestion", "Feature Suggestion"),
                            ("compliment", "Compliment"),
                            ("improvement", "Improvement"),
                            ("other", "Other"),
                        ],
                        default="other",
                        help_text="Category of feedback",
                        max_length=20,
                    ),
                ),
                (
                    "subject",
                    models.CharField(
                        blank=True,
                        help_text="Brief subject line for the feedback",
                        max_length=200,
                    ),
                ),
                ("message", models.TextField(help_text="Detailed feedback message")),
                (
                    "rating",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        choices=[
                            (1, "1 Star - Poor"),
                            (2, "2 Stars - Fair"),
                            (3, "3 Stars - Good"),
                            (4, "4 Stars - Very Good"),
                            (5, "5 Stars - Excellent"),
                        ],
                        help_text="Optional rating (1-5 stars)",
                        null=True,
                    ),
                ),
                (
                    "browser_info",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Browser and technical information for debugging",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("in_progress", "In Progress"),
                            ("resolved", "Resolved"),
                            ("dismissed", "Dismissed"),
                        ],
                        default="new",
                        help_text="Current status of this feedback",
                        max_length=20,
                    ),
                ),
                (
                    "admin_notes",
                    models.TextField(
                        blank=True, help_text="Internal notes for administrators"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, help_text="When this feedback was submitted"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, help_text="When this feedback was last updated"
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who submitted this feedback (optional for anonymous feedback)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="feedback_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "User Feedback",
                "verbose_name_plural": "User Feedback",
                "db_table": "feedback_userfeedback",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="userfeedback",
            index=models.Index(
                fields=["-created_at"], name="feedback_us_created_4c7c68_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="userfeedback",
            index=models.Index(
                fields=["page_path"], name="feedback_us_page_pa_0e1e4a_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="userfeedback",
            index=models.Index(
                fields=["feedback_type"], name="feedback_us_feedbac_c8a42c_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="userfeedback",
            index=models.Index(fields=["status"], name="feedback_us_status_1f3c56_idx"),
        ),
        migrations.AddIndex(
            model_name="userfeedback",
            index=models.Index(fields=["user"], name="feedback_us_user_id_9c7b47_idx"),
        ),
    ]
