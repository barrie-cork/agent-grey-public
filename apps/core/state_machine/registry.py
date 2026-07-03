"""State registry for managing state definitions and allowed transitions."""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class StateDefinition:
    """Definition of a single state in the state machine."""

    name: str
    allowed_transitions: List[str]
    is_automated: bool = False
    is_terminal: bool = False
    metadata: Optional[Dict] = None


class StateRegistry:
    """Registry for all states and their allowed transitions."""

    def __init__(self):
        self._states: Dict[str, StateDefinition] = {}
        self._initialize_default_states()

    def _initialize_default_states(self):
        """Initialize with the 9-state workflow from requirements."""
        states = [
            StateDefinition("draft", ["defining_search", "archived"], False),
            StateDefinition(
                "defining_search", ["ready_to_execute", "draft", "archived"], False
            ),
            StateDefinition(
                "ready_to_execute", ["executing", "defining_search", "archived"], True
            ),
            StateDefinition(
                "executing", ["processing_results", "failed", "archived"], True
            ),
            StateDefinition(
                "processing_results",
                ["ready_for_review", "completed", "failed", "archived"],
                True,
            ),
            StateDefinition("ready_for_review", ["under_review", "archived"], True),
            StateDefinition(
                "under_review", ["completed", "ready_for_review", "archived"], False
            ),
            StateDefinition("completed", ["archived", "under_review"], False),
            StateDefinition("archived", ["draft"], False, True),
            StateDefinition("failed", ["draft", "archived"], False),
        ]

        for state in states:
            self.register_state(state)

    def register_state(self, state: StateDefinition):
        """Register a new state definition."""
        self._states[state.name] = state

    def get_state(self, state_name: str) -> Optional[StateDefinition]:
        """Get a state definition by name."""
        return self._states.get(state_name)

    def can_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a transition is allowed."""
        state_def = self.get_state(from_state)
        if not state_def:
            return False
        return to_state in state_def.allowed_transitions

    def get_automated_states(self) -> List[str]:
        """Get list of all automated states."""
        return [name for name, state in self._states.items() if state.is_automated]

    def get_all_states(self) -> List[str]:
        """Get list of all state names."""
        return list(self._states.keys())

    def is_terminal_state(self, state_name: str) -> bool:
        """Check if a state is terminal."""
        state_def = self.get_state(state_name)
        return state_def.is_terminal if state_def else False


# Global registry instance
state_registry = StateRegistry()
