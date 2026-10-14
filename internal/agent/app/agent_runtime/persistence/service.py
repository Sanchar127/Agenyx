from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.events import AgentEvent
from app.agent_runtime.persistence.mappers import (
    event_to_record,
    execution_to_record,
    result_to_record,
)
from app.agent_runtime.persistence.models import (
    ExecutionEventRecord,
    ExecutionRecord,
    ExecutionResultRecord,
)
from app.agent_runtime.persistence.postgres import (
    PostgreSQLExecutionEventStore,
    PostgreSQLExecutionResultStore,
    PostgreSQLExecutionStore,
)
from app.agent_runtime.domain.execution import Execution
from app.agent_runtime.domain.result import ExecutionResult


class ExecutionPersistence(Protocol):
    """
    Application-level persistence interface used by AgentRuntime.

    This abstraction deliberately hides SQLAlchemy sessions and
    PostgreSQL-specific store implementations from the runtime.
    """

    async def create_execution(
        self,
        execution: Execution,
    ) -> None:
        ...

    async def update_execution(
        self,
        execution: Execution,
    ) -> None:
        ...

    async def append_event(
        self,
        event: AgentEvent,
    ) -> None:
        ...

    async def save_result(
        self,
        result: ExecutionResult,
    ) -> None:
        ...


class PostgreSQLExecutionPersistence:
    """
    PostgreSQL-backed persistence coordinator.

    Each operation owns a short database transaction.

    The agent execution itself must NOT hold a PostgreSQL transaction
    open while waiting for LLMs, tools, approvals, or other external
    operations.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

        # Event sequences are local coordination state.
        #
        # The first event for an execution is initialized from
        # PostgreSQL. Subsequent events for that execution are
        # allocated locally.
        #
        # This is sufficient for the current single-runtime process.
        # Distributed sequence allocation can be introduced later
        # when crash recovery/distributed execution requires it.
        self._event_sequences: dict[UUID, int] = {}
        self._event_locks: dict[UUID, asyncio.Lock] = {}

    def _get_event_lock(
        self,
        execution_id: UUID,
    ) -> asyncio.Lock:
        lock = self._event_locks.get(execution_id)

        if lock is None:
            lock = asyncio.Lock()
            self._event_locks[execution_id] = lock

        return lock

    async def create_execution(
        self,
        execution: Execution,
    ) -> None:
        record = execution_to_record(execution)

        async with self._session_factory() as session:
            async with session.begin():
                store = PostgreSQLExecutionStore(session)
                await store.create(record)

    async def update_execution(
        self,
        execution: Execution,
    ) -> None:
        record = execution_to_record(execution)

        async with self._session_factory() as session:
            async with session.begin():
                store = PostgreSQLExecutionStore(session)
                await store.update(record)

    async def append_event(
        self,
        event: AgentEvent,
    ) -> None:
        execution_id = UUID(event.execution_id)

        lock = self._get_event_lock(execution_id)

        async with lock:
            async with self._session_factory() as session:
                async with session.begin():
                    store = PostgreSQLExecutionEventStore(session)

                    if execution_id not in self._event_sequences:
                        existing_events = await store.list(
                            execution_id,
                        )

                        last_sequence = (
                            existing_events[-1].sequence
                            if existing_events
                            else 0
                        )

                        self._event_sequences[
                            execution_id
                        ] = last_sequence

                    sequence = (
                        self._event_sequences[execution_id]
                        + 1
                    )

                    record = event_to_record(
                        event,
                        sequence=sequence,
                    )

                    await store.append(record)

                    self._event_sequences[
                        execution_id
                    ] = sequence

    async def save_result(
        self,
        result: ExecutionResult,
    ) -> None:
        record = result_to_record(result)

        async with self._session_factory() as session:
            async with session.begin():
                store = PostgreSQLExecutionResultStore(session)
                await store.save(record)

    async def close_execution(
        self,
        execution_id: UUID,
    ) -> None:
        """
        Release in-memory event sequencing state for an execution.

        Durable events remain in PostgreSQL.
        """

        self._event_sequences.pop(execution_id, None)
        self._event_locks.pop(execution_id, None)
