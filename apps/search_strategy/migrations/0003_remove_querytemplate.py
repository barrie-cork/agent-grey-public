from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("search_strategy", "0002_check_querytemplate_data"),
    ]

    operations = [
        migrations.DeleteModel(
            name="QueryTemplate",
        ),
    ]
