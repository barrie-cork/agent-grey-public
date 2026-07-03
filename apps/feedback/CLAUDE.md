# Feedback App

User feedback collection and management with voice, screenshot, and issue-linking support.

## Model

- `UserFeedback` -- feedback with voice/audio, screenshot, enhanced categorisation, GitHub issue linking, triage fields
- Properties: `is_anonymous`, `is_critical`, `submitter_display`
- Methods: `mark_as_resolved`, `mark_as_dismissed`, `categorize_screen` (auto-populates `screen_category` on save)
- Choice tuples: `SEVERITY_CHOICES`, `FREQUENCY_CHOICES`, `DECISION_CHOICES` (module-level)
- `FEEDBACK_TYPES`: bug, idea, suggestion, general (changed from bug, suggestion, compliment, improvement, other)

## Views

| View | Purpose |
|------|---------|
| `FeedbackSubmissionView` | Submit feedback (POST JSON or multipart/form-data with file uploads). Skips Celery transcription when `pre_transcribed=true` |
| `TranscribeAudioView` | Synchronous audio transcription (POST, auth required, 5MB limit, 30s timeout). Returns `{"success": true, "text": "..."}` |
| `FeedbackExportView` | Export feedback as JSON for clustering scripts (GET, staff-only) |
| `QuickFeedbackView` | Lightweight inline feedback (POST) |
| `FeedbackListView` | Admin list (staff-only) |
| `FeedbackDetailView` | Admin detail (staff-only) |
| `FeedbackStatsView` | Feedback statistics (staff-only) |
| `update_feedback_status` | Status update function |

### File Upload Limits
- Audio: 5MB max (`MAX_AUDIO_SIZE`)
- Screenshot: 2MB max (`MAX_SCREENSHOT_SIZE`)
- Django setting: `DATA_UPLOAD_MAX_MEMORY_SIZE = 10MB`, `FILE_UPLOAD_MAX_MEMORY_SIZE = 5MB`

## Services

- `transcribe_audio_with_groq(audio_data, filename)` -- shared Groq Whisper API helper (`services.py`). Used by both `TranscribeAudioView` (synchronous) and `transcribe_feedback_audio` Celery task. Raises `ValueError` (no API key), `RuntimeError` (API error), or `RequestException` (network).

## Celery Tasks

- `transcribe_feedback_audio(feedback_id)` -- Groq Whisper transcription (max_retries=2, retry_delay=10s, timeout=30s). Delegates to `transcribe_audio_with_groq`. Skipped when JS client sets `pre_transcribed=true`.

## Management Commands

| Command | Arguments | Purpose |
|---------|-----------|---------|
| `export_feedback` | `--status` (default: new), `--limit`, `--has-issue`, `--since` | Export JSON for clustering scripts |
| `mark_feedback_processed` | `--ids` (UUIDs), `--issue-url`, `--issue-number` | Link feedback to GitHub issue |
| `update_issue_status` | `--issue-number`, `--state` (open/closed), `--resolution`, `--closed-at` | Sync GitHub issue state |

## Serialization

`serializers.py` contains `serialize_feedback(fb, request=None)` -- shared between `FeedbackExportView` and `export_feedback` management command. Outputs MFS-compatible camelCase field names.

## Forms

- `FeedbackForm` -- full feedback with subject, message, email validation
- `QuickFeedbackForm` -- minimal inline feedback (maps helpful->general, not_helpful/confusing/missing_info->suggestion)
