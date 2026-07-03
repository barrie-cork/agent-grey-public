"""Mark feedback as processed and link to GitHub issue."""

import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.feedback.models import UserFeedback


class Command(BaseCommand):
    help = "Mark feedback as processed and link to GitHub issue"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ids",
            nargs="+",
            required=True,
            help="Feedback UUIDs to mark as processed",
        )
        parser.add_argument("--issue-url", required=True, help="GitHub issue URL")
        parser.add_argument(
            "--issue-number",
            type=int,
            default=0,
            help="GitHub issue number (auto-detected from URL if omitted)",
        )

    def handle(self, *args, **options):
        ids = options["ids"]
        issue_url = options["issue_url"]
        issue_number = options["issue_number"]

        if not issue_number and "/issues/" in issue_url:
            try:
                issue_number = int(issue_url.rstrip("/").split("/")[-1])
            except (ValueError, IndexError):
                pass

        updated = UserFeedback.objects.filter(id__in=ids).update(
            status="resolved",
            github_issue_url=issue_url,
            github_issue_number=issue_number or None,
            github_issue_state="open",
            team_decision="accepted",
            team_decision_at=timezone.now(),
        )
        self.stdout.write(
            json.dumps({"processed": updated, "failed": len(ids) - updated})
        )
