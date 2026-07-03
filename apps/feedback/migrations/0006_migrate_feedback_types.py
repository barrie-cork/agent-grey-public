"""
Data migration to map old feedback_type values to new ones.

Mappings:
- improvement -> suggestion
- compliment -> general
- other -> general
"""

from django.db import migrations


def migrate_feedback_types(apps, schema_editor):
    UserFeedback = apps.get_model("feedback", "UserFeedback")
    UserFeedback.objects.filter(feedback_type="improvement").update(
        feedback_type="suggestion"
    )
    UserFeedback.objects.filter(feedback_type__in=["compliment", "other"]).update(
        feedback_type="general"
    )


def reverse_feedback_types(apps, schema_editor):
    UserFeedback = apps.get_model("feedback", "UserFeedback")
    # Best-effort reverse: general -> other, but we can't distinguish
    # which were originally compliment vs other
    UserFeedback.objects.filter(feedback_type="general").update(feedback_type="other")


class Migration(migrations.Migration):
    dependencies = [
        ("feedback", "0005_userfeedback_actual_behaviour_and_more"),
    ]

    operations = [
        migrations.RunPython(
            migrate_feedback_types,
            reverse_feedback_types,
        ),
    ]
