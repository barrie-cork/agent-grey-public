from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reporting", "0002_add_new_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="exportreport",
            name="file_path",
            field=models.FileField(
                upload_to="reports/%Y/%m/",
                max_length=255,
                help_text="Path to generated file",
            ),
        ),
    ]
