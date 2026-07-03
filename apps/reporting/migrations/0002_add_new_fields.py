# Generated manually to add new fields to ExportReport

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reporting", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="exportreport",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("generating", "Generating"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                default="pending",
                help_text="Report generation status",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="exportreport",
            name="progress_percentage",
            field=models.IntegerField(
                default=0, help_text="Progress percentage (0-100)"
            ),
        ),
        migrations.AddField(
            model_name="exportreport",
            name="error_message",
            field=models.TextField(
                blank=True, help_text="Error message if generation failed"
            ),
        ),
        migrations.AddField(
            model_name="exportreport",
            name="download_count",
            field=models.IntegerField(
                default=0, help_text="Number of times report was downloaded"
            ),
        ),
        migrations.AddField(
            model_name="exportreport",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
                help_text="When report was created",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="exportreport",
            name="completed_at",
            field=models.DateTimeField(
                blank=True, help_text="When report generation completed", null=True
            ),
        ),
        migrations.AlterField(
            model_name="exportreport",
            name="generated_at",
            field=models.DateTimeField(
                blank=True, help_text="When report generation completed", null=True
            ),
        ),
    ]
