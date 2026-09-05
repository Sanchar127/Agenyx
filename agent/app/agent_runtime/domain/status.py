from __future__ import annotations

from enum import StrEnum


class ExecutionStatus(StrEnum):
    """Lifecycle status of an agent execution."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
