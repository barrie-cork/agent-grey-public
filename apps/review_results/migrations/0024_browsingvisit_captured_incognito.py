# Generated 2026-06-18 – browser-extension incognito provenance flag

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("review_results", "0023_add_browsing_visit"),
    ]

    operations = [
        migrations.AddField(
            model_name="browsingvisit",
            name="captured_incognito",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True if captured in an incognito window (de-personalised "
                    "search). False covers both 'normal window' and 'incognito "
                    "unavailable' — the safe default is to assume searches were "
                    "NOT de-personalised."
                ),
            ),
        ),
    ]
