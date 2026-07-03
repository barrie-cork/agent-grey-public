# Composite index for the PRISMA provenance counts, which filter
# BrowsingVisit by (session, captured_incognito). Also syncs the
# help_text (em dash removed per repo documentation rules).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("review_results", "0024_browsingvisit_captured_incognito"),
    ]

    operations = [
        migrations.AlterField(
            model_name="browsingvisit",
            name="captured_incognito",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True if captured in an incognito window (de-personalised "
                    "search). False covers both 'normal window' and 'incognito "
                    "unavailable' - the safe default is to assume searches were "
                    "NOT de-personalised."
                ),
            ),
        ),
        migrations.AddIndex(
            model_name="browsingvisit",
            index=models.Index(
                fields=["session", "captured_incognito"],
                name="bv_session_incognito_idx",
            ),
        ),
    ]
