"""Shared services for feedback processing."""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def transcribe_audio_with_groq(audio_data: bytes, filename: str) -> str:
    """Transcribe audio using Groq Whisper API.

    Args:
        audio_data: Raw audio bytes.
        filename: Original filename (used for MIME type hint).

    Returns:
        Transcribed text string.

    Raises:
        ValueError: If GROQ_API_KEY is not configured.
        requests.RequestException: On network/API errors.
        RuntimeError: If the Groq API returns an error response.
    """
    groq_api_key = getattr(settings, "GROQ_API_KEY", "")
    if not groq_api_key:
        raise ValueError("GROQ_API_KEY not configured")

    response = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {groq_api_key}"},
        files={"file": (filename, audio_data, "audio/webm")},
        data={"model": "whisper-large-v3-turbo"},
        timeout=30,
    )

    if not response.ok:
        error_detail = response.text[:200]
        raise RuntimeError(f"Groq API error {response.status_code}: {error_detail}")

    result = response.json()
    return result.get("text", "")
