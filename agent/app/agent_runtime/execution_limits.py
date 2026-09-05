
from __future__ import annotations

from dataclasses import dataclass
import time

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
    - maximum repeated identical tool calls
    - maximum total execution time
    """

    max_steps: int = 10
    max_tool_calls: int = 20
    max_repeated_tool_calls: int = 3
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise ValueError(
                "max_steps must be greater than zero"
            )

        if self.max_tool_calls < 0:
            raise ValueError(
                "max_tool_calls cannot be negative"
            )

        if self.max_repeated_tool_calls <= 0:
            raise ValueError(
                "max_repeated_tool_calls must be greater than zero"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero"
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

    def validate_tool_call(self, tool_calls: int) -> None:
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

    def validate_repeated_tool_call(
        self,
        repeated_calls: int,
    ) -> None:
        """
        Validate that an identical tool call has not been repeated
        beyond the configured limit.

        `repeated_calls` is the number of times the same tool call
        with the same arguments has already been executed.
        """

        if repeated_calls >= self.max_repeated_tool_calls:
            raise ExecutionLimitExceeded(
                "Agent exceeded maximum repeated tool calls: "
                f"{self.max_repeated_tool_calls}"
            )

    def validate_timeout(self, started_at: float) -> None:
        """
        Validate that the execution has not exceeded its time budget.

        `started_at` must come from time.monotonic().
        """

        elapsed = time.monotonic() - started_at

        if elapsed >= self.timeout_seconds:
            raise ExecutionLimitExceeded(
                "Agent execution exceeded timeout: "
                f"{self.timeout_seconds} seconds"
            )
