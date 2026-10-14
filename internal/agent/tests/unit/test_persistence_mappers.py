from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.agent_runtime.domain import (
    Execution,
    ExecutionResult,
    ExecutionState,
    ExecutionStatus,
    Step,
    StepStatus,
    StepType,
)
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.persistence.mappers import (
    event_to_record,
    execution_from_record,
    execution_to_record,
    result_from_record,
    result_to_record,
    step_from_record,
    step_to_record,
)
from app.agent_runtime.persistence.models import (
    ExecutionEventRecord,
    ExecutionRecord,
    ExecutionResultRecord,
    StepRecord,
)


def test_step_round_trip() -> None:
    started_at = datetime(
        2026,
        9,
        7,
        10,
        0,
        tzinfo=timezone.utc,
    )

    completed_at = datetime(
        2026,
        9,
        7,
        10,
        0,
        5,
        tzinfo=timezone.utc,
    )

    step = Step(
        step_id=uuid4(),
        number=1,
        type=StepType.TOOL_CALL,
        status=StepStatus.COMPLETED,
        input={"tool": "calculator", "arguments": {"a": 2, "b": 3}},
        output={"result": 5},
        started_at=started_at,
        completed_at=completed_at,
    )

    record = step_to_record(step)
    restored = step_from_record(record)

    assert restored.step_id == step.step_id
    assert restored.number == step.number
    assert restored.type is step.type
    assert restored.status is step.status
    assert restored.input == step.input
    assert restored.output == step.output
    assert restored.error == step.error
    assert restored.started_at == step.started_at
    assert restored.completed_at == step.completed_at


def test_failed_step_round_trip() -> None:
    step = Step(
        step_id=uuid4(),
        number=2,
        type=StepType.TOOL_CALL,
        status=StepStatus.FAILED,
        input={"tool": "calculator"},
        error="Tool execution failed",
    )

    record = step_to_record(step)
    restored = step_from_record(record)

    assert restored.step_id == step.step_id
    assert restored.status is StepStatus.FAILED
    assert restored.error == "Tool execution failed"


def test_execution_round_trip() -> None:
    created_at = datetime(
        2026,
        9,
        7,
        10,
        0,
        tzinfo=timezone.utc,
    )

    started_at = datetime(
        2026,
        9,
        7,
        10,
        0,
        1,
        tzinfo=timezone.utc,
    )

    step = Step(
        step_id=uuid4(),
        number=1,
        type=StepType.INFERENCE,
        status=StepStatus.COMPLETED,
        input={"prompt": "What is 2 + 2?"},
        output={"text": "4"},
        started_at=started_at,
        completed_at=datetime(
            2026,
            9,
            7,
            10,
            0,
            2,
            tzinfo=timezone.utc,
        ),
    )

    execution = Execution(
        id=uuid4(),
        status=ExecutionStatus.RUNNING,
        created_at=created_at,
        started_at=started_at,
        metadata={
            "session_id": "session-123",
            "model": "qwen2.5:7b",
        },
        steps=[step],
    )

    execution.state_machine.state = ExecutionState.OBSERVING

    record = execution_to_record(execution)
    restored = execution_from_record(record)

    # Identity
    assert restored.id == execution.id

    # Lifecycle state
    assert restored.state is ExecutionState.OBSERVING
    assert restored.status is ExecutionStatus.RUNNING

    # Timestamps
    assert restored.created_at == execution.created_at
    assert restored.started_at == execution.started_at
    assert restored.completed_at == execution.completed_at

    # Metadata
    assert restored.metadata == execution.metadata

    # Error information
    assert restored.error == execution.error
    assert restored.error_type == execution.error_type

    # Steps
    assert len(restored.steps) == 1

    restored_step = restored.steps[0]

    assert restored_step.step_id == step.step_id
    assert restored_step.number == step.number
    assert restored_step.type is StepType.INFERENCE
    assert restored_step.status is StepStatus.COMPLETED
    assert restored_step.input == step.input
    assert restored_step.output == step.output
    assert restored_step.started_at == step.started_at
    assert restored_step.completed_at == step.completed_at


