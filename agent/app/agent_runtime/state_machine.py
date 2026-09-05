from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from app.agent_runtime.domain.execution_state import ExecutionState


class InvalidExecutionTransitionError(
    RuntimeError
):
    """
    Raised when an execution attempts an invalid
    lifecycle transition.
    """


@dataclass
class ExecutionStateMachine:
    """
    Single authority for execution lifecycle transitions.

    The state machine owns the rules for moving an
    execution from one lifecycle state to another.
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
        return target in self._TRANSITIONS[self.state]

    def transition_to(
        self,
        target: ExecutionState,
    ) -> None:
        if not self.can_transition_to(target):
            raise InvalidExecutionTransitionError(
                "Invalid execution state transition: "
                f"{self.state.value} -> {target.value}"
            )

        self.state = target

    @property
    def is_terminal(self) -> bool:
        return self.state in {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
        }
