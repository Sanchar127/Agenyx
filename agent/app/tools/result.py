from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """
    Standard result returned by tool execution.
    """

    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float | None = None

    @property
    def failed(self) -> bool:
        return not self.success
