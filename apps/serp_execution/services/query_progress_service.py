"""
Service for managing query-level progress tracking.

This service handles real-time progress updates for individual search executions,
broadcasting updates via SSE to connected clients.
"""

import logging
from typing import Optional
from uuid import UUID

from django.db import transaction

from apps.serp_execution.models import SearchExecution

logger = logging.getLogger(__name__)


class QueryProgressError(Exception):
    """Raised when query progress tracking fails."""

    pass


class QueryProgressService:
    """
    Service for managing query-level progress tracking.

    Follows existing service patterns from api_service.py and statistics_service.py
    """

    def __init__(self, execution_id: UUID):
        """Initialize service with execution ID."""
        try:
            self.execution = SearchExecution.objects.select_related(
                "query", "query__session", "initiated_by"
            ).get(id=execution_id)
        except SearchExecution.DoesNotExist:
            raise QueryProgressError(f"Execution {execution_id} not found")

    @transaction.atomic
    def update_status(
        self, step: str = "", phase: Optional[str] = None, broadcast: bool = True
    ) -> bool:
        """
        Update query execution status (no percentages).

        Args:
            step: Current step description
            phase: Processing phase
            broadcast: Whether to broadcast via SSE

        Returns:
            True if successful
        """
        try:
            # Update execution
            if step:
                self.execution.current_step = step
            if phase:
                self.execution.processing_phase = phase

            self.execution.save(
                update_fields=["current_step", "processing_phase", "updated_at"]
            )

            # Update session status directly
            if broadcast and self.execution.query:
                from apps.review_manager.models import SearchSession

                try:
                    session = SearchSession.objects.get(
                        id=self.execution.query.session_id
                    )
                    session.update_status_detail(step)
                except SearchSession.DoesNotExist:
                    logger.warning(
                        f"Session {self.execution.query.session_id} not found for progress update"
                    )

            logger.info(f"Updated status for execution {self.execution.id}: {step}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to update status for execution {self.execution.id}: {e}",
                exc_info=True,
            )
            raise QueryProgressError(f"Status update failed: {e}")
