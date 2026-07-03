"""
Service layer for API business logic in SERP execution module.

Provides centralized business logic for API endpoints, maintaining
separation of concerns and single responsibility principle.
"""

import logging
from typing import Any, Dict

from django.http import Http404
from django.utils import timezone

from ..models import SearchExecution
from apps.core.services.serper_client import SerperClient

from ..services.result_processor import ResultProcessor
from .statistics_service import SessionProgressService

logger = logging.getLogger(__name__)


class ExecutionAPIService:
    """Service for execution-related API operations."""

    def get_execution_status(self, execution_id: str, user) -> Dict[str, Any]:
        """
        Get detailed execution status with ownership verification.

        Args:
            execution_id: UUID string identifying the search execution
            user: The authenticated user

        Returns:
            Dict[str, Any]: Execution status data compatible with ExecutionStatusResponse

        Raises:
            Http404: If execution not found
            PermissionError: If user doesn't own the execution
        """
        try:
            execution = SearchExecution.objects.get(id=execution_id)
        except SearchExecution.DoesNotExist:
            raise Http404("Execution not found")

        # Verify ownership
        if execution.query.strategy.session.owner != user:
            raise PermissionError("Permission denied")

        return {
            "id": str(execution.id),
            "status": execution.status,
            "status_display": execution.get_status_display(),
            "results_count": execution.results_count,
            "current_step": execution.current_step,
            "error_message": execution.error_message,
            "duration_seconds": execution.duration_seconds,
            "can_retry": execution.can_retry(),
            "created_at": execution.created_at.isoformat(),
            "completed_at": (
                execution.completed_at.isoformat() if execution.completed_at else None
            ),
        }


class SessionAPIService:
    """Service for session-related API operations."""

    def __init__(self):
        self.progress_service = SessionProgressService()

    def get_session_progress(
        self, session_id: str, user, session_provider
    ) -> Dict[str, Any]:
        """
        Get session progress with ownership verification.

        Args:
            session_id: UUID string identifying the search session
            user: The authenticated user
            session_provider: Session provider for ownership verification

        Returns:
            dict: Session progress data

        Raises:
            Http404: If session not found
            PermissionError: If user doesn't own the session
        """
        # Get session and verify ownership through provider
        session = session_provider.get_session(session_id)
        if session is None:
            raise Http404(f"Session {session_id} not found")
        if not session_provider.verify_session_ownership(session_id, user):
            raise PermissionError("Permission denied")

        # Get execution statistics
        executions = (
            SearchExecution.objects.filter(query__session_id=session.id)
            .select_related("query")
            .order_by("-created_at")
        )

        # Calculate counts
        total_queries = executions.count()
        completed_queries = executions.filter(status="completed").count()

        return {
            "session_id": session_id,
            "session_status": session.status,
            "current_step": session.status_detail
            or session.STATUS_MESSAGES.get(session.status, ""),
            "processed_count": completed_queries,
            "total_count": total_queries,
            "total_queries": total_queries,
            "completed_queries": completed_queries,
            "component": (
                "executing" if session.status == "executing" else session.status
            ),
            "updated_at": timezone.now().isoformat(),
        }

    def cancel_session_executions(
        self, session_id: str, user, session_provider
    ) -> Dict[str, Any]:
        """
        Cancel all running executions for a session.

        Args:
            session_id: UUID string identifying the search session
            user: The authenticated user
            session_provider: Session provider for ownership verification

        Returns:
            dict: Cancellation results

        Raises:
            Http404: If session not found
            PermissionError: If user doesn't own the session
        """
        # Get session and verify ownership
        session = session_provider.get_session(session_id)
        if session is None:
            raise Http404(f"Session {session_id} not found")
        if not session_provider.verify_session_ownership(session_id, user):
            raise PermissionError("Permission denied")

        # Cancel running executions
        running_executions = SearchExecution.objects.filter(
            query__session_id=session.id, status__in=["pending", "running"]
        )

        cancelled_count = 0
        failed_cancellations = []

        for execution in running_executions:
            try:
                # Revoke Celery task if it has a task ID
                if execution.celery_task_id:
                    from celery import current_app

                    current_app.control.revoke(execution.celery_task_id, terminate=True)

                # Update status
                execution.status = "cancelled"
                execution.completed_at = timezone.now()
                execution.error_message = "Cancelled by user"
                execution.save()
                cancelled_count += 1

                logger.info(
                    f"Cancelled execution {execution.id} for session {session_id}"
                )

            except Exception as e:
                logger.error(f"Failed to cancel execution {execution.id}: {str(e)}")
                failed_cancellations.append({"id": str(execution.id), "error": str(e)})

        # Update session status if all executions are complete
        remaining_active = SearchExecution.objects.filter(
            query__session_id=session.id, status__in=["pending", "running"]
        ).exists()

        if not remaining_active:
            session.status = "completed"
            session.save()

        return {
            "success": cancelled_count > 0 or len(failed_cancellations) == 0,
            "cancelled_count": cancelled_count,
            "failed_cancellations": failed_cancellations,
            "session_status": session.status,
            "has_active_executions": remaining_active,
            "message": (
                f"Cancelled {cancelled_count} executions"
                if cancelled_count > 0
                else "No executions to cancel"
            ),
        }


