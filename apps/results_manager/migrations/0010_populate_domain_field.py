"""
Data migration to populate domain field for existing ProcessedResult records.
"""

from django.db import migrations


def populate_domain_field(apps, schema_editor):
    """Extract and populate domain from existing URLs."""
    # Import here to avoid issues during migrations
    from apps.core.utils.url_utils import extract_domain

    ProcessedResult = apps.get_model("results_manager", "ProcessedResult")

    # Process in batches to avoid memory issues
    batch_size = 1000
    total_updated = 0

    # Get all records with empty domain
    records = ProcessedResult.objects.filter(domain="").select_related(None)
    total_count = records.count()

    print(f"Populating domain for {total_count} ProcessedResult records...")

    for i in range(0, total_count, batch_size):
        batch = list(records[i : i + batch_size])

        for result in batch:
            if result.url:
                result.domain = extract_domain(
                    result.url, lowercase=True, strip_www=False
                )

        # Bulk update for performance
        ProcessedResult.objects.bulk_update(batch, ["domain"], batch_size=500)
        total_updated += len(batch)

        print(f"Progress: {total_updated}/{total_count} records updated")

    print(f"✓ Domain population complete: {total_updated} records updated")


def reverse_populate(apps, schema_editor):
    """Reverse migration - clear domain field."""
    ProcessedResult = apps.get_model("results_manager", "ProcessedResult")
    ProcessedResult.objects.all().update(domain="")


class Migration(migrations.Migration):
    dependencies = [
        ("results_manager", "0009_add_domain_field_to_processed_result"),
    ]

    operations = [
        migrations.RunPython(populate_domain_field, reverse_populate),
    ]
