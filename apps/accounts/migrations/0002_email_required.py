"""Make email field required on User model.

Since all existing users already have email addresses, this migration
simply changes the field from nullable to required (blank=False).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(blank=False, max_length=254, unique=True),
        ),
    ]
