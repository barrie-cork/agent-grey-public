"""Update feedback records with GitHub issue status changes."""

import json

from django.core.management.base import BaseCommand

from apps.feedback.models import UserFeedback


class Command(BaseCommand):
    help = "Update feedback records with GitHub issue status changes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--issue-number", type=int, required=True, help="GitHub issue number"
        )
        parser.add_argument(
            "--state", required=True, choices=["open", "closed"], help="Issue state"
        )
        parser.add_argument("--resolution", default="", help="Issue resolution label")
        parser.add_argument(
            "--closed-at", default="", help="ISO datetime when issue was closed"
        )
        parser.add_argument(
            "--commit-sha", default="", help="Commit SHA that resolved the issue"
        )
        parser.add_argument("--commit-url", default="", help="Commit URL")

    def handle(self, *args, **options):
        qs = UserFeedback.objects.filter(github_issue_number=options["issue_number"])

        update_fields = {
            "github_issue_state": options["state"],
        }

        if options["state"] == "closed":
            update_fields["team_decision"] = "completed"
            if options["resolution"]:
                update_fields["github_issue_resolution"] = options["resolution"]
            if options["closed_at"]:
                from django.utils.dateparse import parse_datetime

                closed_dt = parse_datetime(options["closed_at"])
                if closed_dt:
                    update_fields["github_issue_closed_at"] = closed_dt
        elif options["state"] == "open":
            update_fields["team_decision"] = "accepted"

        updated = qs.update(**update_fields)
        self.stdout.write(
            json.dumps({"updated": updated, "issue_number": options["issue_number"]})
        )
