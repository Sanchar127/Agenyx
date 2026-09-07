from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.persistence.models import (
    ExecutionEventRecord,
    ExecutionRecord,
    ExecutionResultRecord,
)
from app.db.models import (
    ExecutionEventModel,
    ExecutionModel,
    ExecutionResultModel,
    StepModel,
)


class PostgreSQLExecutionStore:
    """
    PostgreSQL-backed implementation of ExecutionStore.

    Stores the current durable snapshot of an execution.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        execution: ExecutionRecord,
    ) -> None:
        existing = await self.get(execution.execution_id)

        if existing is not None:
            raise ValueError(
                f"Execution already exists: {execution.execution_id}"
            )

        model = ExecutionModel(
            execution_id=execution.execution_id,
            state=execution.state,
            status=execution.status,
            metadata_=execution.metadata,
            error=execution.error,
            error_type=execution.error_type,
            created_at=execution.created_at,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
        )

        self._session.add(model)

        for step in execution.steps:
            self._session.add(
                StepModel(
                    step_id=step.step_id,
                    execution_id=execution.execution_id,
                    number=step.number,
                    type=step.type,
                    status=step.status,
                    input=step.input,
                    output=step.output,
                    error=step.error,
                    started_at=step.started_at,
                    completed_at=step.completed_at,
                )
            )

        await self._session.flush()

    async def get(
        self,
        execution_id: UUID,
    ) -> ExecutionRecord | None:
        result = await self._session.execute(
            select(ExecutionModel)
            .where(ExecutionModel.execution_id == execution_id)
        )

        model = result.scalar_one_or_none()

        if model is None:
            return None

        steps_result = await self._session.execute(
            select(StepModel)
            .where(StepModel.execution_id == execution_id)
            .order_by(StepModel.number)
        )

        steps = steps_result.scalars().all()

        return ExecutionRecord(
            execution_id=model.execution_id,
            state=model.state,
            status=model.status,
            metadata=model.metadata_,
            error=model.error,
            error_type=model.error_type,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            steps=tuple(
                self._step_to_record(step)
                for step in steps
            ),
        )

    async def update(
        self,
        execution: ExecutionRecord,
    ) -> None:
        result = await self._session.execute(
            select(ExecutionModel)
            .where(
                ExecutionModel.execution_id
                == execution.execution_id
            )
        )

        model = result.scalar_one_or_none()

        if model is None:
            raise ValueError(
                f"Execution does not exist: {execution.execution_id}"
            )

        model.state = execution.state
        model.status = execution.status
        model.metadata_ = execution.metadata
        model.error = execution.error
        model.error_type = execution.error_type
        model.created_at = execution.created_at
        model.started_at = execution.started_at
        model.completed_at = execution.completed_at

        existing_steps_result = await self._session.execute(
            select(StepModel)
            .where(
                StepModel.execution_id
                == execution.execution_id
            )
        )

        existing_steps = existing_steps_result.scalars().all()

        existing_by_id = {
            step.step_id: step
            for step in existing_steps
        }

        incoming_ids: set[UUID] = set()

        for step in execution.steps:
            incoming_ids.add(step.step_id)

            existing_step = existing_by_id.get(step.step_id)

            if existing_step is None:
                self._session.add(
                    StepModel(
                        step_id=step.step_id,
                        execution_id=execution.execution_id,
                        number=step.number,
                        type=step.type,
                        status=step.status,
                        input=step.input,
                        output=step.output,
                        error=step.error,
                        started_at=step.started_at,
                        completed_at=step.completed_at,
                    )
                )
                continue

            existing_step.number = step.number
            existing_step.type = step.type
            existing_step.status = step.status
            existing_step.input = step.input
            existing_step.output = step.output
            existing_step.error = step.error
            existing_step.started_at = step.started_at
            existing_step.completed_at = step.completed_at

        for existing_step in existing_steps:
            if existing_step.step_id not in incoming_ids:
                await self._session.delete(existing_step)

        await self._session.flush()

    @staticmethod
    def _step_to_record(
        step: StepModel,
    ):
        from app.agent_runtime.persistence.models import StepRecord

        return StepRecord(
            step_id=step.step_id,
            number=step.number,
            type=step.type,
            status=step.status,
            input=step.input,
            output=step.output,
            error=step.error,
            started_at=step.started_at,
            completed_at=step.completed_at,
        )


class PostgreSQLExecutionResultStore:
    """
    PostgreSQL-backed implementation of ExecutionResultStore.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        result: ExecutionResultRecord,
    ) -> None:
        existing_result = await self.get(
            result.execution_id
        )

        if existing_result is None:
            model = ExecutionResultModel(
                execution_id=result.execution_id,
                status=result.status,
                output=result.output,
                error=result.error,
                error_type=result.error_type,
                metadata_=result.metadata,
                created_at=result.created_at,
                started_at=result.started_at,
                completed_at=result.completed_at,
                duration_seconds=result.duration_seconds,
            )

            self._session.add(model)

        else:
            query_result = await self._session.execute(
                select(ExecutionResultModel)
                .where(
                    ExecutionResultModel.execution_id
                    == result.execution_id
                )
            )

            model = query_result.scalar_one()

            model.status = result.status
            model.output = result.output
            model.error = result.error
            model.error_type = result.error_type
            model.metadata_ = result.metadata
            model.created_at = result.created_at
            model.started_at = result.started_at
            model.completed_at = result.completed_at
            model.duration_seconds = result.duration_seconds

        await self._session.flush()

    async def get(
        self,
        execution_id: UUID,
    ) -> ExecutionResultRecord | None:
        result = await self._session.execute(
            select(ExecutionResultModel)
            .where(
                ExecutionResultModel.execution_id
                == execution_id
            )
        )

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return ExecutionResultRecord(
            execution_id=model.execution_id,
            status=model.status,
            output=model.output,
            error=model.error,
            error_type=model.error_type,
            metadata=model.metadata_,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            duration_seconds=model.duration_seconds,
        )


