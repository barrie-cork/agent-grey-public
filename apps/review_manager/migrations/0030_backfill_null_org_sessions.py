"""Backfill NULL organisation on SearchSession records.

A handful of sessions were created before the organisation foreign key was
enforced. This migration sets ``session.organisation`` to the session owner's
personal organisation (auto-created on signup) so that downstream code can
safely rely on ``session.organisation`` being non-NULL.
"""

from django.db import migrations


def backfill_null_org(apps, schema_editor):
    SearchSession = apps.get_model("review_manager", "SearchSession")
    Organisation = apps.get_model("organisation", "Organisation")

    null_org_sessions = SearchSession.objects.filter(organisation__isnull=True)
    for session in null_org_sessions:
        # Pick the first org the owner belongs to (auto-created personal org
        # from the create_personal_organisation signal in accounts/signals.py).
        owner_org = Organisation.objects.filter(
            memberships__user=session.owner,
        ).first()
        if owner_org:
            session.organisation = owner_org
            session.save(update_fields=["organisation"])


def reverse_backfill(apps, schema_editor):
    # Intentionally a no-op -- we don't want to null out organisations
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("review_manager", "0029_alter_sessionactivity_activity_type"),
        ("organisation", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_null_org, reverse_backfill),
    ]
