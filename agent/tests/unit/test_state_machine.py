from __future__ import annotations

import pytest

from app.agent_runtime.domain import ExecutionState
from app.agent_runtime.state_machine import ExecutionStateMachine
from app.core.errors import InvalidStateTransition


def test_initial_state_is_created() -> None:
    machine = ExecutionStateMachine()

    assert machine.state is ExecutionState.CREATED
    assert not machine.is_terminal


def test_valid_happy_path_transition() -> None:
    machine = ExecutionStateMachine()

    machine.transition_to(
        ExecutionState.PLANNING
    )
    assert machine.state is ExecutionState.PLANNING

    machine.transition_to(
        ExecutionState.INFERENCE
    )
    assert machine.state is ExecutionState.INFERENCE

    machine.transition_to(
        ExecutionState.COMPLETED
    )
    assert machine.state is ExecutionState.COMPLETED

    assert machine.is_terminal


def test_valid_tool_execution_loop() -> None:
    machine = ExecutionStateMachine()

    machine.transition_to(
        ExecutionState.PLANNING
    )
    machine.transition_to(
        ExecutionState.INFERENCE
    )
    machine.transition_to(
        ExecutionState.TOOL_EXECUTION
    )
    machine.transition_to(
        ExecutionState.OBSERVING
    )
    machine.transition_to(
        ExecutionState.INFERENCE
    )
    machine.transition_to(
        ExecutionState.COMPLETED
    )

    assert machine.state is ExecutionState.COMPLETED


@pytest.mark.parametrize(
    "start,target",
    [
        (
            ExecutionState.CREATED,
            ExecutionState.INFERENCE,
        ),
        (
            ExecutionState.CREATED,
            ExecutionState.COMPLETED,
        ),
        (
            ExecutionState.PLANNING,
            ExecutionState.COMPLETED,
        ),
        (
            ExecutionState.INFERENCE,
            ExecutionState.OBSERVING,
        ),
        (
            ExecutionState.TOOL_EXECUTION,
            ExecutionState.COMPLETED,
        ),
        (
            ExecutionState.COMPLETED,
            ExecutionState.INFERENCE,
        ),
        (
            ExecutionState.FAILED,
            ExecutionState.INFERENCE,
        ),
        (
            ExecutionState.CANCELLED,
            ExecutionState.INFERENCE,
        ),
    ],
)
def test_invalid_transition_is_rejected(
    start: ExecutionState,
    target: ExecutionState,
) -> None:
    machine = ExecutionStateMachine(
        state=start
    )

    assert not machine.can_transition_to(
        target
    )

    with pytest.raises(
        InvalidStateTransition,
        match="Invalid execution state transition",
    ):
        machine.transition_to(target)


@pytest.mark.parametrize(
    "state",
    [
        ExecutionState.PLANNING,
        ExecutionState.INFERENCE,
        ExecutionState.TOOL_EXECUTION,
        ExecutionState.OBSERVING,
    ],
)
def test_active_states_can_fail(
    state: ExecutionState,
) -> None:
    machine = ExecutionStateMachine(
        state=state
    )

    machine.transition_to(
        ExecutionState.FAILED
    )

    assert machine.state is ExecutionState.FAILED
    assert machine.is_terminal


@pytest.mark.parametrize(
    "state",
    [
        ExecutionState.PLANNING,
        ExecutionState.INFERENCE,
        ExecutionState.TOOL_EXECUTION,
        ExecutionState.OBSERVING,
    ],
)
def test_active_states_can_be_cancelled(
    state: ExecutionState,
) -> None:
    machine = ExecutionStateMachine(
        state=state
    )

    machine.transition_to(
        ExecutionState.CANCELLED
    )

    assert machine.state is ExecutionState.CANCELLED
    assert machine.is_terminal


def test_terminal_states_have_no_outgoing_transitions() -> None:
    for state in (
        ExecutionState.COMPLETED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    ):
        machine = ExecutionStateMachine(
            state=state
        )

        assert machine.is_terminal

        for target in ExecutionState:
            assert not machine.can_transition_to(
                target
            )
