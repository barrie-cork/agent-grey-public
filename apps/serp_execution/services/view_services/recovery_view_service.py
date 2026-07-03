"""
Business logic service for ErrorRecoveryView.

Handles error analysis, recovery options, and retry logic
extracted from the view to maintain single responsibility.
"""

import logging

from ...recovery import recovery_manager

logger = logging.getLogger(__name__)


class RecoveryViewService:
    """Service for error recovery view business logic."""

    def analyze_execution_error(self, execution):
        """
        Analyze execution error and determine recovery options.

        Args:
            execution: The failed SearchExecution object

        Returns:
            dict: Error analysis and recovery options
        """
        analysis = recovery_manager.analyze_error(execution)
        recovery_options = recovery_manager.get_recovery_options(execution)

        return {
            "error_analysis": analysis,
            "recovery_options": recovery_options,
            "can_retry": execution.can_retry(),
            "retry_count": execution.retry_count or 0,
        }

    def prepare_recovery_form_data(self, execution):
        """
        Prepare initial data for the recovery form.

        Args:
            execution: The failed SearchExecution object

        Returns:
            dict: Initial form data based on error analysis
        """
        analysis = recovery_manager.analyze_error(execution)

        initial_data = {}

        # Set default recovery action based on error type
        if analysis.get("error_type") == "RateLimitError":
            initial_data["recovery_action"] = "retry_later"
        elif analysis.get("is_recoverable", False):
            initial_data["recovery_action"] = "retry"
        else:
            initial_data["recovery_action"] = "skip"

        return initial_data

    def process_recovery_action(self, execution, form_data):
        """
        Process the selected recovery action.

        Args:
            execution: The failed SearchExecution object
            form_data: Validated form data with recovery action

        Returns:
            dict: Result of recovery action

        Raises:
            Exception: If recovery action fails
        """
        action = form_data["recovery_action"]

        if action == "retry":
            # Import here to avoid circular dependency
            from ...tasks import retry_failed_execution_task

            try:
                # Submit retry task
                task = retry_failed_execution_task.delay(str(execution.id))

                logger.info(
                    f"Retry task submitted for execution {execution.id}, task ID: {task.id}"
                )

                return {
                    "success": True,
                    "action": "retry",
                    "message": "Execution retry has been initiated.",
                    "task_id": task.id,
                }

            except Exception as e:
                logger.error(f"Failed to submit retry task: {str(e)}")
                raise

        elif action == "skip":
            # Mark as skipped
            execution.status = "skipped"
            execution.error_message = "Skipped by user after error"
            execution.save()

            return {
                "success": True,
                "action": "skip",
                "message": "Execution has been skipped.",
            }

        elif action == "retry_later":
            # Keep in failed state for later retry
            return {
                "success": True,
                "action": "retry_later",
                "message": "Execution marked for later retry.",
            }

        elif action == "manual":
            # Keep in failed state but mark for manual intervention
            execution.error_message = "Manual intervention required - marked by user"
            execution.save()

            return {
                "success": True,
                "action": "manual",
                "message": "Execution marked for manual intervention.",
            }

        else:
            raise ValueError(f"Unknown recovery action: {action}")
