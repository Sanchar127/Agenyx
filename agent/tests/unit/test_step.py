from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.agent_runtime.domain.step import Step
from app.agent_runtime.domain.step_status import StepStatus
from app.agent_runtime.domain.step_type import StepType


def test_step_defaults() -> None:
    step = Step(
        number=1,
    )

    assert step.number == 1
    assert step.type is StepType.PLAN
    assert step.status is StepStatus.CREATED

    assert step.input is None
    assert step.output is None
    assert step.error is None

    assert step.started_at is None
    assert step.completed_at is None


def test_step_rejects_zero_number() -> None:
    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        Step(number=0)


def test_step_rejects_negative_number() -> None:
    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        Step(number=-1)


def test_step_has_unique_ids() -> None:
    first = Step(number=1)
    second = Step(number=2)

    assert first.step_id != second.step_id


def test_step_can_start() -> None:
    step = Step(
        number=1,
        type=StepType.INFERENCE,
    )

    step.mark_started()

    assert step.status is StepStatus.RUNNING
    assert step.started_at is not None
    assert step.completed_at is None


def test_step_start_does_not_replace_started_at() -> None:
    step = Step(number=1)

    step.mark_started()

    first_started_at = step.started_at

    step.mark_started()

    assert step.started_at == first_started_at


def test_step_can_complete() -> None:
    step = Step(
        number=1,
        type=StepType.INFERENCE,
        input={"model": "test-model"},
    )

    step.mark_started()
    step.mark_completed(
        output={
            "answer": "hello",
        }
    )

    assert step.status is StepStatus.COMPLETED

    assert step.output == {
        "answer": "hello",
    }

    assert step.completed_at is not None


def test_step_can_fail() -> None:
    step = Step(
        number=1,
        type=StepType.TOOL_CALL,
    )

    step.mark_started()

    step.mark_failed(
        error="Tool execution failed",
    )

    assert step.status is StepStatus.FAILED
    assert step.error == "Tool execution failed"
    assert step.completed_at is not None


def test_step_rejects_empty_failure() -> None:
    step = Step(number=1)

    with pytest.raises(
        ValueError,
        match="cannot be empty",
    ):
        step.mark_failed(error="")


def test_step_can_be_cancelled() -> None:
    step = Step(number=1)

    step.mark_started()
    step.mark_cancelled()

    assert step.status is StepStatus.CANCELLED
    assert step.completed_at is not None


def test_step_duration() -> None:
    step = Step(number=1)

    start = datetime.now(timezone.utc)
    end = start + timedelta(seconds=2.5)

    step.started_at = start
    step.completed_at = end

    assert step.duration_seconds == pytest.approx(2.5)


def test_step_duration_is_none_when_not_started() -> None:
    step = Step(number=1)

    assert step.duration_seconds is None


def test_step_duration_is_none_when_not_completed() -> None:
    step = Step(number=1)

    step.mark_started()

    assert step.duration_seconds is None


def test_step_status_properties() -> None:
    completed = Step(number=1)
    completed.mark_started()
    completed.mark_completed(output="done")

    assert completed.is_completed
    assert not completed.is_failed
    assert not completed.is_cancelled

    failed = Step(number=2)
    failed.mark_started()
    failed.mark_failed(error="failed")

    assert failed.is_failed
    assert not failed.is_completed
    assert not failed.is_cancelled

    cancelled = Step(number=3)
    cancelled.mark_started()
    cancelled.mark_cancelled()

    assert cancelled.is_cancelled
    assert not cancelled.is_completed
    assert not cancelled.is_failed


def test_execution_can_store_steps() -> None:
    from app.agent_runtime.domain.execution import Execution

    execution = Execution()

    step = Step(
        number=1,
        type=StepType.PLAN,
    )

    execution.add_step(step)

    assert len(execution.steps) == 1
    assert execution.steps[0] is step


def test_execution_steps_are_independent() -> None:
    from app.agent_runtime.domain.execution import Execution

    first = Execution()
    second = Execution()

    first.add_step(
        Step(number=1)
    )

    assert len(first.steps) == 1
    assert len(second.steps) == 0