class PostgreSQLExecutionEventStore:
    """
    PostgreSQL-backed implementation of ExecutionEventStore.

    Events are append-only and ordered by sequence.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        event: ExecutionEventRecord,
    ) -> None:
        existing = await self._session.execute(
            select(ExecutionEventModel)
            .where(
                ExecutionEventModel.execution_id
                == event.execution_id,
                ExecutionEventModel.sequence
                == event.sequence,
            )
        )

        if existing.scalar_one_or_none() is not None:
            raise ValueError(
                "Execution event sequence already exists: "
                f"{event.execution_id}:{event.sequence}"
            )

        self._session.add(
            ExecutionEventModel(
                event_id=event.event_id,
                execution_id=event.execution_id,
                sequence=event.sequence,
                type=event.type,
                data=event.data,
                created_at=event.created_at,
            )
        )

        await self._session.flush()

    async def append_many(
            self,
            events: Sequence[ExecutionEventRecord],
        ) -> None:
            """
            Append multiple events while preserving per-execution ordering.

            Events for the same execution must be strictly increasing
            relative to both:
            - events already persisted
            - other events in this batch
            """

            if not events:
                return

            grouped: dict[UUID, list[ExecutionEventRecord]] = {}

            for event in events:
                grouped.setdefault(
                    event.execution_id,
                    [],
                ).append(event)

            # Validate each execution's batch against persisted events.
            for execution_id, batch in grouped.items():
                batch = sorted(
                    batch,
                    key=lambda event: event.sequence,
                )

                last_event_result = await self._session.execute(
                    select(ExecutionEventModel.sequence)
                    .where(
                        ExecutionEventModel.execution_id == execution_id,
                    )
                    .order_by(
                        ExecutionEventModel.sequence.desc(),
                    )
                    .limit(1)
                )

                last_sequence = last_event_result.scalar_one_or_none() or 0

                previous_sequence = last_sequence

                for event in batch:
                    if event.sequence <= previous_sequence:
                        raise ValueError(
                            "Event sequences must be strictly increasing "
                            f"for execution {execution_id}"
                        )

                    previous_sequence = event.sequence

            # Only add events after the entire batch has passed validation.
            for event in events:
                self._session.add(
                    ExecutionEventModel(
                        event_id=event.event_id,
                        execution_id=event.execution_id,
                        sequence=event.sequence,
                        type=event.type,
                        data=event.data,
                        created_at=event.created_at,
                    )
                )

            await self._session.flush()

    async def list(
        self,
        execution_id: UUID,
        *,
        after_sequence: int = 0,
    ) -> list[ExecutionEventRecord]:
        if after_sequence < 0:
            raise ValueError(
                "after_sequence cannot be negative"
            )

        result = await self._session.execute(
            select(ExecutionEventModel)
            .where(
                ExecutionEventModel.execution_id
                == execution_id,
                ExecutionEventModel.sequence
                > after_sequence,
            )
            .order_by(ExecutionEventModel.sequence)
        )

        models = result.scalars().all()

        return [
            ExecutionEventRecord(
                event_id=model.event_id,
                execution_id=model.execution_id,
                sequence=model.sequence,
                type=model.type,
                data=model.data,
                created_at=model.created_at,
            )
            for model in models
        ]
