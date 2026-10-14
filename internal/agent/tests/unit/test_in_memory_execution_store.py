from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.agent_runtime.domain import (
    Execution,
    ExecutionState,
    ExecutionResult,
    ExecutionStatus,
)
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.persistence.in_memory import (
    InMemoryExecutionEventStore,
    InMemoryExecutionResultStore,
    InMemoryExecutionStore,
)
from app.agent_runtime.persistence.mappers import (
    event_to_record,
    execution_to_record,
    result_to_record,
)


@pytest.mark.asyncio
async def test_create_and_get_execution() -> None:
    store = InMemoryExecutionStore()

    execution = Execution(
        id=uuid4(),
        metadata={"task": "calculate"},
    )

    record = execution_to_record(execution)

    await store.create(record)

    stored = await store.get(execution.id)

    assert stored is not None
    assert stored.execution_id == execution.id
    assert stored.metadata == {"task": "calculate"}
    assert stored.state == ExecutionState.CREATED.value


@pytest.mark.asyncio
async def test_get_unknown_execution_returns_none() -> None:
    store = InMemoryExecutionStore()

    result = await store.get(uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_create_rejects_duplicate_execution() -> None:
    store = InMemoryExecutionStore()

    execution = Execution(id=uuid4())
    record = execution_to_record(execution)

    await store.create(record)

    with pytest.raises(ValueError, match="already exists"):
        await store.create(record)


@pytest.mark.asyncio
async def test_update_existing_execution() -> None:
    store = InMemoryExecutionStore()

    execution = Execution(
        id=uuid4(),
        metadata={"task": "calculate"},
    )

    record = execution_to_record(execution)

    await store.create(record)

    execution.mark_started()
    execution.transition_to(ExecutionState.INFERENCE)

    updated_record = execution_to_record(execution)

    await store.update(updated_record)

    stored = await store.get(execution.id)

    assert stored is not None
    assert stored.state == ExecutionState.INFERENCE.value
    assert stored.status == "running"


@pytest.mark.asyncio
async def test_update_unknown_execution_is_rejected() -> None:
    store = InMemoryExecutionStore()

    execution = Execution(id=uuid4())
    record = execution_to_record(execution)

    with pytest.raises(ValueError, match="does not exist"):
        await store.update(record)


@pytest.mark.asyncio
async def test_save_and_get_execution_result() -> None:
    store = InMemoryExecutionResultStore()

    execution_id = uuid4()

    result = ExecutionResult(
        execution_id=execution_id,
        status=ExecutionStatus.COMPLETED,
        output={"answer": 42},
    )

    record = result_to_record(result)

    await store.save(record)

    stored = await store.get(execution_id)

    assert stored is not None
    assert stored.execution_id == execution_id
    assert stored.status == ExecutionStatus.COMPLETED.value
    assert stored.output == {"answer": 42}


@pytest.mark.asyncio
async def test_get_unknown_result_returns_none() -> None:
    store = InMemoryExecutionResultStore()

    result = await store.get(uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_result_save_is_idempotent() -> None:
    store = InMemoryExecutionResultStore()

    execution_id = uuid4()

    first = ExecutionResult(
        execution_id=execution_id,
        status=ExecutionStatus.COMPLETED,
        output={"answer": 42},
    )

    second = ExecutionResult(
        execution_id=execution_id,
        status=ExecutionStatus.COMPLETED,
        output={"answer": 42},
    )

    await store.save(result_to_record(first))
    await store.save(result_to_record(second))

    stored = await store.get(execution_id)

    assert stored is not None
    assert stored.output == {"answer": 42}


@pytest.mark.asyncio
async def test_append_and_list_events() -> None:
    store = InMemoryExecutionEventStore()

    execution_id = uuid4()

    event1 = event_to_record(
        AgentEvent(
            type="execution.started",
            execution_id=str(execution_id),
        ),
        sequence=1,
    )

    event2 = event_to_record(
        AgentEvent(
            type="planning.started",
            execution_id=str(execution_id),
        ),
        sequence=2,
    )

    await store.append(event1)
    await store.append(event2)

    events = await store.list(execution_id)

    assert len(events) == 2
    assert events[0].sequence == 1
    assert events[1].sequence == 2
    assert events[0].type == "execution.started"
    assert events[1].type == "planning.started"


@pytest.mark.asyncio
async def test_list_events_after_sequence() -> None:
    store = InMemoryExecutionEventStore()

    execution_id = uuid4()

    for sequence in range(1, 6):
        event = event_to_record(
            AgentEvent(
                type=f"event.{sequence}",
                execution_id=str(execution_id),
            ),
            sequence=sequence,
        )

        await store.append(event)

    events = await store.list(
        execution_id,
        after_sequence=3,
    )

    assert [event.sequence for event in events] == [4, 5]


@pytest.mark.asyncio
async def test_list_unknown_execution_returns_empty_list() -> None:
    store = InMemoryExecutionEventStore()

    events = await store.list(uuid4())

    assert events == []


@pytest.mark.asyncio
async def test_event_sequence_must_increase() -> None:
    store = InMemoryExecutionEventStore()

    execution_id = uuid4()

    first = event_to_record(
        AgentEvent(
            type="event.1",
            execution_id=str(execution_id),
        ),
        sequence=1,
    )

    duplicate = event_to_record(
        AgentEvent(
            type="event.duplicate",
            execution_id=str(execution_id),
        ),
        sequence=1,
    )

    await store.append(first)

    with pytest.raises(ValueError, match="sequence"):
        await store.append(duplicate)


@pytest.mark.asyncio
async def test_append_many_events() -> None:
    store = InMemoryExecutionEventStore()

    execution_id = uuid4()

    events = [
        event_to_record(
            AgentEvent(
                type=f"event.{sequence}",
                execution_id=str(execution_id),
            ),
            sequence=sequence,
        )
        for sequence in range(1, 4)
    ]

    await store.append_many(events)

    stored = await store.list(execution_id)

    assert [event.sequence for event in stored] == [1, 2, 3]


@pytest.mark.asyncio
async def test_append_many_rejects_invalid_batch() -> None:
    store = InMemoryExecutionEventStore()

    execution_id = uuid4()

    events = [
        event_to_record(
            AgentEvent(
                type="event.1",
                execution_id=str(execution_id),
            ),
            sequence=1,
        ),
        event_to_record(
            AgentEvent(
                type="event.2",
                execution_id=str(execution_id),
            ),
            sequence=1,
        ),
    ]

    with pytest.raises(ValueError, match="sequence"):
        await store.append_many(events)

    stored = await store.list(execution_id)

    assert stored == []


@pytest.mark.asyncio
async def test_append_many_rejects_batch_against_existing_events() -> None:
    store = InMemoryExecutionEventStore()

    execution_id = uuid4()

    existing = event_to_record(
        AgentEvent(
            type="event.1",
            execution_id=str(execution_id),
        ),
        sequence=1,
    )

    await store.append(existing)

    invalid_batch = [
        event_to_record(
            AgentEvent(
                type="event.2",
                execution_id=str(execution_id),
            ),
            sequence=2,
        ),
        event_to_record(
            AgentEvent(
                type="event.invalid",
                execution_id=str(execution_id),
            ),
            sequence=2,
        ),
    ]

    with pytest.raises(ValueError, match="sequence"):
        await store.append_many(invalid_batch)

    stored = await store.list(execution_id)

    assert [event.sequence for event in stored] == [1]


@pytest.mark.asyncio
async def test_events_are_isolated_between_executions() -> None:
    store = InMemoryExecutionEventStore()

    execution_a = uuid4()
    execution_b = uuid4()

    event_a = event_to_record(
        AgentEvent(
            type="event.a",
            execution_id=str(execution_a),
        ),
        sequence=1,
    )

    event_b = event_to_record(
        AgentEvent(
            type="event.b",
            execution_id=str(execution_b),
        ),
        sequence=1,
    )

    await store.append(event_a)
    await store.append(event_b)

    events_a = await store.list(execution_a)
    events_b = await store.list(execution_b)

    assert len(events_a) == 1
    assert len(events_b) == 1

    assert events_a[0].type == "event.a"
    assert events_b[0].type == "event.b"
