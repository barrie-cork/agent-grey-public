"""
Base validator class for state transitions.

This module provides the abstract base class for all state validators
in the workflow system.
"""

from abc import ABC, abstractmethod


class BaseStateValidator(ABC):
    """Base class for state validators."""

    @abstractmethod
    def validate(self, session):
        """
        Validate if session can transition to this state.

        Args:
            session: SearchSession instance to validate

        Returns:
            tuple: A tuple of (is_valid, error_message) where:
                - is_valid (bool): True if transition is allowed
                - error_message (str or None): Description of why transition is not allowed (if applicable)
        """
        pass
