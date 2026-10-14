# app/agent_runtime/domain/status.py
from __future__ import annotations

from enum import StrEnum


class ExecutionStatus(StrEnum):
    """Lifecycle status of an agent execution."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"
    CRASHED = "crashed"
    RECOVERING = "recovering"
    REPLAYING = "replaying"
