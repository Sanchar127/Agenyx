from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import (
    AgentMaxStepsError,
    ExecutionLimitExceeded,
)


@dataclass(frozen=True)
class ExecutionLimits:
    """
    Immutable execution policy for one AgentRuntime execution.

    Limits currently supported:

    - maximum inference/execution steps
    - maximum tool calls

    The policy is immutable so limits cannot be changed while an
    execution is already running.
    """

    max_steps: int = 10
    max_tool_calls: int = 20

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise ValueError(
                "max_steps must be greater than zero"
            )

        if self.max_tool_calls < 0:
            raise ValueError(
                "max_tool_calls cannot be negative"
            )

    def validate_step(self, step: int) -> None:
        """
        Validate that a step is within the configured limit.
        """

        if step > self.max_steps:
            raise AgentMaxStepsError(
                "Agent exceeded maximum steps: "
                f"{self.max_steps}"
            )

    def validate_tool_call(
        self,
        tool_calls: int,
    ) -> None:
        """
        Validate that another tool call is permitted.

        `tool_calls` is the number of tool calls that have already
        been executed.
        """

        if tool_calls >= self.max_tool_calls:
            raise ExecutionLimitExceeded(
                "Agent exceeded maximum tool calls: "
                f"{self.max_tool_calls}"
            )
