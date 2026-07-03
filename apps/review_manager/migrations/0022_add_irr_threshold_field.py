# Generated manually for Phase 01: Model Validation & Configuration Enhancement
# Add irr_threshold field to ReviewConfiguration model

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("review_manager", "0021_migrate_invited_reviewers_data"),
    ]

    operations = [
        migrations.AddField(
            model_name="reviewconfiguration",
            name="irr_threshold",
            field=models.FloatField(
                default=0.70,
                validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
                help_text="Minimum Cohen's Kappa for acceptable IRR (PRISMA 2020 guideline: 0.70)",
            ),
        ),
    ]
