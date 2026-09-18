from __future__ import annotations

from enum import StrEnum


class StepStatus(StrEnum):
    """
    Lifecycle status of an individual execution step.

    CREATED:
        Step exists but has not started.

    WAITING_APPROVAL:
        Step requires approval before execution.

    RUNNING:
        Step is actively executing.

    COMPLETED / FAILED / CANCELLED:
        Terminal step states.
    """

    CREATED = "created"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            StepStatus.COMPLETED,
            StepStatus.FAILED,
            StepStatus.CANCELLED,
        }
