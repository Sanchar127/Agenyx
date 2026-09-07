from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.persistence.models import (
    ExecutionEventRecord,
    ExecutionRecord,
    ExecutionResultRecord,
    StepRecord,
)
from app.agent_runtime.persistence.postgres import (
    PostgreSQLExecutionEventStore,
    PostgreSQLExecutionResultStore,
    PostgreSQLExecutionStore,
)
from app.db.models import (
    ExecutionEventModel,
    ExecutionModel,
    ExecutionResultModel,
    StepModel,
)
from app.db.session import engine

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """
    Provide one isolated database transaction per test.

    The fixture uses the same function-scoped event loop as the test so
    asyncpg connections are never reused across different event loops.

    Production stores only flush changes. Transaction ownership remains
    with the caller, so the fixture owns rollback.
    """
    await engine.dispose()

    async with engine.connect() as connection:
        transaction = await connection.begin()

        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
        )

        try:
            yield session
        finally:
            if transaction.is_active:
                await transaction.rollback()

            await session.close()

    await engine.dispose()


async def create_test_execution(
    db_session: AsyncSession,
    execution_id: UUID,
) -> ExecutionRecord:
    """
    Create a parent execution required by steps, results, and events.
    """
    now = datetime.now(timezone.utc)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        created_at=now,
    )

    store = PostgreSQLExecutionStore(db_session)
    await store.create(execution)

    return execution


def make_event(
    execution_id: UUID,
    sequence: int,
    event_type: str = "test.event",
    data: dict | None = None,
) -> ExecutionEventRecord:
    """
    Create a test event with a unique event ID.
    """
    return ExecutionEventRecord(
        event_id=uuid4(),
        execution_id=execution_id,
        sequence=sequence,
        type=event_type,
        data=data or {},
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Execution Store
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execution_store_create_and_get(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        metadata={"source": "test"},
        created_at=now,
        started_at=now,
        steps=(
            StepRecord(
                step_id=uuid4(),
                number=1,
                type="tool_call",
                status="completed",
                input={"tool": "calculator"},
                output={"result": 42},
                started_at=now,
                completed_at=now,
            ),
        ),
    )

    store = PostgreSQLExecutionStore(db_session)

    await store.create(execution)

    loaded = await store.get(execution_id)

    assert loaded is not None
    assert loaded.execution_id == execution_id
    assert loaded.state == "running"
    assert loaded.status == "running"
    assert loaded.metadata == {"source": "test"}

    assert len(loaded.steps) == 1
    assert loaded.steps[0].number == 1
    assert loaded.steps[0].type == "tool_call"
    assert loaded.steps[0].input == {"tool": "calculator"}
    assert loaded.steps[0].output == {"result": 42}


@pytest.mark.asyncio
async def test_execution_store_get_returns_none_for_missing_execution(
    db_session: AsyncSession,
) -> None:
    store = PostgreSQLExecutionStore(db_session)

    loaded = await store.get(uuid4())

    assert loaded is None


@pytest.mark.asyncio
async def test_execution_store_update(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        metadata={"attempt": 1},
        created_at=now,
        started_at=now,
        steps=(
            StepRecord(
                step_id=uuid4(),
                number=1,
                type="tool_call",
                status="running",
                input={"tool": "search"},
                started_at=now,
            ),
        ),
    )

    store = PostgreSQLExecutionStore(db_session)

    await store.create(execution)

    step_id = execution.steps[0].step_id

    updated = ExecutionRecord(
        execution_id=execution_id,
        state="completed",
        status="completed",
        metadata={"attempt": 1, "updated": True},
        created_at=now,
        started_at=now,
        completed_at=now,
        steps=(
            StepRecord(
                step_id=step_id,
                number=1,
                type="tool_call",
                status="completed",
                input={"tool": "search"},
                output={"result": "success"},
                started_at=now,
                completed_at=now,
            ),
            StepRecord(
                step_id=uuid4(),
                number=2,
                type="tool_call",
                status="completed",
                input={"tool": "calculator"},
                output={"result": 100},
                started_at=now,
                completed_at=now,
            ),
        ),
    )

    await store.update(updated)

    loaded = await store.get(execution_id)

    assert loaded is not None
    assert loaded.state == "completed"
    assert loaded.status == "completed"
    assert loaded.metadata == {
        "attempt": 1,
        "updated": True,
    }
    assert loaded.completed_at == now

    assert len(loaded.steps) == 2
    assert loaded.steps[0].number == 1
    assert loaded.steps[0].status == "completed"
    assert loaded.steps[0].output == {"result": "success"}

    assert loaded.steps[1].number == 2
    assert loaded.steps[1].output == {"result": 100}


@pytest.mark.asyncio
async def test_execution_store_update_removes_deleted_steps(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    first_step_id = uuid4()
    second_step_id = uuid4()

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        created_at=now,
        steps=(
            StepRecord(
                step_id=first_step_id,
                number=1,
                type="tool_call",
                status="completed",
                output={"result": 1},
                started_at=now,
                completed_at=now,
            ),
            StepRecord(
                step_id=second_step_id,
                number=2,
                type="tool_call",
                status="completed",
                output={"result": 2},
                started_at=now,
                completed_at=now,
            ),
        ),
    )

    store = PostgreSQLExecutionStore(db_session)

    await store.create(execution)

    updated = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        created_at=now,
        steps=(
            StepRecord(
                step_id=first_step_id,
                number=1,
                type="tool_call",
                status="completed",
                output={"result": 100},
                started_at=now,
                completed_at=now,
            ),
        ),
    )

    await store.update(updated)

    loaded = await store.get(execution_id)

    assert loaded is not None
    assert len(loaded.steps) == 1
    assert loaded.steps[0].step_id == first_step_id
    assert loaded.steps[0].output == {"result": 100}


