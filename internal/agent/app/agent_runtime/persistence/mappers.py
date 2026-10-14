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
from app.agent_runtime.state_machine import ExecutionStateMachine
from app.agent_runtime.persistence.models import (
    ExecutionEventRecord,
    ExecutionRecord,
    ExecutionResultRecord,
    StepRecord,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


def step_to_record(step: Step) -> StepRecord:
    """
    Convert a domain Step into its durable representation.
    """

    return StepRecord(
        step_id=step.step_id,
        number=step.number,
        type=step.type.value,
        status=step.status.value,
        input=step.input,
        output=step.output,
        error=step.error,
        started_at=step.started_at,
        completed_at=step.completed_at,
    )


def step_from_record(record: StepRecord) -> Step:
    """
    Restore a domain Step from durable storage.
    """

    return Step(
        step_id=record.step_id,
        number=record.number,
        type=StepType(record.type),
        status=StepStatus(record.status),
        input=record.input,
        output=record.output,
        error=record.error,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def execution_to_record(
    execution: Execution,
) -> ExecutionRecord:
    """
    Convert a domain Execution into a durable snapshot.

    Only durable domain state is persisted.
    Runtime-only objects such as the state-machine object itself,
    cancellation tokens, asyncio tasks, event streams, etc. are excluded.
    """

    if execution.created_at is None:
        raise ValueError("Execution created_at cannot be None")

    return ExecutionRecord(
        execution_id=execution.id,
        state=execution.state.value,
        status=execution.status.value,
        metadata=dict(execution.metadata),
        error=execution.error,
        error_type=execution.error_type,
        created_at=execution.created_at,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        steps=tuple(
            step_to_record(step)
            for step in execution.steps
        ),
    )


def execution_from_record(
    record: ExecutionRecord,
) -> Execution:
    """
    Restore an Execution from durable storage.

    IMPORTANT:
    We restore the state machine directly instead of replaying
    lifecycle transitions. Replaying transitions could change
    timestamps or reject valid historical states.
    """

    if record.created_at is None:
        raise ValueError("Persisted execution is missing created_at")

    state = ExecutionState(record.state)
    status = ExecutionStatus(record.status)

    execution = Execution(
        id=record.execution_id,
        status=status,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        metadata=dict(record.metadata),
        error=record.error,
        error_type=record.error_type,
        steps=[
            step_from_record(step)
            for step in record.steps
        ],
    )

    execution.state_machine = ExecutionStateMachine(
        state=state,
    )

    return execution


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------


def result_to_record(
    result: ExecutionResult,
) -> ExecutionResultRecord:
    """
    Convert a domain ExecutionResult into a durable representation.
    """

    return ExecutionResultRecord(
        execution_id=result.execution_id,
        status=result.status.value,
        output=result.output,
        error=result.error,
        error_type=result.error_type,
        metadata=dict(result.metadata),
        created_at=result.created_at,
        started_at=result.started_at,
        completed_at=result.completed_at,
        duration_seconds=result.duration_seconds,
    )


def result_from_record(
    record: ExecutionResultRecord,
) -> ExecutionResult:
    """
    Restore an ExecutionResult from durable storage.
    """

    return ExecutionResult(
        execution_id=record.execution_id,
        status=ExecutionStatus(record.status),
        output=record.output,
        error=record.error,
        error_type=record.error_type,
        metadata=dict(record.metadata),
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        duration_seconds=record.duration_seconds,
    )


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def event_to_record(
    event: AgentEvent,
    *,
    sequence: int,
    event_id: UUID | None = None,
    created_at: datetime | None = None,
) -> ExecutionEventRecord:
    """
    Convert a live AgentEvent into an append-only durable event.

    AgentEvent intentionally does not own persistence concerns such as
    database IDs or sequence numbers, so those are supplied here.
    """

    return ExecutionEventRecord(
        event_id=event_id or uuid4(),
        execution_id=UUID(event.execution_id),
        sequence=sequence,
        type=event.type,
        data=dict(event.data),
        created_at=created_at or utc_now(),
    )
