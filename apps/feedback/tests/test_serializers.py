"""Tests for feedback serialization and settings."""

from django.conf import settings
from django.test import TestCase

from apps.core.tests.utils import create_test_user
from apps.feedback.models import UserFeedback
from apps.feedback.serializers import serialize_feedback


class SerializeFeedbackTest(TestCase):
    """Test the shared serialize_feedback function."""

    def setUp(self):
        self.user = create_test_user()
        self.feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/search/results/",
            feedback_type="bug",
            subject="Test Subject",
            message="Test message.",
            severity="must_have",
            expected_behaviour="Should work",
            actual_behaviour="Crashes",
            frequency="always",
            contact_email="test@example.com",
            status="new",
        )

    def test_all_expected_fields_present(self):
        """All MFS-compatible fields should be in the output."""
        result = serialize_feedback(self.feedback)
        expected_keys = {
            "_id",
            "type",
            "message",
            "subject",
            "severity",
            "screen",
            "screenCategory",
            "interactionContext",
            "expectedBehavior",
            "actualBehavior",
            "frequency",
            "contactEmail",
            "transcription",
            "audioDurationMs",
            "audioStorageId",
            "screenshotUrl",
            "lastError",
            "deviceInfo",
            "createdAt",
            "user",
            "userRole",
            "linkedIssueNumber",
            "linkedIssueUrl",
            "linkedIssueState",
            "teamDecision",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_camel_case_field_names(self):
        """All multi-word fields should use camelCase, not snake_case."""
        result = serialize_feedback(self.feedback)
        for key in result.keys():
            self.assertNotIn(
                "_",
                key.lstrip("_"),  # allow leading underscore (_id)
                f"Field '{key}' uses snake_case instead of camelCase",
            )

    def test_created_at_is_milliseconds(self):
        """createdAt should be an integer (milliseconds since epoch)."""
        result = serialize_feedback(self.feedback)
        self.assertIsInstance(result["createdAt"], int)
        # Should be a reasonable timestamp (> 2020 in ms)
        self.assertGreater(result["createdAt"], 1577836800000)

    def test_serialize_used_by_view_and_command(self):
        """Both FeedbackExportView and export_feedback command use serialize_feedback."""
        import inspect
        from apps.feedback.views import FeedbackExportView
        from apps.feedback.management.commands.export_feedback import Command

        view_source = inspect.getsource(FeedbackExportView.get)
        command_source = inspect.getsource(Command.handle)

        self.assertIn("serialize_feedback", view_source)
        self.assertIn("serialize_feedback", command_source)


class FeedbackSettingsTest(TestCase):
    """Test that required settings are configured."""

    def test_groq_api_key_setting_exists(self):
        """GROQ_API_KEY setting should exist (may be empty in test)."""
        self.assertTrue(hasattr(settings, "GROQ_API_KEY"))

    def test_data_upload_max_memory_size(self):
        """DATA_UPLOAD_MAX_MEMORY_SIZE should be 10MB."""
        self.assertEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 10 * 1024 * 1024)

    def test_file_upload_max_memory_size(self):
        """FILE_UPLOAD_MAX_MEMORY_SIZE should be 5MB."""
        self.assertEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 5 * 1024 * 1024)
