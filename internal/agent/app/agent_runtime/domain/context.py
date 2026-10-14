from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent_runtime.domain.execution import Execution


@dataclass
class ExecutionContext:
    """
    Working state for a single agent execution.

    The context gives the planner and runtime the information
    they need to decide and execute the next action.
    """

    execution: Execution

    messages: list[dict[str, Any]] = field(default_factory=list)

    current_plan: str | None = None

    current_step: int = 0

    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    observations: list[str] = field(default_factory=list)

    errors: list[str] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def add_tool_call(self, tool_call: dict[str, Any]) -> None:
        self.tool_calls.append(tool_call)

    def add_observation(self, observation: str) -> None:
        self.observations.append(observation)

    def add_error(self, error: str) -> None:
        if not error:
            raise ValueError("Execution context error cannot be empty")

        self.errors.append(error)

    def advance_step(self) -> None:
        self.current_step += 1

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_observations(self) -> bool:
        return bool(self.observations)

    @property
    def tool_call_count(self) -> int:
        return len(self.tool_calls)
