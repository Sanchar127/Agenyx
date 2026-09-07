from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
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
from app.db.session import engine


pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """
    Provide an isolated PostgreSQL session for each test.

    Each test receives its own explicit database transaction.
    The transaction is rolled back after the test so no test
    data persists in PostgreSQL.

    The engine pool is disposed before and after each test to
    prevent asyncpg connections from being reused across
    pytest event-loop boundaries.
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
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="completed",
        status="completed",
        created_at=now,
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
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    events = [
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=1,
            type="execution_started",
            data={"step": 1},
            created_at=now,
        ),
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=2,
            type="step_started",
            data={"step": 2},
            created_at=now,
        ),
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=3,
            type="step_completed",
            data={"step": 2},
            created_at=now,
        ),
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
async def test_event_store_rejects_duplicate_sequence(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    first = ExecutionEventRecord(
        event_id=uuid4(),
        execution_id=execution_id,
        sequence=1,
        type="first",
        created_at=now,
    )

    duplicate = ExecutionEventRecord(
        event_id=uuid4(),
        execution_id=execution_id,
        sequence=1,
        type="duplicate",
        created_at=now,
    )

    await store.append(first)

    with pytest.raises(ValueError, match="already exists"):
        await store.append(duplicate)


@pytest.mark.asyncio
async def test_execution_event_store_lists_events_after_sequence(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    events = [
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=1,
            type="first",
            created_at=now,
        ),
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=2,
            type="second",
            created_at=now,
        ),
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=3,
            type="third",
            created_at=now,
        ),
    ]

    await store.append_many(events)

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
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    events = [
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=3,
            type="third",
            created_at=now,
        ),
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=1,
            type="first",
            created_at=now,
        ),
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=2,
            type="second",
            created_at=now,
        ),
    ]

    await store.append_many(events)

    loaded = await store.list(execution_id)

    assert [event.sequence for event in loaded] == [1, 2, 3]
    assert [event.type for event in loaded] == [
        "first",
        "second",
        "third",
    ]


@pytest.mark.asyncio
async def test_execution_event_store_rejects_sequence_gap(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    events = [
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=1,
            type="first",
            created_at=now,
        ),
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=3,
            type="third",
            created_at=now,
        ),
    ]

    with pytest.raises(ValueError):
        await store.append_many(events)


@pytest.mark.asyncio
async def test_execution_event_store_rejects_duplicate_sequence_in_batch(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    events = [
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=1,
            type="first",
            created_at=now,
        ),
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=1,
            type="duplicate",
            created_at=now,
        ),
    ]

    with pytest.raises(ValueError):
        await store.append_many(events)


@pytest.mark.asyncio
async def test_execution_event_store_rejects_batch_starting_after_existing_sequence(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    await create_test_execution(db_session, execution_id)

    store = PostgreSQLExecutionEventStore(db_session)

    await store.append(
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=1,
            type="first",
            created_at=now,
        )
    )

    events = [
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=3,
            type="third",
            created_at=now,
        ),
    ]

    with pytest.raises(ValueError):
        await store.append_many(events)


@pytest.mark.asyncio
async def test_execution_event_store_rejects_invalid_after_sequence(
    db_session: AsyncSession,
) -> None:
    store = PostgreSQLExecutionEventStore(db_session)

    with pytest.raises(ValueError):
        await store.list(uuid4(), after_sequence=-1)


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

    # The fixture will roll the transaction back after this test.
    # Therefore the execution must not exist when the next test
    # uses a fresh transaction.


@pytest.mark.asyncio
async def test_persistence_data_isolation_between_tests(
    db_session: AsyncSession,
) -> None:
    """
    Verify that tests do not depend on data persisted by previous tests.

    This uses a fresh UUID, so the test should always see no execution.
    """
    execution_id = uuid4()

    store = PostgreSQLExecutionStore(db_session)

    loaded = await store.get(execution_id)

    assert loaded is None


# ---------------------------------------------------------------------------
# Foreign Key Enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_store_rejects_missing_execution(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    store = PostgreSQLExecutionEventStore(db_session)

    event = ExecutionEventRecord(
        event_id=uuid4(),
        execution_id=execution_id,
        sequence=1,
        type="execution_started",
        created_at=now,
    )

    with pytest.raises(IntegrityError):
        await store.append(event)


@pytest.mark.asyncio
async def test_result_store_rejects_missing_execution(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    store = PostgreSQLExecutionResultStore(db_session)

    result = ExecutionResultRecord(
        execution_id=execution_id,
        status="completed",
        output={"result": "ok"},
        created_at=now,
        completed_at=now,
    )

    with pytest.raises(IntegrityError):
        await store.save(result)
