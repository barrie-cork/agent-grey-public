# Generated manually to fix unique_count field issue

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("results_manager", "0002_processedresult_review_priority_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="processingsession",
            name="unique_count",
            field=models.IntegerField(
                default=0,
                null=True,
                blank=True,
                help_text="Number of unique results after deduplication",
            ),
        ),
    ]
