from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ExecutionSubmission:
    """
    Represents an asynchronously submitted execution.

    The execution_id uses the same UUID type as the underlying
    Execution and ExecutionResult domain objects.
    """

    execution_id: UUID
    status: str = "submitted"