@pytest.mark.asyncio
async def test_execution_store_update_rejects_missing_execution(
    db_session: AsyncSession,
) -> None:
    execution = ExecutionRecord(
        execution_id=uuid4(),
        state="completed",
        status="completed",
        created_at=datetime.now(timezone.utc),
    )

    store = PostgreSQLExecutionStore(db_session)

    with pytest.raises(ValueError):
        await store.update(execution)


@pytest.mark.asyncio
async def test_execution_store_rejects_duplicate_execution_id(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        created_at=now,
    )

    store = PostgreSQLExecutionStore(db_session)

    await store.create(execution)

    with pytest.raises(ValueError):
        await store.create(execution)


@pytest.mark.asyncio
async def test_execution_store_rejects_duplicate_step_number(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        created_at=now,
        steps=(
            StepRecord(
                step_id=uuid4(),
                number=1,
                type="tool_call",
                status="completed",
                input={"tool": "first"},
                output={"result": "ok"},
                started_at=now,
                completed_at=now,
            ),
            StepRecord(
                step_id=uuid4(),
                number=1,
                type="tool_call",
                status="completed",
                input={"tool": "second"},
                output={"result": "ok"},
                started_at=now,
                completed_at=now,
            ),
        ),
    )

    store = PostgreSQLExecutionStore(db_session)

    with pytest.raises(IntegrityError):
        await store.create(execution)


@pytest.mark.asyncio
async def test_execution_store_round_trips_nested_json_metadata(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    metadata = {
        "request": {
            "source": "api",
            "user": {
                "id": "user-123",
                "roles": ["admin", "developer"],
            },
        },
        "limits": {
            "max_steps": 8,
            "timeout": 30.5,
        },
        "tags": ["production", "agent"],
    }

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        metadata=metadata,
        created_at=now,
    )

    store = PostgreSQLExecutionStore(db_session)

    await store.create(execution)

    loaded = await store.get(execution_id)

    assert loaded is not None
    assert loaded.metadata == metadata


