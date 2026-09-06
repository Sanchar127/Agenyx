from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentEvent:
    """
    Immutable event emitted during an agent execution.

    Events represent observable execution activity and are
    intentionally independent of the transport layer.

    The event can later be consumed by:
    - SSE
    - WebSocket
    - CLI clients
    - internal observers
    - logging/observability systems
    """

    type: str
    execution_id: str
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.type:
            raise ValueError("Event type cannot be empty")

        if not self.execution_id:
            raise ValueError("Execution ID cannot be empty")
