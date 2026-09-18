from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.agent_runtime.domain.step_status import StepStatus
from app.agent_runtime.domain.step_type import StepType
from app.core.errors import InvalidStateTransition


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Step:
    """
    Represents one significant operation within an execution.

    Step lifecycle:

        CREATED
           |
           +--------------------+
           |                    |
           v                    v
    WAITING_APPROVAL          RUNNING
           |                    |
           v                    |
         RUNNING                |
           |                    |
           +---------+----------+
                     |
          +----------+----------+
          |          |          |
          v          v          v
      COMPLETED    FAILED    CANCELLED

    Terminal states are immutable.
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

    def mark_waiting_approval(self) -> None:
        self._transition_to(StepStatus.WAITING_APPROVAL)

    def mark_started(self) -> None:
        if self.status is StepStatus.RUNNING:
            return

        self._transition_to(StepStatus.RUNNING)

        if self.started_at is None:
            self.started_at = utc_now()

    def mark_completed(self, *, output: Any = None) -> None:
        self._transition_to(StepStatus.COMPLETED)

        self.output = output

        if self.completed_at is None:
            self.completed_at = utc_now()

    def mark_failed(self, *, error: str) -> None:
        if not error:
            raise ValueError("Step failure error cannot be empty")

        self._transition_to(StepStatus.FAILED)

        self.error = error

        if self.completed_at is None:
            self.completed_at = utc_now()

    def mark_cancelled(self) -> None:
        self._transition_to(StepStatus.CANCELLED)

        if self.completed_at is None:
            self.completed_at = utc_now()

    def _transition_to(self, target: StepStatus) -> None:
        transitions: dict[StepStatus, frozenset[StepStatus]] = {
            StepStatus.CREATED: frozenset(
                {
                    StepStatus.WAITING_APPROVAL,
                    StepStatus.RUNNING,
                    StepStatus.FAILED,
                    StepStatus.CANCELLED,
                }
            ),
            StepStatus.WAITING_APPROVAL: frozenset(
                {
                    StepStatus.RUNNING,
                    StepStatus.FAILED,
                    StepStatus.CANCELLED,
                }
            ),
            StepStatus.RUNNING: frozenset(
                {
                    StepStatus.COMPLETED,
                    StepStatus.FAILED,
                    StepStatus.CANCELLED,
                }
            ),
            StepStatus.COMPLETED: frozenset(),
            StepStatus.FAILED: frozenset(),
            StepStatus.CANCELLED: frozenset(),
        }

        if target not in transitions[self.status]:
            raise InvalidStateTransition(
                "Invalid step state transition: "
                f"{self.status.value} -> {target.value}"
            )

        self.status = target

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None or self.completed_at is None:
            return None

        return max(
            0.0,
            (self.completed_at - self.started_at).total_seconds(),
        )

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    @property
    def is_completed(self) -> bool:
        return self.status is StepStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status is StepStatus.FAILED

    @property
    def is_cancelled(self) -> bool:
        return self.status is StepStatus.CANCELLED
