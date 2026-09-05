from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from app.agent_runtime.domain.execution_state import ExecutionState
from app.core.errors import InvalidStateTransition


@dataclass
class ExecutionStateMachine:
    """
    Single authority for execution lifecycle transitions.

    The state machine owns the rules for moving an execution from one
    lifecycle state to another.

    Invalid transitions are exposed as the Agent-level
    InvalidStateTransition error.
    """

    state: ExecutionState = ExecutionState.CREATED

    _TRANSITIONS: ClassVar[
        dict[
            ExecutionState,
            frozenset[ExecutionState],
        ]
    ] = {
        ExecutionState.CREATED: frozenset(
            {
                ExecutionState.PLANNING,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
            }
        ),
        ExecutionState.PLANNING: frozenset(
            {
                ExecutionState.INFERENCE,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
            }
        ),
        ExecutionState.INFERENCE: frozenset(
            {
                ExecutionState.TOOL_EXECUTION,
                ExecutionState.COMPLETED,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
            }
        ),
        ExecutionState.TOOL_EXECUTION: frozenset(
            {
                ExecutionState.OBSERVING,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
            }
        ),
        ExecutionState.OBSERVING: frozenset(
            {
                ExecutionState.INFERENCE,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
            }
        ),
        ExecutionState.COMPLETED: frozenset(),
        ExecutionState.FAILED: frozenset(),
        ExecutionState.CANCELLED: frozenset(),
    }

    def can_transition_to(
        self,
        target: ExecutionState,
    ) -> bool:
        """
        Return whether the current state can transition to target.
        """
        return target in self._TRANSITIONS[self.state]

    def transition_to(
        self,
        target: ExecutionState,
    ) -> None:
        """
        Transition to target state.

        Invalid lifecycle transitions are converted into the Agent-level
        InvalidStateTransition error.
        """
        if not self.can_transition_to(target):
            raise InvalidStateTransition(
                "Invalid execution state transition: "
                f"{self.state.value} -> {target.value}"
            )

        self.state = target

    @property
    def is_terminal(self) -> bool:
        """
        Return whether the current state is terminal.
        """
        return self.state in {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
        }
