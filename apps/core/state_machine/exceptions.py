"""Custom exceptions for the state machine module."""


class StateMachineException(Exception):
    """Base exception for all state machine errors."""

    pass


class InvalidTransition(StateMachineException):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: str, to_state: str, message: str | None = None):
        self.from_state = from_state
        self.to_state = to_state
        if message is None:
            message = f"Cannot transition from '{from_state}' to '{to_state}'"
        super().__init__(message)


class StateNotFound(StateMachineException):
    """Raised when a state is not found in the state graph."""

    pass


class LockAcquisitionFailed(StateMachineException):
    """Raised when unable to acquire a distributed lock."""

    pass


class EventBusError(StateMachineException):
    """Raised when event bus operations fail."""

    pass
