"""Make ReviewerCompletion.invitation nullable for session owners.

Session owners participate in dual-screening but don't have invitations.
This migration allows ReviewerCompletion records with invitation=None.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("review_results", "0012_conflictaccesslog"),
    ]

    operations = [
        # Step 1: Make invitation nullable
        migrations.AlterField(
            model_name="reviewercompletion",
            name="invitation",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="completion_status",
                to="review_manager.reviewinvitation",
                help_text="The invitation that led to this completion tracking. Null for session owners.",
            ),
        ),
        # Step 2: Remove old unique_together constraint on invitation
        migrations.AlterUniqueTogether(
            name="reviewercompletion",
            unique_together=set(),
        ),
        # Step 3: Add new unique constraint on (session, reviewer)
        migrations.AddConstraint(
            model_name="reviewercompletion",
            constraint=models.UniqueConstraint(
                fields=["session", "reviewer"],
                name="unique_session_reviewer_completion",
            ),
        ),
    ]