def test_execution_round_trip_preserves_failed_state() -> None:
    execution = Execution(
        id=uuid4(),
        metadata={"task": "test"},
    )

    execution.mark_started()
    execution.mark_failed(
        error="Inference service unavailable",
        error_type="InferenceError",
    )

    record = execution_to_record(execution)
    restored = execution_from_record(record)

    assert restored.id == execution.id
    assert restored.state is ExecutionState.FAILED
    assert restored.status is ExecutionStatus.FAILED
    assert restored.error == "Inference service unavailable"
    assert restored.error_type == "InferenceError"


def test_execution_round_trip_preserves_cancelled_state() -> None:
    execution = Execution(
        id=uuid4(),
        metadata={"task": "test"},
    )

    execution.mark_started()
    execution.transition_to(ExecutionState.CANCELLED)

    record = execution_to_record(execution)
    restored = execution_from_record(record)

    assert restored.id == execution.id
    assert restored.state is ExecutionState.CANCELLED
    assert restored.status is ExecutionStatus.CANCELLED


def test_execution_result_round_trip() -> None:
    execution_id = uuid4()

    created_at = datetime(
        2026,
        9,
        7,
        10,
        0,
        tzinfo=timezone.utc,
    )

    completed_at = datetime(
        2026,
        9,
        7,
        10,
        0,
        3,
        tzinfo=timezone.utc,
    )

    result = ExecutionResult(
        execution_id=execution_id,
        status=ExecutionStatus.COMPLETED,
        output={"answer": 42},
        metadata={
            "model": "qwen2.5:7b",
            "tokens": 100,
        },
        created_at=created_at,
        started_at=created_at,
        completed_at=completed_at,
        duration_seconds=3.0,
    )

    record = result_to_record(result)
    restored = result_from_record(record)

    assert restored.execution_id == result.execution_id
    assert restored.status is ExecutionStatus.COMPLETED
    assert restored.output == result.output
    assert restored.error == result.error
    assert restored.error_type == result.error_type
    assert restored.metadata == result.metadata
    assert restored.created_at == result.created_at
    assert restored.started_at == result.started_at
    assert restored.completed_at == result.completed_at
    assert restored.duration_seconds == result.duration_seconds


def test_failed_execution_result_round_trip() -> None:
    result = ExecutionResult(
        execution_id=uuid4(),
        status=ExecutionStatus.FAILED,
        error="Tool timeout",
        error_type="ToolTimeoutError",
        metadata={"tool": "calculator"},
    )

    record = result_to_record(result)
    restored = result_from_record(record)

    assert restored.status is ExecutionStatus.FAILED
    assert restored.error == "Tool timeout"
    assert restored.error_type == "ToolTimeoutError"
    assert restored.metadata == {"tool": "calculator"}


def test_agent_event_to_persistence_record() -> None:
    execution_id = uuid4()

    event = AgentEvent(
        type="tool.completed",
        execution_id=str(execution_id),
        data={
            "tool": "calculator",
            "result": 5,
        },
    )

    event_id = uuid4()

    created_at = datetime(
        2026,
        9,
        7,
        10,
        0,
        tzinfo=timezone.utc,
    )

    record = event_to_record(
        event,
        sequence=7,
        event_id=event_id,
        created_at=created_at,
    )

    assert record.event_id == event_id
    assert record.execution_id == execution_id
    assert record.sequence == 7
    assert record.type == "tool.completed"
    assert record.data == {
        "tool": "calculator",
        "result": 5,
    }
    assert record.created_at == created_at


def test_event_sequence_must_be_positive() -> None:
    execution_id = uuid4()

    event = AgentEvent(
        type="execution.started",
        execution_id=str(execution_id),
    )

    try:
        event_to_record(
            event,
            sequence=0,
        )
    except ValueError as exc:
        assert "sequence" in str(exc).lower()
    else:
        raise AssertionError(
            "Expected ValueError for invalid event sequence"
        )
