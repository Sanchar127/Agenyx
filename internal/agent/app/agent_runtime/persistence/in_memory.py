from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.agent_runtime.persistence.models import (
    ExecutionEventRecord,
    ExecutionRecord,
    ExecutionResultRecord,
)


class InMemoryExecutionStore:
    """
    In-memory implementation of ExecutionStore.

    Primarily useful for:
    - unit tests
    - local development
    - validating the persistence contract
    """

    def __init__(self) -> None:
        self._executions: dict[UUID, ExecutionRecord] = {}

    async def create(
        self,
        execution: ExecutionRecord,
    ) -> None:
        if execution.execution_id in self._executions:
            raise ValueError(
                f"Execution already exists: {execution.execution_id}"
            )

        self._executions[execution.execution_id] = execution

    async def get(
        self,
        execution_id: UUID,
    ) -> ExecutionRecord | None:
        return self._executions.get(execution_id)

    async def update(
        self,
        execution: ExecutionRecord,
    ) -> None:
        if execution.execution_id not in self._executions:
            raise ValueError(
                f"Execution does not exist: {execution.execution_id}"
            )

        self._executions[execution.execution_id] = execution


class InMemoryExecutionResultStore:
    """
    In-memory implementation of ExecutionResultStore.

    Each execution has at most one final result.
    """

    def __init__(self) -> None:
        self._results: dict[UUID, ExecutionResultRecord] = {}

    async def save(
        self,
        result: ExecutionResultRecord,
    ) -> None:
        """
        Save an execution result.

        Saving the same execution ID replaces the previous result.
        This makes the operation naturally idempotent.
        """

        self._results[result.execution_id] = result

    async def get(
        self,
        execution_id: UUID,
    ) -> ExecutionResultRecord | None:
        return self._results.get(execution_id)


class InMemoryExecutionEventStore:
    """
    In-memory append-only execution event store.

    Events are stored independently for each execution and are ordered
    by their sequence number.
    """

    def __init__(self) -> None:
        self._events: dict[
            UUID,
            list[ExecutionEventRecord],
        ] = {}

    async def append(
        self,
        event: ExecutionEventRecord,
    ) -> None:
        events = self._events.setdefault(
            event.execution_id,
            [],
        )

        if events:
            last_sequence = events[-1].sequence

            if event.sequence <= last_sequence:
                raise ValueError(
                    "Event sequence must be greater than the "
                    "last persisted sequence"
                )

        events.append(event)

    async def append_many(
        self,
        events: Sequence[ExecutionEventRecord],
    ) -> None:
        """
        Append multiple events atomically from the perspective of this
        in-memory implementation.

        Validation happens before mutating storage so a bad batch does
        not leave a partially written event sequence.
        """

        if not events:
            return

        grouped: dict[
            UUID,
            list[ExecutionEventRecord],
        ] = {}

        for event in events:
            grouped.setdefault(
                event.execution_id,
                [],
            ).append(event)

        for execution_id, batch in grouped.items():
            existing = self._events.get(
                execution_id,
                [],
            )

            previous_sequence = (
                existing[-1].sequence
                if existing
                else 0
            )

            for event in batch:
                if event.sequence <= previous_sequence:
                    raise ValueError(
                        "Event sequence must be strictly increasing "
                        "within a batch"
                    )

                previous_sequence = event.sequence

        for event in events:
            self._events.setdefault(
                event.execution_id,
                [],
            ).append(event)

    async def list(
        self,
        execution_id: UUID,
        *,
        after_sequence: int = 0,
    ) -> list[ExecutionEventRecord]:
        """
        Return events after the supplied sequence number.
        """

        if after_sequence < 0:
            raise ValueError(
                "after_sequence cannot be negative"
            )

        events = self._events.get(
            execution_id,
            [],
        )

        return [
            event
            for event in events
            if event.sequence > after_sequence
        ]
