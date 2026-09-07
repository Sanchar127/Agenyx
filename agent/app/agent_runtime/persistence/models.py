from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ExecutionRecord:
    """
    Durable snapshot of an agent execution.

    This represents the state that must survive an AgentRuntime
    process restart.

    It intentionally contains data, not runtime objects such as:

    - asyncio.Task
    - CancellationToken
    - EventStream
    - ExecutionStateMachine
    """

    execution_id: UUID

    state: str
    status: str

    metadata: dict[str, Any] = field(default_factory=dict)

    error: str | None = None
    error_type: str | None = None

    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    steps: tuple[StepRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StepRecord:
    """
    Durable representation of one execution step.
    """

    step_id: UUID

    number: int

    type: str

    status: str

    input: Any = None
    output: Any = None
    error: str | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class ExecutionResultRecord:
    """
    Durable representation of a completed execution result.

    Results are stored separately from the execution lifecycle
    snapshot because callers may retrieve the result independently
    of the current runtime object.
    """

    execution_id: UUID

    status: str

    output: Any = None

    error: str | None = None
    error_type: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    duration_seconds: float | None = None


@dataclass(frozen=True)
class ExecutionEventRecord:
    """
    Durable representation of one execution event.

    Events are append-only.

    sequence provides deterministic ordering within one execution.
    """

    event_id: UUID

    execution_id: UUID

    sequence: int

    type: str

    data: dict[str, Any] = field(default_factory=dict)

    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError(
                "Event sequence must be greater than zero"
            )

        if not self.type:
            raise ValueError(
                "Event type cannot be empty"
            )
