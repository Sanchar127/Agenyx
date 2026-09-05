from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.agent_runtime.domain.status import ExecutionStatus


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass
class Execution:
    """
    Domain representation of a single agent execution.

    Execution owns execution identity and lifecycle-related data.
    Lifecycle transition rules are intentionally handled by the
    state machine introduced in a later phase.
    """

    id: UUID = field(default_factory=uuid4)

    status: ExecutionStatus = ExecutionStatus.CREATED

    created_at: datetime = field(default_factory=utc_now)

    started_at: datetime | None = None

    completed_at: datetime | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    error: str | None = None

    error_type: str | None = None

    def mark_started(self) -> None:
        """Record that execution processing has started."""

        self.status = ExecutionStatus.RUNNING

        if self.started_at is None:
            self.started_at = utc_now()

    def mark_completed(self) -> None:
        """Record successful execution completion."""

        self.status = ExecutionStatus.COMPLETED

        if self.completed_at is None:
            self.completed_at = utc_now()

    def mark_failed(
        self,
        *,
        error: str,
        error_type: str | None = None,
    ) -> None:
        """Record execution failure information."""

        if not error:
            raise ValueError("Execution failure error cannot be empty")

        self.status = ExecutionStatus.FAILED
        self.error = error
        self.error_type = error_type

        if self.completed_at is None:
            self.completed_at = utc_now()

    def mark_cancelled(self) -> None:
        """Record execution cancellation."""

        self.status = ExecutionStatus.CANCELLED

        if self.completed_at is None:
            self.completed_at = utc_now()

    @property
    def duration_seconds(self) -> float | None:
        """
        Return execution duration in seconds.

        Returns None when execution has not started or has not completed.
        """

        if self.started_at is None:
            return None

        end_time = self.completed_at

        if end_time is None:
            return None

        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
        )
