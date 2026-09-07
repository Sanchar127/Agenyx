from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.agent_runtime.persistence.models import ExecutionResultRecord
from app.agent_runtime.persistence.models import (
    ExecutionEventRecord,
    ExecutionRecord,
)


class ExecutionStore(Protocol):
    """
    Durable storage interface for execution state.

    AgentRuntime depends on this abstraction rather than directly
    depending on PostgreSQL.
    """

    async def create(
        self,
        execution: ExecutionRecord,
    ) -> None:
        """
        Persist a newly created execution.
        """
        ...

    async def get(
        self,
        execution_id: UUID,
    ) -> ExecutionRecord | None:
        """
        Retrieve an execution snapshot.
        """
        ...

    async def update(
        self,
        execution: ExecutionRecord,
    ) -> None:
        """
        Replace/update the durable execution snapshot.
        """
        ...


class ExecutionResultStore(Protocol):
    """
    Durable storage interface for execution results.
    """

    async def save(self, result: ExecutionResultRecord) -> None:
        """
        Persist an execution result.
        """
        ...

    async def get(
        self,
        execution_id: UUID,
    ) -> ExecutionResult | None:
        """
        Retrieve an execution result.
        """
        ...


class ExecutionEventStore(Protocol):
    """
    Durable append-only execution event storage.
    """

    async def append(
        self,
        event: ExecutionEventRecord,
    ) -> None:
        """
        Append one execution event.
        """
        ...

    async def append_many(
        self,
        events: Sequence[ExecutionEventRecord],
    ) -> None:
        """
        Append multiple events.
        """
        ...

    async def list(
        self,
        execution_id: UUID,
        *,
        after_sequence: int = 0,
    ) -> list[ExecutionEventRecord]:
        """
        Return events in sequence order.

        after_sequence allows callers to resume event consumption
        without replaying already-consumed events.
        """
        ...
