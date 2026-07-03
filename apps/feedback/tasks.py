"""Celery tasks for feedback processing."""

import logging

import requests
from celery import shared_task
from django.utils import timezone

from apps.feedback.services import transcribe_audio_with_groq

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def transcribe_feedback_audio(self, feedback_id: str) -> None:
    """Transcribe voice feedback audio using Groq Whisper API."""
    from apps.feedback.models import UserFeedback

    try:
        feedback = UserFeedback.objects.get(id=feedback_id)
    except UserFeedback.DoesNotExist:
        logger.error("Feedback %s not found for transcription", feedback_id)
        return

    if not feedback.audio_file:
        logger.warning("Feedback %s has no audio file", feedback_id)
        return

    if feedback.transcription:
        logger.info("Feedback %s already transcribed, skipping", feedback_id)
        return

    try:
        feedback.audio_file.seek(0)
        audio_data = feedback.audio_file.read()
        filename = (
            feedback.audio_file.name.split("/")[-1]
            if feedback.audio_file.name
            else "recording.webm"
        )

        transcription = transcribe_audio_with_groq(audio_data, filename)
        feedback.transcription = transcription
        feedback.voice_metadata = {
            "transcription_service": "groq",
            "transcription_model": "whisper-large-v3-turbo",
            "transcription_confidence": 0.95,
            "transcribed_at": timezone.now().isoformat(),
        }
        update_fields = ["transcription", "voice_metadata"]
        # If message is empty, pre-fill with transcription
        if not feedback.message.strip():
            feedback.message = feedback.transcription
            update_fields.append("message")
        feedback.save(update_fields=update_fields)
        logger.info(
            "Transcribed feedback %s: %d chars",
            feedback_id,
            len(feedback.transcription),
        )

    except ValueError:
        logger.warning(
            "GROQ_API_KEY not configured, cannot transcribe feedback %s", feedback_id
        )
        feedback.voice_metadata = {
            "transcription_service": "groq",
            "error": "GROQ_API_KEY not configured",
            "attempted_at": timezone.now().isoformat(),
        }
        feedback.save(update_fields=["voice_metadata"])

    except RuntimeError as e:
        error_msg = str(e)
        logger.error("Groq API error for feedback %s: %s", feedback_id, error_msg)
        feedback.voice_metadata = {
            "transcription_service": "groq",
            "error": error_msg,
            "attempted_at": timezone.now().isoformat(),
        }
        feedback.save(update_fields=["voice_metadata"])
        if "429" in error_msg:
            raise self.retry(exc=e)

    except requests.RequestException as e:
        logger.error("Groq API request failed: %s", e)
        raise self.retry(exc=e)
