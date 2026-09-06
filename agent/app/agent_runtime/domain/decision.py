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
class ToolCall:
    """
    Domain representation of one tool invocation.

    This is intentionally independent of the inference provider's
    response format.

    The Planner converts provider-specific tool-call data into this
    Agenyx-owned representation before the runtime executes it.
    """

    name: str

    arguments: dict[str, Any] = field(
        default_factory=dict
    )

    call_id: str | None = None


@dataclass(frozen=True)
class AgentDecision:
    """
    Domain decision produced by the agent planning layer.

    The runtime consumes this model instead of directly depending
    on the raw inference-provider response format.

    A TOOL_CALL decision may contain one or more ToolCall objects.

    Multiple tool calls represent one model decision and may be
    executed concurrently by the runtime when the calls are
    independently executable.
    """

    type: DecisionType

    content: str | None = None

    # Canonical representation for tool execution.
    tool_calls: tuple[ToolCall, ...] = field(
        default_factory=tuple
    )

    # Backward-compatible single-tool fields.
    #
    # Existing callers/tests may still construct:
    #
    #     AgentDecision(
    #         type=DecisionType.TOOL_CALL,
    #         tool_name="calculator",
    #         arguments={...},
    #         call_id="call-1",
    #     )
    #
    # The runtime supports this representation as well.
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

    @property
    def has_multiple_tool_calls(self) -> bool:
        """
        Return True when this decision contains multiple tool calls.
        """

        return len(self.tool_calls) > 1

    def normalized_tool_calls(self) -> tuple[ToolCall, ...]:
        """
        Return the canonical tool-call representation.

        New Planner-generated decisions use ``tool_calls``.

        Older single-tool decisions may still contain only
        ``tool_name``, ``arguments`` and ``call_id``. Those are
        converted here so the runtime has one execution path.
        """

        if self.tool_calls:
            return self.tool_calls

        if self.tool_name is None:
            return ()

        return (
            ToolCall(
                name=self.tool_name,
                arguments=self.arguments,
                call_id=self.call_id,
            ),
        )
