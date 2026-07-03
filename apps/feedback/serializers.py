"""
Shared feedback serialization for export API and management commands.
"""


def serialize_feedback(fb, request=None):
    """Serialize a UserFeedback instance to MFS-compatible dict.

    Args:
        fb: UserFeedback instance
        request: Optional HttpRequest for building absolute URLs
    """
    js_errors = []
    if fb.interaction_context and isinstance(fb.interaction_context, dict):
        js_errors = fb.interaction_context.get("js_errors", [])

    screenshot_url = None
    if fb.screenshot:
        if request:
            screenshot_url = request.build_absolute_uri(fb.screenshot.url)
        else:
            screenshot_url = fb.screenshot.url

    return {
        "_id": str(fb.id),
        "type": fb.feedback_type,
        "message": fb.message,
        "subject": fb.subject,
        "severity": fb.severity or None,
        "screen": fb.page_path,
        "screenCategory": fb.screen_category or fb.categorize_screen(),
        "interactionContext": (
            fb.interaction_context.get("formatted_text", "")
            if isinstance(fb.interaction_context, dict)
            else ""
        ),
        "expectedBehavior": fb.expected_behaviour,
        "actualBehavior": fb.actual_behaviour,
        "frequency": fb.frequency,
        "contactEmail": fb.contact_email or fb.email or "",
        "transcription": fb.transcription,
        "audioDurationMs": fb.audio_duration_ms,
        "audioStorageId": fb.audio_file.name if fb.audio_file else None,
        "screenshotUrl": screenshot_url,
        "lastError": js_errors[0] if js_errors else None,
        "deviceInfo": {
            "platform": "web",
            "browser": (
                fb.browser_info.get("user_agent", "")[:100] if fb.browser_info else ""
            ),
            "screenResolution": (
                fb.browser_info.get("screen_resolution", "") if fb.browser_info else ""
            ),
        },
        "createdAt": int(fb.created_at.timestamp() * 1000),
        "user": ({"email": fb.user.email, "role": "user"} if fb.user else None),
        "userRole": "user",
        "linkedIssueNumber": fb.github_issue_number,
        "linkedIssueUrl": fb.github_issue_url,
        "linkedIssueState": fb.github_issue_state,
        "teamDecision": fb.team_decision,
    }
