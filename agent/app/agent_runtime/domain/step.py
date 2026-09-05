from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.agent_runtime.domain.step_status import StepStatus
from app.agent_runtime.domain.step_type import StepType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Step:
    """
    Represents one significant operation within an execution.

    A Step belongs to a single Execution and records the
    lifecycle and data associated with that operation.
    """

    step_id: UUID = field(default_factory=uuid4)
    number: int = 0
    type: StepType = StepType.PLAN
    status: StepStatus = StepStatus.CREATED

    input: Any = None
    output: Any = None
    error: str | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(
                "Step number must be greater than zero"
            )

    def mark_started(self) -> None:
        self.status = StepStatus.RUNNING

        if self.started_at is None:
            self.started_at = utc_now()

    def mark_completed(
        self,
        *,
        output: Any = None,
    ) -> None:
        self.status = StepStatus.COMPLETED
        self.output = output

        if self.completed_at is None:
            self.completed_at = utc_now()

    def mark_failed(
        self,
        *,
        error: str,
    ) -> None:
        if not error:
            raise ValueError(
                "Step failure error cannot be empty"
            )

        self.status = StepStatus.FAILED
        self.error = error

        if self.completed_at is None:
            self.completed_at = utc_now()

    def mark_cancelled(self) -> None:
        self.status = StepStatus.CANCELLED

        if self.completed_at is None:
            self.completed_at = utc_now()

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None:
            return None

        if self.completed_at is None:
            return None

        return max(
            0.0,
            (
                self.completed_at - self.started_at
            ).total_seconds(),
        )

    @property
    def is_completed(self) -> bool:
        return self.status is StepStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status is StepStatus.FAILED

    @property
    def is_cancelled(self) -> bool:
        return self.status is StepStatus.CANCELLED
