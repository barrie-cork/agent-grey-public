"""
Tests for feedback views.
"""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from ..models import UserFeedback
from apps.core.tests.utils import create_test_user

User = get_user_model()


class FeedbackSubmissionViewTest(TestCase):
    """Test feedback submission view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.submission_url = reverse("feedback:submit")

    def test_submit_feedback_authenticated_user(self):
        """Test feedback submission by authenticated user."""
        self.client.login(username=self.user.username, password="testpass123")

        data = {
            "feedback_type": "bug",
            "subject": "Test Bug Report",
            "message": "This is a detailed test bug report with sufficient length to pass validation requirements.",
            "rating": "2",
            "page_path": "/test-page/",
            "page_title": "Test Page",
        }

        response = self.client.post(
            self.submission_url, data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data["success"])
        self.assertIn("Thank you", response_data["message"])

        # Check feedback was created
        feedback = UserFeedback.objects.get()
        self.assertEqual(feedback.user, self.user)
        self.assertEqual(feedback.feedback_type, "bug")
        self.assertEqual(feedback.subject, "Test Bug Report")

    def test_submit_feedback_anonymous_user(self):
        """Test feedback submission by anonymous user."""
        data = {
            "feedback_type": "suggestion",
            "subject": "Anonymous Suggestion",
            "message": "This is an anonymous suggestion with sufficient length to pass validation requirements.",
            "email": "anonymous@example.com",
            "page_path": "/test-page/",
            "page_title": "Test Page",
        }

        response = self.client.post(
            self.submission_url, data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data["success"])

        # Check feedback was created
        feedback = UserFeedback.objects.get()
        self.assertIsNone(feedback.user)
        self.assertEqual(feedback.email, "anonymous@example.com")
        self.assertEqual(feedback.feedback_type, "suggestion")

    def test_submit_feedback_validation_error(self):
        """Test feedback submission with validation errors."""
        data = {
            "feedback_type": "",  # Required field
            "message": "Short",  # Too short
            "page_path": "/test-page/",
            "page_title": "Test Page",
        }

        response = self.client.post(
            self.submission_url, data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertFalse(response_data["success"])
        self.assertIn("errors", response_data)

        # No feedback should be created
        self.assertEqual(UserFeedback.objects.count(), 0)

    def test_submit_feedback_invalid_json(self):
        """Test feedback submission with invalid JSON."""
        response = self.client.post(
            self.submission_url, data="invalid json", content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertFalse(response_data["success"])
        self.assertIn("Invalid JSON", response_data["message"])

    def test_submit_feedback_form_data(self):
        """Test feedback submission using form data instead of JSON."""
        data = {
            "feedback_type": "general",
            "message": "This is general feedback with sufficient length to pass validation requirements.",
            "page_path": "/test-page/",
            "page_title": "Test Page",
        }

        response = self.client.post(self.submission_url, data)

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data["success"])

        # Check feedback was created
        feedback = UserFeedback.objects.get()
        self.assertEqual(feedback.feedback_type, "general")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.feedback.tasks.transcribe_feedback_audio.delay")
    def test_submit_feedback_with_audio_file(self, mock_transcribe):
        """Test feedback submission with audio file upload."""
        audio_content = b"\x00" * 1024  # 1KB dummy audio
        audio_file = SimpleUploadedFile(
            "recording.webm", audio_content, content_type="audio/webm"
        )

        data = {
            "feedback_type": "bug",
            "message": "This is a detailed test bug report with sufficient length to pass validation requirements.",
            "page_path": "/test-page/",
            "page_title": "Test Page",
            "audio_duration_ms": "5000",
            "severity": "must_have",
        }

        response = self.client.post(
            self.submission_url, data={**data, "audio_file": audio_file}
        )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data["success"])

        feedback = UserFeedback.objects.get()
        self.assertTrue(feedback.audio_file)
        self.assertEqual(feedback.audio_duration_ms, 5000)
        self.assertEqual(feedback.severity, "must_have")

        # Transcription task should be triggered
        mock_transcribe.assert_called_once_with(str(feedback.id))

    @patch("apps.feedback.tasks.transcribe_feedback_audio.delay")
    def test_submit_feedback_with_screenshot(self, mock_transcribe):
        """Test feedback submission with screenshot upload."""
        # 1x1 red PNG
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        screenshot = SimpleUploadedFile(
            "screenshot.png", png_data, content_type="image/png"
        )

        data = {
            "feedback_type": "bug",
            "message": "This is a detailed test bug report with sufficient length to pass validation requirements.",
            "page_path": "/test-page/",
            "page_title": "Test Page",
        }

        response = self.client.post(
            self.submission_url, data={**data, "screenshot": screenshot}
        )

        self.assertEqual(response.status_code, 200)
        feedback = UserFeedback.objects.get()
        self.assertTrue(feedback.screenshot)

        # No audio = no transcription task
        mock_transcribe.assert_not_called()

    def test_submit_feedback_audio_too_large(self):
        """Test that audio files larger than 5MB are rejected."""
        large_audio = SimpleUploadedFile(
            "large.webm",
            b"\x00" * (5 * 1024 * 1024 + 1),
            content_type="audio/webm",
        )

        data = {
            "feedback_type": "bug",
            "message": "This is a detailed test bug report with sufficient length to pass validation requirements.",
            "page_path": "/test-page/",
            "page_title": "Test Page",
        }

        response = self.client.post(
            self.submission_url, data={**data, "audio_file": large_audio}
        )

        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn("Audio file too large", response_data["message"])

    def test_submit_feedback_screenshot_too_large(self):
        """Test that screenshots larger than 2MB are rejected."""
        large_screenshot = SimpleUploadedFile(
            "large.png",
            b"\x00" * (2 * 1024 * 1024 + 1),
            content_type="image/png",
        )

        data = {
            "feedback_type": "bug",
            "message": "This is a detailed test bug report with sufficient length to pass validation requirements.",
            "page_path": "/test-page/",
            "page_title": "Test Page",
        }

        response = self.client.post(
            self.submission_url, data={**data, "screenshot": large_screenshot}
        )

        self.assertEqual(response.status_code, 400)
        response_data = response.json()
        self.assertIn("Screenshot too large", response_data["message"])

    def test_submit_feedback_with_interaction_context_string(self):
        """Test that interaction_context JSON string is parsed correctly."""
        context_data = {"pages_visited": ["/page1", "/page2"], "js_errors": []}
        data = {
            "feedback_type": "bug",
            "message": "This is a detailed test bug report with sufficient length to pass validation requirements.",
            "page_path": "/test-page/",
            "page_title": "Test Page",
            "interaction_context": json.dumps(context_data),
        }

        response = self.client.post(self.submission_url, data=data)

        self.assertEqual(response.status_code, 200)
        feedback = UserFeedback.objects.get()
        self.assertEqual(feedback.interaction_context, context_data)

    def test_submit_feedback_new_fields_saved(self):
        """Test that all enhanced fields are saved from FormData."""
        data = {
            "feedback_type": "bug",
            "message": "This is a detailed test bug report with sufficient length to pass validation requirements.",
            "page_path": "/test-page/",
            "page_title": "Test Page",
            "severity": "should_have",
            "expected_behaviour": "It should work",
            "actual_behaviour": "It crashes",
            "frequency": "always",
            "contact_email": "user@example.com",
        }

        response = self.client.post(self.submission_url, data=data)

        self.assertEqual(response.status_code, 200)
        feedback = UserFeedback.objects.get()
        self.assertEqual(feedback.severity, "should_have")
        self.assertEqual(feedback.expected_behaviour, "It should work")
        self.assertEqual(feedback.actual_behaviour, "It crashes")
        self.assertEqual(feedback.frequency, "always")
        self.assertEqual(feedback.contact_email, "user@example.com")


class FeedbackExportViewTest(TestCase):
    """Test feedback export view."""

    def setUp(self):
        self.client = Client()
        self.staff_user = create_test_user(username_prefix="staffuser", is_staff=True)
        self.regular_user = create_test_user(username_prefix="regular")
        self.export_url = reverse("feedback:feedback_export")

        # Create test feedback
        self.feedback = UserFeedback.objects.create(
            user=self.regular_user,
            page_path="/test-page/",
            feedback_type="bug",
            subject="Test Bug",
            message="Test bug report with sufficient length to pass validation.",
            severity="must_have",
            status="new",
        )

    def test_export_staff_access(self):
        """Test that staff users can access export."""
        self.client.login(username=self.staff_user.username, password="testpass123")
        response = self.client.get(self.export_url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["_id"], str(self.feedback.id))
        self.assertEqual(data[0]["type"], "bug")
        self.assertEqual(data[0]["severity"], "must_have")

    def test_export_non_staff_denied(self):
        """Test that non-staff users cannot export."""
        self.client.login(username=self.regular_user.username, password="testpass123")
        response = self.client.get(self.export_url)
        self.assertIn(response.status_code, [302, 403])

    def test_export_status_filter(self):
        """Test export with status filter."""
        self.client.login(username=self.staff_user.username, password="testpass123")

        response = self.client.get(self.export_url + "?status=resolved")
        data = response.json()
        self.assertEqual(len(data), 0)

        response = self.client.get(self.export_url + "?status=new")
        data = response.json()
        self.assertEqual(len(data), 1)

    def test_export_all_status(self):
        """Test export with status=all."""
        UserFeedback.objects.create(
            page_path="/page2/",
            feedback_type="idea",
            message="Resolved feedback.",
            status="resolved",
        )
        self.client.login(username=self.staff_user.username, password="testpass123")

        response = self.client.get(self.export_url + "?status=all")
        data = response.json()
        self.assertEqual(len(data), 2)

    def test_export_limit(self):
        """Test export with limit."""
        UserFeedback.objects.create(
            page_path="/page2/",
            feedback_type="idea",
            message="Another feedback item.",
            status="new",
        )
        self.client.login(username=self.staff_user.username, password="testpass123")

        response = self.client.get(self.export_url + "?status=all&limit=1")
        data = response.json()
        self.assertEqual(len(data), 1)

    def test_export_has_issue_filter(self):
        """Test export with has_issue filter."""
        self.feedback.github_issue_number = 42
        self.feedback.save()

        self.client.login(username=self.staff_user.username, password="testpass123")

        response = self.client.get(self.export_url + "?has_issue=1")
        data = response.json()
        self.assertEqual(len(data), 1)

    def test_export_json_field_names(self):
        """Test that export JSON uses MFS-compatible field names."""
        self.client.login(username=self.staff_user.username, password="testpass123")
        response = self.client.get(self.export_url)
        data = response.json()
        item = data[0]

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
        self.assertEqual(set(item.keys()), expected_keys)

    def test_export_screenshot_url_absolute(self):
        """Test that screenshotUrl is absolute when screenshot exists."""
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        self.feedback.screenshot = SimpleUploadedFile(
            "shot.png", png_data, content_type="image/png"
        )
        self.feedback.save()

        self.client.login(username=self.staff_user.username, password="testpass123")
        response = self.client.get(self.export_url)
        data = response.json()
        url = data[0]["screenshotUrl"]
        self.assertIsNotNone(url)
        self.assertTrue(url.startswith("http"), f"Expected absolute URL, got: {url}")


class QuickFeedbackViewTest(TestCase):
    """Test quick feedback view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.quick_url = reverse("feedback:quick_submit")

    def test_quick_feedback_submission(self):
        """Test quick feedback submission."""
        data = {
            "feedback_type": "helpful",
            "rating": "5",
            "additional_comment": "This page was very helpful!",
            "page_path": "/helpful-page/",
            "page_title": "Helpful Page",
        }

        response = self.client.post(
            self.quick_url, data=json.dumps(data), content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertTrue(response_data["success"])

        # Check feedback was created
        feedback = UserFeedback.objects.get()
        self.assertEqual(feedback.feedback_type, "general")  # mapped from 'helpful'
        self.assertEqual(feedback.rating, 5)
        self.assertIn("This page was helpful", feedback.message)
        self.assertIn("This page was very helpful!", feedback.message)


class FeedbackListViewTest(TestCase):
    """Test feedback list view for staff users."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = create_test_user()
        self.staff_user = create_test_user(username_prefix="staffuser", is_staff=True)
        self.list_url = reverse("feedback:list")

        # Create test feedback
        UserFeedback.objects.create(
            user=self.user,
            page_path="/test-page/",
            feedback_type="bug",
            message="Test bug report with sufficient length to pass validation requirements.",
        )

    def test_feedback_list_staff_access(self):
        """Test that staff users can access feedback list."""
        self.client.login(username=self.staff_user.username, password="testpass123")

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
        self.assertContains(response, "Bug Report")

    def test_feedback_list_non_staff_denied(self):
        """Test that non-staff users cannot access feedback list."""
        self.client.login(username=self.user.username, password="testpass123")

        response = self.client.get(self.list_url)

        # Should redirect to login or return 403
        self.assertIn(response.status_code, [302, 403])

    def test_feedback_list_anonymous_denied(self):
        """Test that anonymous users cannot access feedback list."""
        response = self.client.get(self.list_url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)


class FeedbackStatsViewTest(TestCase):
    """Test feedback statistics view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.staff_user = create_test_user(username_prefix="staffuser", is_staff=True)
        self.stats_url = reverse("feedback:stats_api")

        # Create test feedback
        UserFeedback.objects.create(
            page_path="/test-page/",
            feedback_type="bug",
            message="Test bug report with sufficient length to pass validation requirements.",
        )
        UserFeedback.objects.create(
            page_path="/test-page/",
            feedback_type="suggestion",
            message="Test suggestion with sufficient length to pass validation requirements.",
        )

    def test_feedback_stats_staff_access(self):
        """Test that staff users can access statistics."""
        self.client.login(username=self.staff_user.username, password="testpass123")

        response = self.client.get(self.stats_url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("data", data)
        self.assertEqual(data["data"]["total_feedback"], 2)

    def test_feedback_stats_non_staff_denied(self):
        """Test that non-staff users cannot access statistics."""
        regular_user = create_test_user()
        self.client.login(username=regular_user.username, password="testpass123")

        response = self.client.get(self.stats_url)

        # Should redirect to login or return 403
        self.assertIn(response.status_code, [302, 403])
