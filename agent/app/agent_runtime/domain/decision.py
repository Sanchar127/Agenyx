from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DecisionType(StrEnum):
    """Types of decisions the agent runtime can execute."""

    FINAL = "final"
    TOOL_CALL = "tool_call"
    CONTINUE = "continue"
    FAIL = "fail"


@dataclass(frozen=True)
class AgentDecision:
    """
    Domain decision produced by the agent planning layer.

    The runtime consumes this model instead of directly depending
    on the raw inference-provider response format.
    """

    type: DecisionType

    content: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] = field(
        default_factory=dict
    )
    call_id: str | None = None
    error: str | None = None

    @property
    def is_final(self) -> bool:
        return self.type is DecisionType.FINAL

    @property
    def is_tool_call(self) -> bool:
        return self.type is DecisionType.TOOL_CALL

    @property
    def is_continue(self) -> bool:
        return self.type is DecisionType.CONTINUE

    @property
    def is_failure(self) -> bool:
        return self.type is DecisionType.FAIL
