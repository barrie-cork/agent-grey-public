"""
Error handling and categorization for results processing.

This module provides specialized error handling for the results processing pipeline,
categorizing errors for better user transparency and system debugging.
"""

import logging
from typing import Tuple

from django.db import IntegrityError

from apps.serp_execution.models import RawSearchResult

logger = logging.getLogger(__name__)


class ProcessingStatus:
    """Simplified processing status categories."""

    SUCCESS = "success"
    FILTERED = "filtered"
    ERROR = "error"


class ProcessingErrorHandler:
    """Handles and categorizes processing errors for transparency."""

    ERROR_CATEGORIES = {
        "network": ["timeout", "connection_error"],
        "validation": ["invalid_url", "missing_field"],
        "duplicate": ["url_exists", "content_match"],
        "integrity": ["unique_constraint", "database_constraint"],
        "processing": ["normalization_failed", "extraction_failed"],
    }

    def __init__(self):
        """Initialize the error handler."""
        self.logger = logging.getLogger(self.__class__.__name__)

    def categorize_error(
        self, exception: Exception, raw_result: RawSearchResult
    ) -> Tuple[str, str]:
        """
        Categorize processing errors using simplified categories.

        Args:
            exception: The exception that occurred
            raw_result: The raw result being processed

        Returns:
            Tuple of (category, user_friendly_message)
        """
        if isinstance(exception, IntegrityError):
            if (
                "duplicate" in str(exception).lower()
                or "unique constraint" in str(exception).lower()
            ):
                return (
                    ProcessingStatus.FILTERED,
                    f"Duplicate URL detected: {raw_result.link}",
                )
            else:
                return (
                    ProcessingStatus.ERROR,
                    f"Database constraint error for: {raw_result.title[:50]}...",
                )

        # Network-related errors
        if (
            "timeout" in str(exception).lower()
            or "connection" in str(exception).lower()
        ):
            return (
                ProcessingStatus.ERROR,
                f"Network error processing: {raw_result.title[:50]}...",
            )

        # Validation errors
        if (
            "validation" in str(exception).lower()
            or "invalid" in str(exception).lower()
        ):
            return (
                ProcessingStatus.ERROR,
                f"Validation failed for: {raw_result.title[:50]}...",
            )

        # All other errors are classified as general processing errors
        return (
            ProcessingStatus.ERROR,
            f"Processing failed for: {raw_result.title[:50]}...",
        )

    def handle_batch_error(
        self, exception: Exception, raw_result: RawSearchResult, processing_session=None
    ) -> dict:
        """
        Handle an error that occurred during batch processing.

        Args:
            exception: The exception that occurred
            raw_result: The raw result being processed
            processing_session: Optional ProcessingSession to record error

        Returns:
            Dictionary with error information
        """
        error_category, user_message = self.categorize_error(exception, raw_result)

        self.logger.error(
            f"💥 ERROR [{error_category}] processing result {raw_result.id}:"
        )
        self.logger.error(f"   Message: {user_message}")

        # Record error in raw result
        raw_result.processing_error = f"[{error_category}] {user_message}"
        raw_result.save(update_fields=["processing_error"])

        # Add error to processing session if provided
        if processing_session:
            processing_session.add_error(
                error_message=f"[{error_category}] Failed to process result {raw_result.id}",
                error_details={
                    "raw_result_id": str(raw_result.id),
                    "error_category": error_category,
                    "user_message": user_message,
                    "title": raw_result.title,
                    "url": raw_result.link,
                },
            )

        return {
            "error_category": error_category,
            "user_message": user_message,
            "raw_result_id": str(raw_result.id),
            "exception_type": type(exception).__name__,
        }

    def get_error_summary(self, errors: list) -> dict:
        """
        Generate a summary of errors by category.

        Args:
            errors: List of error dictionaries

        Returns:
            Dictionary with error summary statistics
        """
        summary = {"total_errors": len(errors), "by_category": {}, "common_issues": []}

        # Count by category
        for error in errors:
            category = error.get("error_category", "unknown")
            summary["by_category"][category] = (
                summary["by_category"].get(category, 0) + 1
            )

        # Identify common issues
        if summary["by_category"].get(ProcessingStatus.FILTERED, 0) > 0:
            summary["common_issues"].append(
                f"{summary['by_category'][ProcessingStatus.FILTERED]} duplicates filtered"
            )

        return summary
