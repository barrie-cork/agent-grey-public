"""
Server-Sent Events (SSE) views for real-time session updates.

Provides push-based status updates for search sessions, eliminating
the need for client-side polling. Implements Django 5.2 async patterns
with proper ATOMIC_REQUESTS handling.
"""

import asyncio
import json
import logging

from asgiref.sync import sync_to_async
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.review_manager.models import SearchSession

logger = logging.getLogger(__name__)


@csrf_exempt  # SSE doesn't support CSRF tokens in EventSource API
@login_required
@transaction.non_atomic_requests  # Required for async views with ATOMIC_REQUESTS=True (Django 5.2)
async def session_status_stream(request, session_id):  # noqa: C901 - SSE stream
    """
    SSE endpoint for real-time session status updates.

    Streams session status changes to connected clients using Server-Sent Events.
    Implements Django 5.2 async patterns with proper database thread safety.

    Args:
        request: Django HttpRequest
        session_id: UUID of the SearchSession

    Returns:
        StreamingHttpResponse with text/event-stream content type

    SSE Event Format:
        data: {"type": "connected", "session_id": "uuid"}\\n\\n
        data: {"type": "status_update", "status": "executing", ...}\\n\\n
        data: {"type": "complete", "final_status": "completed"}\\n\\n

    Security:
        - User ownership validated via session.owner == request.user
        - Login required via @login_required decorator
        - CSRF exempt as EventSource API doesn't support CSRF tokens

    Django 5.2 Compatibility:
        - Uses @transaction.non_atomic_requests for async view compatibility
        - Uses sync_to_async(thread_sensitive=True) for database queries
        - Thread-safe database connection handling
    """

    async def event_generator():
        """
        Async generator for SSE events.

        Monitors session status and yields SSE-formatted events when changes occur.
        Implements change detection, error handling, and graceful termination.

        Yields:
            str: SSE-formatted event strings (data: {...}\\n\\n)
        """
        try:
            # Send initial connection event
            yield f'data: {{"type": "connected", "session_id": "{session_id}"}}\n\n'

            last_status = None
            last_updated = None
            consecutive_errors = 0
            max_errors = 3

            while True:
                try:
                    # Non-blocking session query with thread-safe database access
                    @sync_to_async(thread_sensitive=True)
                    def get_session_data():
                        """
                        Fetch session data from database.

                        Thread-safe database query that runs in sync context.
                        Only fetches required fields for efficiency.
                        Note: progress_percentage is calculated from total_results/reviewed_results.

                        Returns:
                            dict: Session data or None if not found/no access
                        """
                        session_data = (
                            SearchSession.objects.filter(
                                id=session_id,
                                owner=request.user,  # Security: only owner can stream
                            )
                            .values(
                                "status",
                                "total_results",
                                "reviewed_results",
                                "updated_at",
                            )
                            .first()
                        )

                        # Calculate progress_percentage property manually
                        if session_data:
                            total = session_data["total_results"]
                            reviewed = session_data["reviewed_results"]
                            session_data["progress_percentage"] = (
                                round((reviewed / total) * 100, 1) if total > 0 else 0
                            )

                        return session_data

                    session = await get_session_data()

                    if not session:
                        yield 'data: {"type": "error", "message": "Session not found or access denied"}\n\n'
                        break

                    # Only send updates when state changes
                    if (
                        session["status"] != last_status
                        or session["updated_at"] != last_updated
                    ):
                        event_data = {
                            "type": "status_update",
                            "status": session["status"],
                            "progress": session["progress_percentage"],
                            "total_results": session["total_results"],
                            "reviewed_results": session["reviewed_results"],
                            "timestamp": (
                                session["updated_at"].isoformat()
                                if session["updated_at"]
                                else None
                            ),
                        }

                        yield f"data: {json.dumps(event_data)}\n\n"

                        last_status = session["status"]
                        last_updated = session["updated_at"]
                        consecutive_errors = 0  # Reset error count on success

                    # Terminal states - close connection
                    if session["status"] in ["completed", "archived", "failed"]:
                        yield f'data: {{"type": "complete", "final_status": "{session["status"]}"}}\n\n'
                        break

                    # Wait before next check (non-blocking)
                    await asyncio.sleep(0.5)  # Check every 500ms

                except Exception as e:
                    consecutive_errors += 1
                    logger.error(
                        f"SSE error for session {session_id}: {e}",
                        exc_info=True,
                        extra={
                            "session_id": str(session_id),
                            "user_id": str(request.user.id),
                        },
                    )

                    if consecutive_errors >= max_errors:
                        yield 'data: {"type": "error", "message": "Too many errors, closing connection"}\n\n'
                        break

                    # Brief wait before retry
                    await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            # Client disconnected
            logger.info(
                f"SSE client disconnected for session {session_id}",
                extra={"session_id": str(session_id), "user_id": str(request.user.id)},
            )
            raise

        except Exception as e:
            logger.error(
                f"SSE generator error for session {session_id}: {e}",
                exc_info=True,
                extra={"session_id": str(session_id), "user_id": str(request.user.id)},
            )
            yield f'data: {{"type": "error", "message": "Stream error: {str(e)}"}}\n\n'

    # Return streaming response with SSE headers
    response = StreamingHttpResponse(
        event_generator(),
        content_type="text/event-stream",
    )

    # SSE-specific headers
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # Disable Nginx buffering

    # CORS headers if needed for cross-origin SSE (currently disabled)
    # response['Access-Control-Allow-Origin'] = '*'
    # response['Access-Control-Allow-Credentials'] = 'true'

    return response
