# Generated 2026-06-04 – Phase 0 browser-extension source capture

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("results_manager", "0014_add_manual_result_fields"),
        ("review_manager", "0032_searchsession_prisma_other_methods"),
        ("review_results", "0022_add_unique_active_conflict_constraint"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BrowsingVisit",
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
                ("url", models.URLField(max_length=2048)),
                ("canonical_url", models.URLField(blank=True, max_length=2048)),
                ("title", models.CharField(blank=True, max_length=512)),
                ("document_type", models.CharField(blank=True, max_length=100)),
                ("site_name", models.CharField(blank=True, max_length=255)),
                ("author", models.CharField(blank=True, max_length=512)),
                ("published_date", models.DateField(blank=True, null=True)),
                ("accessed_at", models.DateTimeField(auto_now_add=True)),
                ("access_successful", models.BooleanField(default=True)),
                (
                    "visit_source",
                    models.CharField(
                        choices=[
                            ("auto", "Auto-logged (capture window)"),
                            ("one_click", "One-click add"),
                        ],
                        default="auto",
                        max_length=20,
                    ),
                ),
                (
                    "client_capture_id",
                    models.CharField(
                        blank=True,
                        help_text="Opaque ID assigned by the browser extension for idempotent ingestion",
                        max_length=64,
                        null=True,
                        unique=True,
                    ),
                ),
                (
                    "promoted_result",
                    models.ForeignKey(
                        blank=True,
                        help_text="ProcessedResult created via Stream-2 one-click add from this visit",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="browsing_visits",
                        to="results_manager.processedresult",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="browsing_visits",
                        to="review_manager.searchsession",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="browsing_visits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "browsing_visits",
                "ordering": ["-accessed_at"],
            },
        ),
        migrations.AddIndex(
            model_name="browsingvisit",
            index=models.Index(
                fields=["session", "accessed_at"],
                name="browsing_vi_session_b1b773_idx",
            ),
        ),
    ]
