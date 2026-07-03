"""
Query management service for serp_execution.
Handles query retrieval, execution record creation, and task orchestration.
"""

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.serp_execution.api_types import ExecutionPlan
from apps.serp_execution.models import SearchExecution

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.review_manager.models import SearchSession

logger = logging.getLogger(__name__)


class QueryManager:
    """Manages search queries and their execution records."""

    def __init__(self):
        """Initialize the query manager."""
        self.logger = logger.getChild(self.__class__.__name__)

    def get_active_queries(self, session: "SearchSession"):
        """
        Get all active queries for a session, ordered for execution.

        Args:
            session: The SearchSession object

        Returns:
            list: List of SearchQuery objects ordered by execution priority
        """
        from apps.search_strategy.models import SearchQuery

        queries = (
            SearchQuery.objects.filter(strategy__session=session, is_active=True)
            .select_related("strategy")
            .order_by("execution_order", "created_at")
        )

        query_count = queries.count()
        self.logger.info(f"Found {query_count} active queries for session {session.id}")

        return list(queries)

    def create_execution_plan(self, session_id: UUID, queries):
        """
        Create an execution plan for the given queries.

        Args:
            session_id: The session UUID
            queries: List of SearchQuery objects

        Returns:
            ExecutionPlan: ExecutionPlan with execution details
        """
        query_ids = [query.id for query in queries]

        # Estimate duration based on query count
        # Assuming ~2 seconds per query for API calls
        estimated_duration = len(queries) * 2

        plan = ExecutionPlan(
            session_id=str(session_id),
            query_ids=[str(qid) for qid in query_ids],
            execution_strategy="parallel",
            estimated_duration=estimated_duration,
            total_queries=len(queries),
        )

        self.logger.info(
            f"Created execution plan for {len(queries)} queries, "
            f"estimated duration: {estimated_duration}s"
        )

        return plan

    @transaction.atomic
    def create_execution_records(
        self,
        queries,
        initiated_by: "User",
        celery_task_id: str | None = None,
        provider_key: str = "serper",
        provider_display: str = "Serper.dev",
    ):
        """
        Create SearchExecution records for all queries.

        Args:
            queries: List of SearchQuery objects
            initiated_by: User who initiated the execution
            celery_task_id: Optional Celery task ID
            provider_key: SERP provider key (e.g. 'serper')
            provider_display: Human-readable provider name

        Returns:
            list: List of created SearchExecution objects

        Raises:
            Exception: If execution record creation fails
        """
        execution_records = []

        try:
            for query in queries:
                execution = SearchExecution.objects.create(
                    query=query,
                    initiated_by=initiated_by,
                    status="pending",
                    celery_task_id=celery_task_id,
                    serp_provider=provider_key,
                    serp_provider_display=provider_display,
                    created_at=timezone.now(),
                )
                execution_records.append(execution)

                self.logger.debug(
                    f"Created execution record {execution.id} for query {query.id}"
                )

            self.logger.info(
                f"Successfully created {len(execution_records)} execution records"
            )

            return execution_records

        except Exception as e:
            self.logger.error(
                f"Failed to create execution records: {str(e)}", exc_info=True
            )
            # Transaction will rollback automatically
            raise

    def prepare_celery_tasks(self, execution_records):
        """
        Prepare Celery task signatures for execution.

        Args:
            execution_records: List of SearchExecution objects

        Returns:
            list: List of Celery task signatures
        """
        from apps.serp_execution.tasks import perform_serp_query_task

        tasks = []

        for execution in execution_records:
            # Create immutable signature for parallel execution
            task = perform_serp_query_task.si(
                str(execution.id), str(execution.query.id)
            )
            tasks.append(task)

        self.logger.info(f"Prepared {len(tasks)} Celery tasks for execution")

        return tasks

    def cleanup_failed_executions(self, execution_records) -> None:
        """
        Clean up execution records after a failure.

        Args:
            execution_records: List of SearchExecution objects to clean up
        """
        if not execution_records:
            return

        deleted_count = 0
        for execution in execution_records:
            try:
                execution.delete()
                deleted_count += 1
            except Exception as e:
                self.logger.error(f"Failed to delete execution {execution.id}: {e}")

        self.logger.info(
            f"Cleaned up {deleted_count}/{len(execution_records)} "
            f"failed execution records"
        )

    def get_execution_statistics(self, session_id: UUID) -> dict:
        """
        Get execution statistics for a session.

        Deprecated: Use ExecutionService.get_execution_stats() instead.
        This method is kept for backward compatibility.

        Args:
            session_id: The session UUID

        Returns:
            Dictionary with execution statistics
        """
        from .execution_service import ExecutionService

        # Delegate to the consolidated method in ExecutionService
        stats = ExecutionService.get_execution_stats(session_id)

        # Transform to match the expected format for this method
        return {
            "total_executions": stats.get("total_executions", 0),
            "completed": stats.get("completed", 0),
            "failed": stats.get("failed", 0),
            "pending": stats.get("pending", 0),
            "in_progress": stats.get("in_progress", 0),
            "completion_rate": stats.get("success_rate", 0),
        }
