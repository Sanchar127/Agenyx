
from __future__ import annotations

from enum import StrEnum


class ExecutionState(StrEnum):
    """
    Lifecycle state of an agent execution.

    This represents the state of the entire execution,
    not the state of an individual Step.
    """

    CREATED = "created"
    PLANNING = "planning"
    INFERENCE = "inference"
    TOOL_EXECUTION = "tool_execution"
    OBSERVING = "observing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
