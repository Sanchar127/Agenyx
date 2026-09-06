from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.core.errors import (
    AgentMaxStepsError,
    ExecutionLimitExceeded,
)


@dataclass(frozen=True)
class ExecutionLimits:
    """
    Immutable execution policy for one agent execution.

    ExecutionLimits owns the constraints that determine how much
    work an execution is allowed to perform.

    Limits:
        max_steps:
            Maximum number of reasoning/inference iterations.

        max_tool_calls:
            Maximum total number of tool executions.

        max_repeated_tool_calls:
            Maximum number of executions of the same tool with the
            same arguments.

        timeout_seconds:
            Execution-wide wall-clock timeout.

        per_tool_limits:
            Optional individual limits for specific tools.

            A value of zero means the tool is disabled for this
            execution.

        max_parallel_tool_calls:
            Maximum number of tool executions that may run
            concurrently from one model decision.
    """

    max_steps: int = 10

    max_tool_calls: int = 20

    max_repeated_tool_calls: int = 3

    timeout_seconds: float = 60.0

    per_tool_limits: dict[str, int] = field(
        default_factory=dict
    )

    max_parallel_tool_calls: int = 4

    def __post_init__(self) -> None:
        """
        Validate execution-limit configuration.
        """

        if self.max_steps <= 0:
            raise ValueError(
                "max_steps must be greater than zero"
            )

        if self.max_tool_calls <= 0:
            raise ValueError(
                "max_tool_calls must be greater than zero"
            )

        if self.max_repeated_tool_calls <= 0:
            raise ValueError(
                "max_repeated_tool_calls must be greater "
                "than zero"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero"
            )

        if self.max_parallel_tool_calls <= 0:
            raise ValueError(
                "max_parallel_tool_calls must be greater "
                "than zero"
            )

        for tool_name, limit in self.per_tool_limits.items():
            if not tool_name:
                raise ValueError(
                    "per_tool_limits contains an empty tool name"
                )

            if limit < 0:
                raise ValueError(
                    "per_tool_limits values cannot be negative"
                )

    def validate_step(
        self,
        step: int,
    ) -> None:
        """
        Validate that the requested reasoning step is allowed.
        """

        if step <= 0:
            raise ValueError(
                "step must be greater than zero"
            )

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
        Validate that another global tool execution is allowed.

        Args:
            tool_calls:
                Number of tool executions that have already been
                admitted or executed.
        """

        if tool_calls < 0:
            raise ValueError(
                "tool_calls cannot be negative"
            )

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
        Validate that another identical tool call is allowed.

        Args:
            repeated_calls:
                Number of previous executions of the same tool with
                the same arguments.
        """

        if repeated_calls < 0:
            raise ValueError(
                "repeated_calls cannot be negative"
            )

        if repeated_calls >= self.max_repeated_tool_calls:
            raise ExecutionLimitExceeded(
                "Agent exceeded maximum repeated tool calls: "
                f"{self.max_repeated_tool_calls}"
            )

    def validate_per_tool_call(
        self,
        tool_name: str,
        tool_calls: int,
    ) -> None:
        """
        Validate that another call to a specific tool is permitted.

        Tools without an entry in per_tool_limits have no individual
        limit and remain subject to the global tool-call limit.

        A per-tool limit of zero means the tool is completely
        disabled for this execution.

        Args:
            tool_name:
                Name of the tool being evaluated.

            tool_calls:
                Number of previous calls to this specific tool.

        Raises:
            ExecutionLimitExceeded:
                If the configured per-tool limit is exhausted.
        """

        if not tool_name:
            raise ValueError(
                "tool_name cannot be empty"
            )

        if tool_calls < 0:
            raise ValueError(
                "tool_calls cannot be negative"
            )

        limit = self.per_tool_limits.get(
            tool_name
        )

        if limit is None:
            return

        if tool_calls >= limit:
            raise ExecutionLimitExceeded(
                "Agent exceeded maximum calls for tool "
                f"'{tool_name}': {limit} "
                "(per-tool limit exceeded)"
            )

    def validate_timeout(
        self,
        started_at: float,
    ) -> None:
        """
        Validate the execution-wide timeout.

        Args:
            started_at:
                Monotonic timestamp representing the beginning of
                the execution.
        """

        elapsed = time.monotonic() - started_at

        if elapsed >= self.timeout_seconds:
            raise ExecutionLimitExceeded(
                "Agent execution exceeded timeout: "
                f"{self.timeout_seconds} seconds"
            )

    def remaining_steps(
        self,
        current_step: int,
    ) -> int:
        """
        Return the number of reasoning steps remaining.
        """

        if current_step < 0:
            raise ValueError(
                "current_step cannot be negative"
            )

        return max(
            self.max_steps - current_step,
            0,
        )

    def remaining_tool_calls(
        self,
        tool_calls: int,
    ) -> int:
        """
        Return the number of global tool calls remaining.
        """

        if tool_calls < 0:
            raise ValueError(
                "tool_calls cannot be negative"
            )

        return max(
            self.max_tool_calls - tool_calls,
            0,
        )

    def remaining_repeated_tool_calls(
        self,
        repeated_calls: int,
    ) -> int:
        """
        Return the number of repeated identical calls remaining.
        """

        if repeated_calls < 0:
            raise ValueError(
                "repeated_calls cannot be negative"
            )

        return max(
            self.max_repeated_tool_calls - repeated_calls,
            0,
        )

    def remaining_per_tool_calls(
        self,
        tool_name: str,
        tool_calls: int,
    ) -> int | None:
        """
        Return the remaining calls for a specific tool.

        Returns:
            None:
                The tool has no individual configured limit.

            int:
                Number of calls remaining.
        """

        if not tool_name:
            raise ValueError(
                "tool_name cannot be empty"
            )

        if tool_calls < 0:
            raise ValueError(
                "tool_calls cannot be negative"
            )

        limit = self.per_tool_limits.get(
            tool_name
        )

        if limit is None:
            return None

        return max(
            limit - tool_calls,
            0,
        )

    def remaining_timeout(
        self,
        started_at: float,
    ) -> float:
        """
        Return the remaining execution-wide timeout in seconds.
        """

        elapsed = time.monotonic() - started_at

        return max(
            self.timeout_seconds - elapsed,
            0.0,
        )
