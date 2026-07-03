"""Tests for feedback management commands."""

import json

from django.test import TestCase
from django.core.management import call_command

from io import StringIO

from apps.core.tests.utils import create_test_user
from apps.feedback.models import UserFeedback


class ExportFeedbackCommandTest(TestCase):
    """Test export_feedback management command."""

    def setUp(self):
        self.user = create_test_user()
        self.fb1 = UserFeedback.objects.create(
            user=self.user,
            page_path="/test/",
            feedback_type="bug",
            subject="Bug one",
            message="First bug report.",
            status="new",
            severity="must_have",
        )
        self.fb2 = UserFeedback.objects.create(
            page_path="/page2/",
            feedback_type="idea",
            message="An idea.",
            status="resolved",
        )

    def test_export_default_new_status(self):
        """Export defaults to status=new."""
        out = StringIO()
        call_command("export_feedback", stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "bug")

    def test_export_all_status(self):
        """Export with --status all returns everything."""
        out = StringIO()
        call_command("export_feedback", "--status", "all", stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(len(data), 2)

    def test_export_with_limit(self):
        """Export with --limit restricts results."""
        out = StringIO()
        call_command("export_feedback", "--status", "all", "--limit", "1", stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(len(data), 1)

    def test_export_has_issue(self):
        """Export with --has-issue filters to linked items."""
        self.fb1.github_issue_number = 10
        self.fb1.save()

        out = StringIO()
        call_command("export_feedback", "--status", "all", "--has-issue", stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["linkedIssueNumber"], 10)

    def test_export_json_format(self):
        """Export JSON uses MFS-compatible field names."""
        out = StringIO()
        call_command("export_feedback", stdout=out)
        data = json.loads(out.getvalue())
        item = data[0]
        self.assertIn("_id", item)
        self.assertIn("screenCategory", item)
        self.assertIn("interactionContext", item)
        self.assertIn("expectedBehavior", item)
        self.assertIn("deviceInfo", item)
        self.assertIn("createdAt", item)

    def test_export_since_filter(self):
        """Export with --since filters by date."""
        # fb1 is recent (created_at = now), so a future --since should exclude it
        out = StringIO()
        call_command(
            "export_feedback",
            "--status",
            "all",
            "--since",
            "2099-01-01T00:00:00",
            stdout=out,
        )
        data = json.loads(out.getvalue())
        self.assertEqual(len(data), 0)

        # Using a past date should include everything
        out = StringIO()
        call_command(
            "export_feedback",
            "--status",
            "all",
            "--since",
            "2020-01-01T00:00:00",
            stdout=out,
        )
        data = json.loads(out.getvalue())
        self.assertEqual(len(data), 2)

    def test_export_shares_serializer_with_view(self):
        """Export command uses the same serialize_feedback as FeedbackExportView."""
        from apps.feedback.serializers import serialize_feedback
        from apps.feedback.management.commands.export_feedback import Command

        # Verify the command imports and uses serialize_feedback
        import inspect

        source = inspect.getsource(Command.handle)
        self.assertIn("serialize_feedback", source)

        # Verify output matches direct serializer call
        out = StringIO()
        call_command("export_feedback", stdout=out)
        command_data = json.loads(out.getvalue())

        direct_data = serialize_feedback(self.fb1)
        self.assertEqual(command_data[0]["_id"], direct_data["_id"])
        self.assertEqual(set(command_data[0].keys()), set(direct_data.keys()))


class MarkFeedbackProcessedCommandTest(TestCase):
    """Test mark_feedback_processed management command."""

    def setUp(self):
        self.fb = UserFeedback.objects.create(
            page_path="/test/",
            feedback_type="bug",
            message="Bug to process.",
            status="new",
        )

    def test_mark_processed(self):
        """Mark feedback as processed with issue link."""
        out = StringIO()
        call_command(
            "mark_feedback_processed",
            "--ids",
            str(self.fb.id),
            "--issue-url",
            "https://github.com/org/repo/issues/42",
            stdout=out,
        )
        result = json.loads(out.getvalue())
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["failed"], 0)

        self.fb.refresh_from_db()
        self.assertEqual(self.fb.status, "resolved")
        self.assertEqual(self.fb.github_issue_number, 42)
        self.assertEqual(self.fb.github_issue_state, "open")
        self.assertEqual(self.fb.team_decision, "accepted")

    def test_mark_processed_explicit_issue_number(self):
        """Explicit --issue-number overrides URL parsing."""
        out = StringIO()
        call_command(
            "mark_feedback_processed",
            "--ids",
            str(self.fb.id),
            "--issue-url",
            "https://github.com/org/repo/issues/42",
            "--issue-number",
            "99",
            stdout=out,
        )
        self.fb.refresh_from_db()
        self.assertEqual(self.fb.github_issue_number, 99)

    def test_mark_processed_sets_team_decision_at(self):
        """Mark processed sets team_decision_at timestamp."""
        out = StringIO()
        call_command(
            "mark_feedback_processed",
            "--ids",
            str(self.fb.id),
            "--issue-url",
            "https://github.com/org/repo/issues/10",
            stdout=out,
        )
        self.fb.refresh_from_db()
        self.assertIsNotNone(self.fb.team_decision_at)

    def test_mark_processed_multiple_ids(self):
        """Mark multiple feedback records as processed."""
        fb2 = UserFeedback.objects.create(
            page_path="/page2/",
            feedback_type="idea",
            message="Another bug.",
            status="new",
        )

        out = StringIO()
        call_command(
            "mark_feedback_processed",
            "--ids",
            str(self.fb.id),
            str(fb2.id),
            "--issue-url",
            "https://github.com/org/repo/issues/50",
            stdout=out,
        )
        result = json.loads(out.getvalue())
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["failed"], 0)

        self.fb.refresh_from_db()
        fb2.refresh_from_db()
        self.assertEqual(self.fb.status, "resolved")
        self.assertEqual(fb2.status, "resolved")

    def test_mark_processed_nonexistent_id(self):
        """Non-existent IDs counted as failed."""
        out = StringIO()
        call_command(
            "mark_feedback_processed",
            "--ids",
            "00000000-0000-0000-0000-000000000000",
            "--issue-url",
            "https://github.com/org/repo/issues/1",
            stdout=out,
        )
        result = json.loads(out.getvalue())
        self.assertEqual(result["processed"], 0)
        self.assertEqual(result["failed"], 1)


