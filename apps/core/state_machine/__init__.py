"""
Event-driven state machine for managing SearchSession workflow.

This module provides a centralized, event-driven approach to state management,
replacing the fragmented state logic scattered across multiple services.
"""

from .event_bus import event_bus
from .event_store import event_store
from .events import ErrorEvent, ProgressEvent, StateTransitionEvent
from .exceptions import (
    EventBusError,
    InvalidTransition,
    LockAcquisitionFailed,
    StateMachineException,
    StateNotFound,
)
from .registry import state_registry
from .state_machine import SessionStateMachine, state_machine

__all__ = [
    "SessionStateMachine",
    "state_machine",
    "StateTransitionEvent",
    "ProgressEvent",
    "ErrorEvent",
    "event_bus",
    "event_store",
    "state_registry",
    "StateMachineException",
    "InvalidTransition",
    "StateNotFound",
    "LockAcquisitionFailed",
    "EventBusError",
]