class DiagnosticAPIService:
    """Service for diagnostic API operations."""

    def run_diagnostic_test(self, query: str, num_results: int, user) -> Dict[str, Any]:
        """
        Run a diagnostic test of the Serper API.

        Args:
            query: Test search query
            num_results: Number of results to request
            user: The authenticated user (for logging)

        Returns:
            dict: Diagnostic test results

        Raises:
            SerperAPIError: If API test fails
        """
        client = SerperClient()
        processor = ResultProcessor()

        logger.info(
            f"Diagnostic API test initiated by {user.username} with query: {query}"
        )

        # Execute search (safe_search returns tuple of results + metadata)
        results, metadata = client.safe_search(query, num_results=num_results)

        # Analyze response structure
        response_analysis = {
            "success": True,
            "query": query,
            "num_requested": num_results,
            "response_keys": list(results.keys()) if results else [],
            "organic_count": len(results.get("organic", [])),
            "metadata": metadata,
            "has_organic": "organic" in results,
            "alternative_results": {},
            "first_result_structure": None,
            "api_status": "connected",
        }

        # Check for alternative result types
        for key in [
            "knowledgeGraph",
            "answerBox",
            "topStories",
            "peopleAlsoAsk",
            "relatedSearches",
        ]:
            if key in results and results[key]:
                response_analysis["alternative_results"][key] = len(results[key])

        # Get first result structure if available
        if results.get("organic"):
            first_result = results["organic"][0]
            response_analysis["first_result_structure"] = {
                "keys": list(first_result.keys()),
                "title": first_result.get("title", "")[:100],
                "link": first_result.get("link", "")[:100],
                "snippet": first_result.get("snippet", "")[:100],
            }

        # Test result processing
        if results.get("organic"):
            # Test processing a single result
            test_result = processor._process_single_result(results["organic"][0])
            if test_result:
                response_analysis["processing_test"] = {
                    "success": True,
                    "processed_url": test_result.get("url", "")[:100],
                    "processed_title": test_result.get("title", "")[:100],
                    "is_pdf": test_result.get("is_pdf", False),
                }
            else:
                response_analysis["processing_test"] = {
                    "success": False,
                    "error": "Failed to process result",
                }

        logger.info(
            f"Diagnostic test completed: {response_analysis['organic_count']} results found"
        )

        return response_analysis


class RecoveryAPIService:
    """Service for recovery-related API operations."""

    def retry_failed_execution(self, execution_id: str, user) -> Dict[str, Any]:
        """
        Retry a failed execution with ownership verification.

        Args:
            execution_id: UUID string identifying the search execution
            user: The authenticated user

        Returns:
            dict: Retry operation results

        Raises:
            Http404: If execution not found
            PermissionError: If user doesn't own the execution
            ValueError: If execution cannot be retried
        """
        try:
            execution = SearchExecution.objects.get(id=execution_id)
        except SearchExecution.DoesNotExist:
            raise Http404("Execution not found")

        # Verify ownership
        if execution.query.strategy.session.owner != user:
            raise PermissionError("Permission denied")

        # Check if execution can be retried
        if not execution.can_retry():
            raise ValueError("Execution cannot be retried in current state")

        # Initiate retry
        try:
            # Import here to avoid circular dependency
            from ..tasks import retry_failed_execution_task

            # Reset execution status
            execution.status = "pending"
            execution.error_message = ""  # Use empty string instead of None
            execution.retry_count = (execution.retry_count or 0) + 1
            execution.save()

            # Submit retry task
            task = retry_failed_execution_task.delay(str(execution.id))

            # Update with new task ID
            execution.celery_task_id = task.id
            execution.save()

            logger.info(
                f"Retry initiated for execution {execution.id} by {user.username}"
            )

            return {
                "success": True,
                "execution_id": str(execution.id),
                "message": f"Retry initiated (attempt {execution.retry_count})",
                "new_status": "pending",
            }

        except Exception as e:
            logger.error(
                f"Failed to initiate retry for execution {execution.id}: {str(e)}"
            )

            # Restore failed status
            execution.status = "failed"
            execution.error_message = f"Retry failed: {str(e)}"
            execution.save()

            raise