class UpdateIssueStatusCommandTest(TestCase):
    """Test update_issue_status management command."""

    def setUp(self):
        self.fb = UserFeedback.objects.create(
            page_path="/test/",
            feedback_type="bug",
            message="Linked bug.",
            status="resolved",
            github_issue_number=42,
            github_issue_state="open",
            team_decision="accepted",
        )

    def test_close_issue(self):
        """Closing an issue updates state and team_decision."""
        out = StringIO()
        call_command(
            "update_issue_status",
            "--issue-number",
            "42",
            "--state",
            "closed",
            "--resolution",
            "completed",
            stdout=out,
        )
        result = json.loads(out.getvalue())
        self.assertEqual(result["updated"], 1)

        self.fb.refresh_from_db()
        self.assertEqual(self.fb.github_issue_state, "closed")
        self.assertEqual(self.fb.team_decision, "completed")
        self.assertEqual(self.fb.github_issue_resolution, "completed")

    def test_reopen_issue(self):
        """Reopening an issue sets team_decision back to accepted."""
        self.fb.github_issue_state = "closed"
        self.fb.team_decision = "completed"
        self.fb.save()

        out = StringIO()
        call_command(
            "update_issue_status",
            "--issue-number",
            "42",
            "--state",
            "open",
            stdout=out,
        )
        result = json.loads(out.getvalue())
        self.assertEqual(result["updated"], 1)

        self.fb.refresh_from_db()
        self.assertEqual(self.fb.github_issue_state, "open")
        self.assertEqual(self.fb.team_decision, "accepted")

    def test_close_with_closed_at(self):
        """Closing with --closed-at saves the timestamp."""
        out = StringIO()
        call_command(
            "update_issue_status",
            "--issue-number",
            "42",
            "--state",
            "closed",
            "--closed-at",
            "2026-03-15T10:00:00+00:00",
            stdout=out,
        )
        self.fb.refresh_from_db()
        self.assertIsNotNone(self.fb.github_issue_closed_at)

    def test_no_matching_issue(self):
        """Non-existent issue number results in 0 updates."""
        out = StringIO()
        call_command(
            "update_issue_status",
            "--issue-number",
            "999",
            "--state",
            "closed",
            stdout=out,
        )
        result = json.loads(out.getvalue())
        self.assertEqual(result["updated"], 0)
