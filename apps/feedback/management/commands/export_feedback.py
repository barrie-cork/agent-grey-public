"""Export feedback as JSON for clustering scripts."""

import json

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from apps.feedback.models import UserFeedback
from apps.feedback.serializers import serialize_feedback


class Command(BaseCommand):
    help = "Export feedback as JSON for clustering scripts"

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            default="new",
            help="Filter by status (default: new, use 'all' for everything)",
        )
        parser.add_argument(
            "--limit", type=int, default=0, help="Max records to return (0 = unlimited)"
        )
        parser.add_argument(
            "--has-issue",
            action="store_true",
            help="Only items linked to GitHub issues",
        )
        parser.add_argument(
            "--since",
            type=str,
            default="",
            help="ISO datetime filter (e.g. 2026-01-01T00:00:00)",
        )

    def handle(self, *args, **options):
        qs = UserFeedback.objects.select_related("user").order_by("-created_at")

        if options["status"] != "all":
            qs = qs.filter(status=options["status"])
        if options["has_issue"]:
            qs = qs.exclude(github_issue_number__isnull=True)
        if options["since"]:
            since_dt = parse_datetime(options["since"])
            if since_dt:
                qs = qs.filter(created_at__gte=since_dt)
        if options["limit"] > 0:
            qs = qs[: options["limit"]]

        output = [serialize_feedback(fb) for fb in qs]
        self.stdout.write(json.dumps(output))
