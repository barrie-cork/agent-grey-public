"""Create ReviewerCompletion records for session owners in existing Workflow #2 sessions.

This data migration backfills completion records for session owners who should
be able to participate in dual-screening but didn't have records created
(because the signal was added after their sessions were created).
"""

from django.db import migrations


def create_owner_completions(apps, schema_editor):
    """Create ReviewerCompletion records for session owners in existing Workflow #2 sessions."""
    SearchSession = apps.get_model("review_manager", "SearchSession")
    ReviewConfiguration = apps.get_model("review_manager", "ReviewConfiguration")
    ReviewerCompletion = apps.get_model("review_results", "ReviewerCompletion")

    # Find sessions in review states - use values() to avoid loading full model
    review_states = ["ready_for_review", "under_review", "completed"]
    sessions_data = SearchSession.objects.filter(status__in=review_states).values(
        "id", "owner_id", "total_results"
    )

    created_count = 0
    for session_data in sessions_data:
        session_id = session_data["id"]
        owner_id = session_data["owner_id"]
        total_results = session_data["total_results"]

        # Check if Workflow #2 (min_reviewers_per_result >= 2)
        config = ReviewConfiguration.objects.filter(session_id=session_id).first()
        if not config or config.min_reviewers_per_result < 2:
            continue

        # Check if owner already has completion record
        if ReviewerCompletion.objects.filter(
            session_id=session_id, reviewer_id=owner_id
        ).exists():
            continue

        # Create completion record for owner
        ReviewerCompletion.objects.create(
            invitation=None,
            session_id=session_id,
            reviewer_id=owner_id,
            total_results=total_results,
            reviewed_results=0,
        )
        created_count += 1

    if created_count > 0:
        print(f"Created {created_count} owner completion records for existing sessions")


def reverse_owner_completions(apps, schema_editor):
    """Remove owner completion records (invitation=None)."""
    ReviewerCompletion = apps.get_model("review_results", "ReviewerCompletion")
    deleted_count, _ = ReviewerCompletion.objects.filter(
        invitation__isnull=True
    ).delete()
    if deleted_count > 0:
        print(f"Removed {deleted_count} owner completion records")


class Migration(migrations.Migration):
    dependencies = [
        ("review_results", "0013_reviewercompletion_nullable_invitation"),
    ]

    operations = [
        migrations.RunPython(create_owner_completions, reverse_owner_completions),
    ]
