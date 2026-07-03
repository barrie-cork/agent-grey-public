"""
Workflow validators for SearchSession state transitions.

This package provides modular validation logic for business rules that govern
when state transitions are allowed in the 9-state workflow.
"""

from .base import BaseStateValidator
from .completion import (
    ArchiveStateValidator,
    CompletionStateValidator,
    DataIntegrityValidator,
)
from .execution import ExecutionStateValidator
from .processing import ProcessingStateValidator
from .review import ReviewStateValidator


# For backward compatibility, expose validators through WorkflowValidator class
class WorkflowValidator:
    """
    Validates workflow state transitions based on business rules.

    This class provides a backward-compatible interface to the modular validators.
    """

    # Initialize validator instances
    _execution_validator = ExecutionStateValidator()
    _processing_validator = ProcessingStateValidator()
    _review_validator = ReviewStateValidator()
    _completion_validator = CompletionStateValidator()
    _archive_validator = ArchiveStateValidator()
    _data_integrity_validator = DataIntegrityValidator()

    @classmethod
    def can_execute(cls, session):
        """Validate if session can move to 'executing' status."""
        return cls._execution_validator.validate(session)

    @classmethod
    def can_process_results(cls, session):
        """Validate if session can move to 'processing_results' status."""
        return cls._processing_validator.validate(session)

    @classmethod
    def can_review(cls, session):
        """Validate if session can move to 'ready_for_review' status."""
        return cls._review_validator.validate(session)

    @classmethod
    def can_complete(cls, session):
        """Validate if session can move to 'completed' status."""
        return cls._completion_validator.validate(session)

    @classmethod
    def can_archive(cls, session):
        """Validate if session can move to 'archived' status."""
        return cls._archive_validator.validate(session)

    @classmethod
    def validate_session_data_integrity(cls, session):
        """Comprehensive data integrity check for a session."""
        return cls._data_integrity_validator.validate_session_data_integrity(session)


__all__ = [
    "BaseStateValidator",
    "ExecutionStateValidator",
    "ProcessingStateValidator",
    "ReviewStateValidator",
    "CompletionStateValidator",
    "ArchiveStateValidator",
    "DataIntegrityValidator",
    "WorkflowValidator",  # For backward compatibility
]
