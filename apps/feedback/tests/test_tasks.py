"""Tests for feedback Celery tasks."""

from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.core.tests.utils import create_test_user
from apps.feedback.models import UserFeedback
from apps.feedback.tasks import transcribe_feedback_audio


class TranscribeFeedbackAudioTest(TestCase):
    """Test the transcribe_feedback_audio Celery task."""

    def setUp(self):
        self.user = create_test_user()
        audio_content = b"\x00" * 1024
        self.feedback = UserFeedback.objects.create(
            user=self.user,
            page_path="/test/",
            feedback_type="bug",
            message="Test bug with voice",
            audio_file=SimpleUploadedFile(
                "recording.webm", audio_content, content_type="audio/webm"
            ),
            audio_duration_ms=3000,
        )

    def test_nonexistent_feedback(self):
        """Task should log error and return for nonexistent feedback."""
        transcribe_feedback_audio("00000000-0000-0000-0000-000000000000")
        # Should not raise

    def test_no_audio_file(self):
        """Task should skip feedback without audio file."""
        feedback_no_audio = UserFeedback.objects.create(
            page_path="/test/",
            feedback_type="bug",
            message="No audio here",
        )
        transcribe_feedback_audio(str(feedback_no_audio.id))
        feedback_no_audio.refresh_from_db()
        self.assertEqual(feedback_no_audio.transcription, "")

    def test_already_transcribed(self):
        """Task should skip already-transcribed feedback."""
        self.feedback.transcription = "Already done"
        self.feedback.save()
        transcribe_feedback_audio(str(self.feedback.id))
        self.feedback.refresh_from_db()
        self.assertEqual(self.feedback.transcription, "Already done")

    @override_settings(GROQ_API_KEY="")
    def test_no_groq_api_key(self):
        """Task should save error metadata when GROQ_API_KEY is not configured."""
        transcribe_feedback_audio(str(self.feedback.id))
        self.feedback.refresh_from_db()
        self.assertEqual(self.feedback.transcription, "")
        self.assertIn("error", self.feedback.voice_metadata)
        self.assertEqual(
            self.feedback.voice_metadata["error"], "GROQ_API_KEY not configured"
        )

    @override_settings(GROQ_API_KEY="test-key-123")
    @patch("apps.feedback.services.requests.post")
    def test_successful_transcription(self, mock_post):
        """Task should save transcription on successful API call."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"text": "Hello, this is a test recording."}
        mock_post.return_value = mock_response

        transcribe_feedback_audio(str(self.feedback.id))

        self.feedback.refresh_from_db()
        self.assertEqual(
            self.feedback.transcription, "Hello, this is a test recording."
        )
        self.assertEqual(self.feedback.voice_metadata["transcription_service"], "groq")
        self.assertIn("transcribed_at", self.feedback.voice_metadata)

    @override_settings(GROQ_API_KEY="test-key-123")
    @patch("apps.feedback.services.requests.post")
    def test_transcription_prefills_empty_message(self, mock_post):
        """Task should prefill message if it was empty."""
        self.feedback.message = ""
        self.feedback.save()

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"text": "Voice-only feedback content."}
        mock_post.return_value = mock_response

        transcribe_feedback_audio(str(self.feedback.id))

        self.feedback.refresh_from_db()
        self.assertEqual(self.feedback.message, "Voice-only feedback content.")

    @override_settings(GROQ_API_KEY="test-key-123")
    @patch("apps.feedback.services.requests.post")
    def test_api_error_saves_metadata(self, mock_post):
        """Task should save error metadata on API failure."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        transcribe_feedback_audio(str(self.feedback.id))

        self.feedback.refresh_from_db()
        self.assertEqual(self.feedback.transcription, "")
        self.assertIn("error", self.feedback.voice_metadata)
        self.assertIn("500", self.feedback.voice_metadata["error"])

    @override_settings(GROQ_API_KEY="test-key-123")
    @patch("apps.feedback.services.requests.post")
    def test_rate_limit_triggers_retry(self, mock_post):
        """Task should retry on 429 rate limit."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 429
        mock_response.text = "Rate limited"
        mock_post.return_value = mock_response

        # The retry will raise Retry exception when max_retries exceeded
        with self.assertRaises(Exception):
            # Call directly (not via .delay) to test retry logic
            transcribe_feedback_audio(str(self.feedback.id))

    @override_settings(GROQ_API_KEY="test-key-123")
    @patch("apps.feedback.services.requests.post")
    def test_request_timeout_set(self, mock_post):
        """Task should use 30s timeout on HTTP request."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"text": "Test."}
        mock_post.return_value = mock_response

        transcribe_feedback_audio(str(self.feedback.id))

        call_kwargs = mock_post.call_args
        self.assertEqual(call_kwargs.kwargs.get("timeout"), 30)

    @override_settings(GROQ_API_KEY="test-key-123")
    @patch("apps.feedback.services.requests.post")
    def test_success_metadata_includes_model(self, mock_post):
        """Task should record service and model in voice_metadata."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {"text": "Hello."}
        mock_post.return_value = mock_response

        transcribe_feedback_audio(str(self.feedback.id))

        self.feedback.refresh_from_db()
        self.assertEqual(
            self.feedback.voice_metadata["transcription_model"],
            "whisper-large-v3-turbo",
        )
