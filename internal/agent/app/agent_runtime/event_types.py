from __future__ import annotations

from enum import StrEnum


class AgentEventType(StrEnum):
    """
    Canonical event types emitted by Agenyx during execution.
    """

    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_CANCELLED = "execution_cancelled"

    INFERENCE_STARTED = "inference_started"
    INFERENCE_COMPLETED = "inference_completed"

    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"

    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_RESOLVED = "approval_resolved"

    STEP_STARTED = "step_started"
