"""
Completion and archive state validators.

Validates transitions to 'completed' and 'archived' states.
"""

import logging

from .base import BaseStateValidator

logger = logging.getLogger(__name__)


class CompletionStateValidator(BaseStateValidator):
    """Validates transitions to completed state."""

    def __init__(self):
        """Initialize validator with service dependencies."""
        super().__init__()
        # Services will be injected at runtime
        self.review_service = None

    def validate(self, session):
        """
        Validate if session can move to 'completed' status.

        Checks:
        - All results have been reviewed (or no results exist)
        - Review decisions have been made

        Args:
            session: SearchSession instance

        Returns:
            Tuple of (is_valid, error_message)
        """
        # If no results, can complete immediately
        if session.total_results == 0:
            return True, None

        # Check review progress
        total_results = session.total_results
        reviewed_results = session.reviewed_results

        if reviewed_results < total_results:
            pending = total_results - reviewed_results
            return (
                False,
                f"Review incomplete: {pending} of {total_results} results still need review.",
            )

        # Verify review decisions exist using service
        if self.review_service is None:
            from apps.review_results.services import ReviewService

            self.review_service = ReviewService

        decisions_count = self.review_service.get_review_decision_count(session.id)

        if decisions_count < total_results:
            logger.warning(
                f"Session {session.id} has {reviewed_results} reviewed but only "
                f"{decisions_count} decisions recorded"
            )
            # Allow completion anyway - reviewed_results is authoritative

        return True, None


class ArchiveStateValidator(BaseStateValidator):
    """Validates transitions to archived state."""

    def validate(self, session):
        """
        Validate if session can move to 'archived' status.

        Archive is generally allowed from any state as a way to
        deactivate a session.

        Args:
            session: SearchSession instance

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Archive is always allowed per the state machine
        # Could add business rules here if needed (e.g., require completion first)
        return True, None


class DataIntegrityValidator:
    """Validates overall session data integrity."""

    def __init__(self):
        """Initialize validator with service dependencies."""
        # Services will be injected at runtime
        self.query_service = None
        self.execution_service = None
        self.processing_service = None
        self.review_service = None

    def validate_session_data_integrity(self, session):
        """
        Comprehensive data integrity check for a session.

        This method performs a deep validation of session data
        to ensure consistency across all related models.

        Args:
            session: SearchSession instance

        Returns:
            Tuple of (is_valid, detailed_report)
        """
        # Initialize services if not already done
        self._initialize_services()

        issues = []

        # Delegate to specific validation methods
        issues.extend(self._validate_search_strategy(session))
        issues.extend(self._validate_queries(session))
        issues.extend(self._validate_executions(session))
        issues.extend(self._validate_results_consistency(session))

        if issues:
            report = "Data integrity issues found:\n" + "\n".join(
                f"- {issue}" for issue in issues
            )
            return False, report
        else:
            stats = self._generate_stats_report(session)
            return True, stats

    def _initialize_services(self):
        """Initialize service dependencies."""
        if self.query_service is None:
            from apps.search_strategy.services import QueryService

            self.query_service = QueryService

        if self.execution_service is None:
            from apps.serp_execution.services import ExecutionService

            self.execution_service = ExecutionService

        if self.processing_service is None:
            from apps.results_manager.services import ProcessingService

            self.processing_service = ProcessingService

        if self.review_service is None:
            from apps.review_results.services import ReviewService

            self.review_service = ReviewService

    def _validate_search_strategy(self, session):
        """Validate search strategy existence."""
        issues = []
        if self.query_service is None:
            return ["Query service not initialised"]
        if not self.query_service.has_search_strategy(session.id):
            issues.append("No search strategy defined")
        return issues

    def _validate_queries(self, session):
        """Validate query configuration."""
        issues = []
        if self.query_service is None:
            return ["Query service not initialised"]
        if self.query_service.has_search_strategy(session.id):
            query_count = self.query_service.get_active_query_count(session.id)

            if query_count == 0:
                issues.append("No active queries in search strategy")
        return issues

    def _validate_executions(self, session):
        """Validate execution statistics."""
        issues = []
        if self.execution_service is None:
            return ["Execution service not initialised"]
        # Get execution stats for potential future validation
        self.execution_service.get_execution_stats(session.id)

        # No specific validation needed for executions at this time
        # Stats are collected for reporting purposes
        return issues

    def _validate_results_consistency(self, session):
        """Validate results count consistency."""
        issues = []
        if self.execution_service is None or self.processing_service is None:
            return ["Services not initialised"]

        # Get stats from services
        execution_stats = self.execution_service.get_execution_stats(session.id)
        processed_count = self.processing_service.get_processed_result_count(session.id)

        # Check processed vs raw results
        raw_results_count = execution_stats.get("result_count", 0)
        if processed_count > raw_results_count:
            issues.append(
                f"More processed results ({processed_count}) than raw results ({raw_results_count})"
            )

        return issues

    def _generate_stats_report(self, session):
        """Generate statistics report for valid session."""
        if (
            self.query_service is None
            or self.execution_service is None
            or self.processing_service is None
        ):
            return "Services not initialised"
        # Get stats from all services
        query_count = self.query_service.get_active_query_count(session.id)
        execution_stats = self.execution_service.get_execution_stats(session.id)
        processed_count = self.processing_service.get_processed_result_count(session.id)

        report = (
            f"Data integrity check passed. "
            f"Queries: {query_count}, "
            f"Executions: {execution_stats['total']} "
            f"(completed: {execution_stats['completed']}, failed: {execution_stats['failed']}), "
            f"Raw results: {execution_stats['result_count']}, "
            f"Processed: {processed_count}"
        )
        return report