@pytest.mark.asyncio
async def test_execution_store_round_trips_nullable_fields(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)  # Add this

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="pending",
        status="pending",
        metadata={},
        error=None,
        error_type=None,
        created_at=now,  # Change this - provide a value
        started_at=None,
        completed_at=None,
    )

    store = PostgreSQLExecutionStore(db_session)

    await store.create(execution)

    loaded = await store.get(execution_id)

    assert loaded is not None
    assert loaded.error is None
    assert loaded.error_type is None
    assert loaded.created_at == now  # Verify it was set correctly
    assert loaded.started_at is None
    assert loaded.completed_at is None

# ---------------------------------------------------------------------------
# Result Store
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execution_result_store_save_and_get(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    result = ExecutionResultRecord(
        execution_id=execution_id,
        status="completed",
        output={"answer": 42},
        metadata={"model": "test-model"},
        created_at=now,
        started_at=now,
        completed_at=now,
        duration_seconds=1.25,
    )

    store = PostgreSQLExecutionResultStore(db_session)

    await store.save(result)

    loaded = await store.get(execution_id)

    assert loaded is not None
    assert loaded.execution_id == execution_id
    assert loaded.status == "completed"
    assert loaded.output == {"answer": 42}
    assert loaded.metadata == {"model": "test-model"}
    assert loaded.duration_seconds == 1.25


@pytest.mark.asyncio
async def test_execution_result_store_get_returns_none_for_missing_result(
    db_session: AsyncSession,
) -> None:
    store = PostgreSQLExecutionResultStore(db_session)

    loaded = await store.get(uuid4())

    assert loaded is None


@pytest.mark.asyncio
async def test_execution_result_store_updates_existing_result(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionResultStore(db_session)

    first = ExecutionResultRecord(
        execution_id=execution_id,
        status="completed",
        output={"value": "first"},
        created_at=now,
        completed_at=now,
    )

    second = ExecutionResultRecord(
        execution_id=execution_id,
        status="completed",
        output={"value": "second"},
        metadata={"updated": True},
        created_at=now,
        completed_at=now,
    )

    await store.save(first)
    await store.save(second)

    loaded = await store.get(execution_id)

    assert loaded is not None
    assert loaded.execution_id == execution_id
    assert loaded.output == {"value": "second"}
    assert loaded.metadata == {"updated": True}


@pytest.mark.asyncio
async def test_execution_result_store_round_trips_nested_json(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    output = {
        "answer": {
            "text": "hello",
            "confidence": 0.98,
        },
        "tool_results": [
            {
                "tool": "calculator",
                "result": 42,
            },
            {
                "tool": "search",
                "result": ["a", "b", "c"],
            },
        ],
    }

    result = ExecutionResultRecord(
        execution_id=execution_id,
        status="completed",
        output=output,
        metadata={
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
            },
        },
        created_at=now,
        completed_at=now,
        duration_seconds=2.5,
    )

    store = PostgreSQLExecutionResultStore(db_session)

    await store.save(result)

    loaded = await store.get(execution_id)

    assert loaded is not None
    assert loaded.output == output
    assert loaded.metadata == {
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
        },
    }


@pytest.mark.asyncio
async def test_execution_result_store_rejects_missing_execution(
    db_session: AsyncSession,
) -> None:
    result = ExecutionResultRecord(
        execution_id=uuid4(),
        status="completed",
        output={"result": "ok"},
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )

    store = PostgreSQLExecutionResultStore(db_session)

    with pytest.raises(IntegrityError):
        await store.save(result)


# ---------------------------------------------------------------------------
# Event Store
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execution_event_store_append_and_list(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    event = ExecutionEventRecord(
        event_id=uuid4(),
        execution_id=execution_id,
        sequence=1,
        type="execution_started",
        data={"foo": "bar"},
        created_at=now,
    )

    await store.append(event)

    events = await store.list(execution_id)

    assert len(events) == 1
    assert events[0].event_id == event.event_id
    assert events[0].execution_id == execution_id
    assert events[0].sequence == 1
    assert events[0].type == "execution_started"
    assert events[0].data == {"foo": "bar"}


@pytest.mark.asyncio
async def test_execution_event_store_append_many(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    events = [
        make_event(execution_id, 1, "execution_started", {"step": 1}),
        make_event(execution_id, 2, "step_started", {"step": 2}),
        make_event(execution_id, 3, "step_completed", {"step": 2}),
    ]

    await store.append_many(events)

    loaded = await store.list(execution_id)

    assert [event.sequence for event in loaded] == [1, 2, 3]
    assert [event.type for event in loaded] == [
        "execution_started",
        "step_started",
        "step_completed",
    ]


@pytest.mark.asyncio
async def test_execution_event_store_lists_events_after_sequence(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    await store.append_many(
        [
            make_event(execution_id, 1, "first"),
            make_event(execution_id, 2, "second"),
            make_event(execution_id, 3, "third"),
        ]
    )

    loaded = await store.list(
        execution_id,
        after_sequence=1,
    )

    assert [event.sequence for event in loaded] == [2, 3]


@pytest.mark.asyncio
async def test_execution_event_store_returns_events_in_sequence_order(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    await store.append_many(
        [
            make_event(execution_id, 3, "third"),
            make_event(execution_id, 1, "first"),
            make_event(execution_id, 2, "second"),
        ]
    )

    loaded = await store.list(execution_id)

    assert [event.sequence for event in loaded] == [1, 2, 3]
    assert [event.type for event in loaded] == [
        "first",
        "second",
        "third",
    ]


@pytest.mark.asyncio
async def test_event_store_rejects_duplicate_sequence(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    first = make_event(execution_id, 1, "first")
    duplicate = make_event(execution_id, 1, "duplicate")

    await store.append(first)

    with pytest.raises(ValueError, match="already exists"):
        await store.append(duplicate)


@pytest.mark.asyncio
async def test_execution_event_store_rejects_sequence_gap(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    events = [
        make_event(execution_id, 1, "first"),
        make_event(execution_id, 3, "third"),
    ]

    with pytest.raises(ValueError, match="contiguous"):
        await store.append_many(events)


@pytest.mark.asyncio
async def test_execution_event_store_rejects_duplicate_sequence_in_batch(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    events = [
        make_event(execution_id, 1, "first"),
        make_event(execution_id, 1, "duplicate"),
    ]

    with pytest.raises(ValueError, match="contiguous"):
        await store.append_many(events)


@pytest.mark.asyncio
async def test_execution_event_store_rejects_batch_starting_after_existing_sequence(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    await store.append(
        make_event(execution_id, 1, "first")
    )

    with pytest.raises(ValueError, match="contiguous"):
        await store.append_many(
            [
                make_event(execution_id, 3, "third"),
            ]
        )


@pytest.mark.asyncio
async def test_execution_event_store_rejects_invalid_after_sequence(
    db_session: AsyncSession,
) -> None:
    store = PostgreSQLExecutionEventStore(db_session)

    with pytest.raises(ValueError, match="after_sequence"):
        await store.list(uuid4(), after_sequence=-1)


@pytest.mark.asyncio
async def test_append_many_rejects_invalid_batch_without_partial_persistence(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    events = [
        make_event(execution_id, 1, "step.started", {"step": 1}),
        make_event(execution_id, 3, "step.completed", {"step": 1}),
    ]

    with pytest.raises(ValueError, match="contiguous"):
        await store.append_many(events)

    persisted = await store.list(execution_id)

    assert persisted == []


@pytest.mark.asyncio
async def test_append_many_does_not_modify_existing_events_when_batch_is_invalid(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    await store.append(
        make_event(execution_id, 1, "execution.started")
    )

    with pytest.raises(ValueError, match="contiguous"):
        await store.append_many(
            [
                make_event(execution_id, 2, "step.started"),
                make_event(execution_id, 4, "step.completed"),
            ]
        )

    persisted = await store.list(execution_id)

    assert [event.sequence for event in persisted] == [1]
    assert [event.type for event in persisted] == [
        "execution.started"
    ]


@pytest.mark.asyncio
async def test_execution_event_store_rejects_duplicate_event_id(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    event_id = uuid4()

    first = ExecutionEventRecord(
        event_id=event_id,
        execution_id=execution_id,
        sequence=1,
        type="first",
        created_at=datetime.now(timezone.utc),
    )

    second = ExecutionEventRecord(
        event_id=event_id,
        execution_id=execution_id,
        sequence=2,
        type="second",
        created_at=datetime.now(timezone.utc),
    )

    await store.append(first)

    with pytest.raises(IntegrityError):
        await store.append(second)


@pytest.mark.asyncio
async def test_execution_event_store_round_trips_nested_json_data(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    data = {
        "tool": {
            "name": "calculator",
            "arguments": {
                "a": 10,
                "b": 32,
            },
        },
        "result": {
            "value": 42,
            "metadata": {
                "cached": False,
                "sources": ["runtime", "tool"],
            },
        },
    }

    await store.append(
        make_event(
            execution_id,
            1,
            "tool.completed",
            data,
        )
    )

    loaded = await store.list(execution_id)

    assert len(loaded) == 1
    assert loaded[0].data == data


@pytest.mark.asyncio
async def test_event_store_rejects_missing_execution(
    db_session: AsyncSession,
) -> None:
    event = ExecutionEventRecord(
        event_id=uuid4(),
        execution_id=uuid4(),
        sequence=1,
        type="execution_started",
        created_at=datetime.now(timezone.utc),
    )

    store = PostgreSQLExecutionEventStore(db_session)

    with pytest.raises(IntegrityError):
        await store.append(event)


# ---------------------------------------------------------------------------
# Transaction / Isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transaction_isolation_and_rollback(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()

    store = PostgreSQLExecutionStore(db_session)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        created_at=datetime.now(timezone.utc),
    )

    await store.create(execution)

    loaded_inside_transaction = await store.get(execution_id)

    assert loaded_inside_transaction is not None
    assert loaded_inside_transaction.execution_id == execution_id

    await db_session.flush()

    # The fixture rolls the transaction back after this test.


@pytest.mark.asyncio
async def test_persistence_data_isolation_between_tests(
    db_session: AsyncSession,
) -> None:
    """
    Verify that tests do not depend on data persisted by previous tests.
    """
    execution_id = uuid4()

    store = PostgreSQLExecutionStore(db_session)

    loaded = await store.get(execution_id)

    assert loaded is None


# ---------------------------------------------------------------------------
# Cascade Delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deleting_execution_cascades_to_children(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        created_at=now,
        steps=(
            StepRecord(
                step_id=uuid4(),
                number=1,
                type="tool",
                status="completed",
                input={"command": "echo hello"},
                output={"stdout": "hello"},
                started_at=now,
                completed_at=now,
            ),
        ),
    )

    execution_store = PostgreSQLExecutionStore(db_session)
    await execution_store.create(execution)

    result_store = PostgreSQLExecutionResultStore(db_session)

    await result_store.save(
        ExecutionResultRecord(
            execution_id=execution_id,
            status="completed",
            output={"result": "hello"},
            created_at=now,
            completed_at=now,
        )
    )

    event_store = PostgreSQLExecutionEventStore(db_session)

    await event_store.append_many(
        [
            make_event(execution_id, 1, "execution.started"),
            make_event(execution_id, 2, "execution.completed"),
        ]
    )

    await db_session.flush()

    execution_model = await db_session.get(
        ExecutionModel,
        execution_id,
    )

    assert execution_model is not None

    await db_session.delete(execution_model)
    await db_session.flush()

    assert await db_session.get(
        ExecutionModel,
        execution_id,
    ) is None

    steps = await db_session.execute(
        select(StepModel).where(
            StepModel.execution_id == execution_id,
        )
    )

    assert steps.scalars().all() == []

    result = await db_session.execute(
        select(ExecutionResultModel).where(
            ExecutionResultModel.execution_id == execution_id,
        )
    )

    assert result.scalar_one_or_none() is None

    events = await db_session.execute(
        select(ExecutionEventModel).where(
            ExecutionEventModel.execution_id == execution_id,
        )
    )

    assert events.scalars().all() == []
