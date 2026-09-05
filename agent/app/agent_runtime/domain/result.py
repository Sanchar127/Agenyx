from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.agent_runtime.domain.execution import Execution
from app.agent_runtime.domain.status import ExecutionStatus


@dataclass(frozen=True)
class ExecutionResult:
    """
    Immutable result returned when an execution finishes.

    The result is a snapshot of execution state and should not mutate
    after it has been produced.
    """

    execution_id: UUID

    status: ExecutionStatus

    output: Any = None

    error: str | None = None

    error_type: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    created_at: datetime | None = None

    started_at: datetime | None = None

    completed_at: datetime | None = None

    duration_seconds: float | None = None

    @classmethod
    def from_execution(
        cls,
        execution: Execution,
        *,
        output: Any = None,
    ) -> ExecutionResult:
        """
        Create an immutable result snapshot from an execution.
        """

        return cls(
            execution_id=execution.id,
            status=execution.status,
            output=output,
            error=execution.error,
            error_type=execution.error_type,
            metadata=dict(execution.metadata),
            created_at=execution.created_at,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            duration_seconds=execution.duration_seconds,
        )

    @property
    def succeeded(self) -> bool:
        """Whether the execution completed successfully."""

        return self.status is ExecutionStatus.COMPLETED

    @property
    def failed(self) -> bool:
        """Whether the execution failed."""

        return self.status is ExecutionStatus.FAILED

    @property
    def cancelled(self) -> bool:
        """Whether the execution was cancelled."""

        return self.status is ExecutionStatus.CANCELLED
