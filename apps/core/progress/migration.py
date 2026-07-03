"""Migration helpers for transitioning to unified progress tracking."""

import logging

from apps.core.models import Configuration

logger = logging.getLogger(__name__)


class ProgressMigrationHelper:
    """Helper for migrating from old to new progress system."""

    @staticmethod
    def update_execution_progress(
        session_id: str,
        queries_completed: int,
        total_queries: int,
        current_query: str | None = None,
    ):
        """
        Migrate execution progress updates.
        Replaces: QueryProgressService.update_progress()
        """
        # Check if new system should be used via JSON config
        use_new_system = Configuration.get_config(
            "use_event_driven_state_machine", False
        )

        if use_new_system:
            # Use new system
            from apps.core.progress.tracker import progress_tracker

            return progress_tracker.update_progress(
                session_id=session_id,
                component="executing",
                processed_count=queries_completed,
                total_count=total_queries,
                current_step=(
                    f"Executing: {current_query}"
                    if current_query
                    else "Executing queries"
                ),
            )
        else:
            # Legacy system - no WebSocket support (removed)
            # Calculate progress using old formula for compatibility
            progress = (
                min(queries_completed * 100 // total_queries, 100)
                if total_queries
                else 0
            )

            logger.debug(
                f"Legacy execution progress: {session_id} - {queries_completed}/{total_queries} ({progress}%)"
            )

            return progress

    @staticmethod
    def update_processing_progress(
        session_id: str, processed: int, total: int, stage: str = "processing"
    ):
        """
        Migrate processing progress updates.
        Replaces: Multiple conflicting calculations in processing tasks
        """
        # Check if new system should be used via JSON config
        use_new_system = Configuration.get_config(
            "use_event_driven_state_machine", False
        )

        if use_new_system:
            # Use new system
            from apps.core.progress.tracker import progress_tracker

            # Map stage to component
            component_map = {
                "processing": "processing_results",
                "deduplication": "deduplication",
                "finalization": "finalization",
            }
            component = component_map.get(stage, "processing_results")

            return progress_tracker.update_progress(
                session_id=session_id,
                component=component,
                processed_count=processed,
                total_count=total,
                current_step=f"{stage.title()}: {processed}/{total}",
            )
        else:
            # Legacy system - no WebSocket support (removed)
            # Calculate progress using old formula for compatibility
            progress = min(40 + (processed * 40 // total), 80) if total else 40

            logger.debug(f"Legacy progress update: {session_id} - {progress}%")

            return progress
