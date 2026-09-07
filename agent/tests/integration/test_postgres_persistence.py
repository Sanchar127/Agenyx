from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
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

    The test runs inside an explicit database transaction.
    The transaction is always rolled back after the test,
    ensuring that test data never persists.

    The SQLAlchemy engine pool is disposed before and after
    each test so asyncpg connections cannot leak across
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
            # Roll back the transaction while it is still
            # associated with the connection.
            if transaction.is_active:
                await transaction.rollback()

            await session.close()

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def dispose_database_pool():
    """
    Prevent asyncpg connections from surviving across
    pytest event loops.

    This only affects integration tests.
    Production continues using the normal SQLAlchemy pool.
    """
    await engine.dispose()

    yield

    await engine.dispose()


@pytest.mark.asyncio
async def test_execution_store_create_and_get(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    created_at = datetime.now(timezone.utc)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        metadata={"source": "integration-test"},
        created_at=created_at,
        started_at=created_at,
        steps=(
            StepRecord(
                step_id=uuid4(),
                number=1,
                type="tool",
                status="completed",
                input={"query": "hello"},
                output={"result": "world"},
                started_at=created_at,
                completed_at=created_at,
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
    assert loaded.metadata == {"source": "integration-test"}

    assert len(loaded.steps) == 1
    assert loaded.steps[0].number == 1
    assert loaded.steps[0].type == "tool"
    assert loaded.steps[0].status == "completed"
    assert loaded.steps[0].input == {"query": "hello"}
    assert loaded.steps[0].output == {"result": "world"}


@pytest.mark.asyncio
async def test_execution_store_update(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    step_id = uuid4()
    now = datetime.now(timezone.utc)

    store = PostgreSQLExecutionStore(db_session)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        metadata={"test": True},
        created_at=now,
        started_at=now,
        steps=(
            StepRecord(
                step_id=step_id,
                number=1,
                type="tool",
                status="running",
                input={"value": 1},
                started_at=now,
            ),
        ),
    )

    await store.create(execution)

    updated = ExecutionRecord(
        execution_id=execution_id,
        state="completed",
        status="completed",
        metadata={
            "test": True,
            "updated": True,
        },
        created_at=now,
        started_at=now,
        completed_at=now,
        steps=(
            StepRecord(
                step_id=step_id,
                number=1,
                type="tool",
                status="completed",
                input={"value": 1},
                output={"value": 2},
                started_at=now,
                completed_at=now,
            ),
        ),
    )

    await store.update(updated)

    loaded = await store.get(execution_id)

    assert loaded is not None
    assert loaded.execution_id == execution_id
    assert loaded.state == "completed"
    assert loaded.status == "completed"

    assert loaded.metadata["test"] is True
    assert loaded.metadata["updated"] is True

    assert loaded.created_at == now
    assert loaded.started_at == now
    assert loaded.completed_at == now

    assert len(loaded.steps) == 1
    assert loaded.steps[0].step_id == step_id
    assert loaded.steps[0].number == 1
    assert loaded.steps[0].status == "completed"
    assert loaded.steps[0].input == {"value": 1}
    assert loaded.steps[0].output == {"value": 2}


@pytest.mark.asyncio
async def test_execution_result_store_save_and_get(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution_store = PostgreSQLExecutionStore(db_session)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="completed",
        status="completed",
        metadata={},
        created_at=now,
        completed_at=now,
    )

    await execution_store.create(execution)

    result_store = PostgreSQLExecutionResultStore(db_session)

    result = ExecutionResultRecord(
        execution_id=execution_id,
        status="completed",
        output={"answer": 42},
        metadata={"model": "test-model"},
        created_at=now,
        completed_at=now,
        duration_seconds=1.25,
    )

    await result_store.save(result)

    loaded = await result_store.get(execution_id)

    assert loaded is not None
    assert loaded.execution_id == execution_id
    assert loaded.status == "completed"
    assert loaded.output == {"answer": 42}
    assert loaded.error is None
    assert loaded.error_type is None
    assert loaded.metadata == {"model": "test-model"}
    assert loaded.created_at == now
    assert loaded.completed_at == now
    assert loaded.duration_seconds == 1.25


@pytest.mark.asyncio
async def test_execution_event_store_append_and_list(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution_store = PostgreSQLExecutionStore(db_session)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        created_at=now,
    )

    await execution_store.create(execution)

    event_store = PostgreSQLExecutionEventStore(db_session)

    event = ExecutionEventRecord(
        event_id=uuid4(),
        execution_id=execution_id,
        sequence=1,
        type="execution.started",
        data={"message": "started"},
        created_at=now,
    )

    await event_store.append(event)

    events = await event_store.list(execution_id)

    assert len(events) == 1

    loaded = events[0]

    assert loaded.event_id == event.event_id
    assert loaded.execution_id == execution_id
    assert loaded.sequence == 1
    assert loaded.type == "execution.started"
    assert loaded.data == {"message": "started"}
    assert loaded.created_at == now


@pytest.mark.asyncio
async def test_execution_event_store_append_many(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution_store = PostgreSQLExecutionStore(db_session)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        created_at=now,
    )

    await execution_store.create(execution)

    event_store = PostgreSQLExecutionEventStore(db_session)

    events = [
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=1,
            type="execution.started",
            data={},
            created_at=now,
        ),
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=2,
            type="step.started",
            data={"step": 1},
            created_at=now,
        ),
        ExecutionEventRecord(
            event_id=uuid4(),
            execution_id=execution_id,
            sequence=3,
            type="step.completed",
            data={"step": 1},
            created_at=now,
        ),
    ]

    await event_store.append_many(events)

    loaded = await event_store.list(execution_id)

    assert len(loaded) == 3
    assert [event.sequence for event in loaded] == [1, 2, 3]

    assert loaded[0].type == "execution.started"
    assert loaded[1].type == "step.started"
    assert loaded[2].type == "step.completed"

    assert loaded[1].data == {"step": 1}
    assert loaded[2].data == {"step": 1}


@pytest.mark.asyncio
async def test_event_store_rejects_duplicate_sequence(
    db_session: AsyncSession,
) -> None:
    execution_id = uuid4()
    now = datetime.now(timezone.utc)

    execution_store = PostgreSQLExecutionStore(db_session)

    execution = ExecutionRecord(
        execution_id=execution_id,
        state="running",
        status="running",
        created_at=now,
    )

    await execution_store.create(execution)

    event_store = PostgreSQLExecutionEventStore(db_session)

    first_event = ExecutionEventRecord(
        event_id=uuid4(),
        execution_id=execution_id,
        sequence=1,
        type="execution.started",
        created_at=now,
    )

    await event_store.append(first_event)

    duplicate = ExecutionEventRecord(
        event_id=uuid4(),
        execution_id=execution_id,
        sequence=1,
        type="duplicate",
        created_at=now,
    )

    with pytest.raises(ValueError):
        await event_store.append(duplicate)

    await db_session.rollback()

ROLLBACK_TEST_EXECUTION_ID = uuid4()


@pytest.mark.asyncio
async def test_transaction_is_rolled_back_after_test(
    db_session: AsyncSession,
) -> None:
    """
    Create an execution without committing it.

    The fixture should roll back the transaction after this
    test finishes.
    """
    now = datetime.now(timezone.utc)

    store = PostgreSQLExecutionStore(db_session)

    execution = ExecutionRecord(
        execution_id=ROLLBACK_TEST_EXECUTION_ID,
        state="running",
        status="running",
        created_at=now,
    )

    await store.create(execution)

    loaded = await store.get(ROLLBACK_TEST_EXECUTION_ID)

    assert loaded is not None
    assert loaded.execution_id == ROLLBACK_TEST_EXECUTION_ID


@pytest.mark.asyncio
async def test_previous_test_data_was_rolled_back(
    db_session: AsyncSession,
) -> None:
    """
    The previous test inserted ROLLBACK_TEST_EXECUTION_ID.

    Because the fixture rolled back its transaction, this test
    must not be able to see that execution.
    """
    store = PostgreSQLExecutionStore(db_session)

    loaded = await store.get(ROLLBACK_TEST_EXECUTION_ID)

    assert loaded is None
