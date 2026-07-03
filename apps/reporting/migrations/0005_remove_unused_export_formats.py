# Generated migration to remove unused export formats

from django.db import migrations


def migrate_formats(apps, schema_editor):
    """Convert existing reports from removed formats to supported ones."""
    ExportReport = apps.get_model("reporting", "ExportReport")

    # Map old formats to new ones
    format_mapping = {
        "docx": "pdf",  # Word documents -> PDF
        "xlsx": "csv",  # Excel spreadsheets -> CSV
        "bibtex": "json",  # BibTeX -> JSON
    }

    for old_format, new_format in format_mapping.items():
        count = ExportReport.objects.filter(export_format=old_format).update(
            export_format=new_format
        )
        if count > 0:
            print(f"Migrated {count} reports from {old_format} to {new_format}")


def reverse_migrate_formats(apps, schema_editor):
    """Reverse migration - no action needed as we're removing formats."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("reporting", "0004_alter_exportreport_options_and_more"),
    ]

    operations = [
        migrations.RunPython(migrate_formats, reverse_migrate_formats),
    ]
