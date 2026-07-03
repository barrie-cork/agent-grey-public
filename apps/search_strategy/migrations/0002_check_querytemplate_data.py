import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def check_querytemplate_usage(apps, schema_editor):
    QueryTemplate = apps.get_model("search_strategy", "QueryTemplate")
    count = QueryTemplate.objects.count()
    if count > 0:
        logger.warning(
            "Found %d QueryTemplate instances in database. "
            "Consider exporting this data before removing the model. "
            "Run: python manage.py dumpdata search_strategy.QueryTemplate > querytemplate_backup.json",
            count,
        )


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("search_strategy", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(check_querytemplate_usage, reverse_func),
    ]
