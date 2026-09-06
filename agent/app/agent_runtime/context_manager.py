from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.agent_runtime.domain.context import ExecutionContext


class TokenCounter(Protocol):
    """
    Abstraction for counting tokens in LLM messages.

    Different model providers can later provide model-specific
    tokenizers without changing ContextManager.
    """

    def count_message_tokens(
        self,
        messages: list[dict[str, Any]],
    ) -> int:
        ...


@dataclass(frozen=True)
class CharacterTokenCounter:
    """
    Deterministic token estimator.

    This is intentionally an approximation rather than a model-
    specific tokenizer.

    The default ratio is approximately 4 characters per token,
    which is a common rough estimate for English text.

    A real model-specific tokenizer can be injected later.
    """

    characters_per_token: int = 4

    def __post_init__(self) -> None:
        if self.characters_per_token <= 0:
            raise ValueError(
                "characters_per_token must be greater than zero"
            )

    def count_message_tokens(
        self,
        messages: list[dict[str, Any]],
    ) -> int:
        total_characters = 0

        for message in messages:
            total_characters += self._count_value(
                message
            )

        if total_characters == 0:
            return 0

        return (
            total_characters
            + self.characters_per_token
            - 1
        ) // self.characters_per_token

    def _count_value(
        self,
        value: Any,
    ) -> int:
        if value is None:
            return 0

        if isinstance(value, str):
            return len(value)

        if isinstance(value, dict):
            return sum(
                self._count_value(key)
                + self._count_value(item)
                for key, item in value.items()
            )

        if isinstance(value, (list, tuple)):
            return sum(
                self._count_value(item)
                for item in value
            )

        return len(str(value))


@dataclass(frozen=True)
class ContextBudget:
    """
    Token budget for one LLM context.

    max_context_tokens:
        Maximum context window supported by the target model.

    reserved_output_tokens:
        Tokens reserved for the model's response.

    Therefore:

        available_input_tokens =
            max_context_tokens
            - reserved_output_tokens
    """

    max_context_tokens: int
    reserved_output_tokens: int = 0

    def __post_init__(self) -> None:
        if self.max_context_tokens <= 0:
            raise ValueError(
                "max_context_tokens must be greater than zero"
            )

        if self.reserved_output_tokens < 0:
            raise ValueError(
                "reserved_output_tokens cannot be negative"
            )

        if self.reserved_output_tokens >= self.max_context_tokens:
            raise ValueError(
                "reserved_output_tokens must be smaller "
                "than max_context_tokens"
            )

    @property
    def available_input_tokens(self) -> int:
        return (
            self.max_context_tokens
            - self.reserved_output_tokens
        )


class ContextManager:
    """
    Manages the LLM-facing context for one agent execution.

    ContextManager deliberately owns context policy while
    ExecutionContext remains the execution-state container.

    Responsibilities:
    - semantic message management
    - tool-call management
    - observation management
    - token estimation
    - context-window budgeting
    - deterministic context trimming
    - construction of inference-ready messages

    It does NOT own:
    - execution lifecycle
    - execution state transitions
    - cancellation
    - execution limits
    - authorization
    - tool execution
    """

    def __init__(
        self,
        context: ExecutionContext,
        *,
        token_counter: TokenCounter | None = None,
        budget: ContextBudget | None = None,
    ) -> None:
        if not isinstance(
            context,
            ExecutionContext,
        ):
            raise TypeError(
                "ContextManager requires a valid ExecutionContext"
            )

        self._context = context

        self._token_counter = (
            token_counter
            or CharacterTokenCounter()
        )

        self._budget = budget

    @property
    def context(self) -> ExecutionContext:
        return self._context

    @property
    def budget(self) -> ContextBudget | None:
        return self._budget

    def add_message(
        self,
        message: dict[str, Any],
    ) -> None:
        if not isinstance(message, dict):
            raise TypeError(
                "message must be a dictionary"
            )

        role = message.get("role")

        if not isinstance(role, str) or not role:
            raise ValueError(
                "message must contain a valid role"
            )

        self._context.add_message(
            dict(message)
        )

    def add_system_message(
        self,
        content: str,
    ) -> None:
        if not isinstance(content, str):
            raise TypeError(
                "system message content must be a string"
            )

        self.add_message(
            {
                "role": "system",
                "content": content,
            }
        )

    def add_user_message(
        self,
        content: str,
    ) -> None:
        if not isinstance(content, str):
            raise TypeError(
                "user message content must be a string"
            )

        self.add_message(
            {
                "role": "user",
                "content": content,
            }
        )

    def add_assistant_message(
        self,
        message: dict[str, Any],
    ) -> None:
        if message.get("role") != "assistant":
            raise ValueError(
                "Assistant message must have role 'assistant'"
            )

        self.add_message(message)

    def add_tool_message(
        self,
        *,
        call_id: str,
        name: str,
        content: str,
    ) -> None:
        if not call_id:
            raise ValueError(
                "Tool message requires a call_id"
            )

        if not name:
            raise ValueError(
                "Tool message requires a tool name"
            )

        if not isinstance(content, str):
            raise TypeError(
                "Tool message content must be a string"
            )

        self.add_message(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": content,
            }
        )

    def get_messages(
        self,
    ) -> list[dict[str, Any]]:
        return [
            dict(message)
            for message in self._context.messages
        ]

    def add_tool_call(
        self,
        tool_call: dict[str, Any],
    ) -> None:
        if not isinstance(tool_call, dict):
            raise TypeError(
                "tool_call must be a dictionary"
            )

        self._context.add_tool_call(
            dict(tool_call)
        )

    def get_tool_calls(
        self,
    ) -> list[dict[str, Any]]:
        return [
            dict(tool_call)
            for tool_call in self._context.tool_calls
        ]

    @property
    def tool_call_count(self) -> int:
        return self._context.tool_call_count

    def add_observation(
        self,
        observation: str,
    ) -> None:
        self._context.add_observation(
            observation
        )

    def get_observations(self) -> list[str]:
        return list(
            self._context.observations
        )

    # =========================================================
    # Token management
    # =========================================================

    def token_count(
        self,
        messages: list[dict[str, Any]] | None = None,
    ) -> int:
        """
        Return the estimated token count of the supplied
        messages or the current context.
        """

        target_messages = (
            self.get_messages()
            if messages is None
            else messages
        )

        return self._token_counter.count_message_tokens(
            target_messages
        )

    def available_input_tokens(self) -> int | None:
        """
        Return the maximum number of input tokens available
        after reserving output tokens.
        """

        if self._budget is None:
            return None

        return self._budget.available_input_tokens

    def remaining_input_tokens(
        self,
        messages: list[dict[str, Any]] | None = None,
    ) -> int | None:
        """
        Return remaining input capacity.

        Returns None when no context budget is configured.
        """

        available = self.available_input_tokens()

        if available is None:
            return None

        used = self.token_count(
            messages
        )

        return max(
            available - used,
            0,
        )

    def exceeds_budget(
        self,
        messages: list[dict[str, Any]] | None = None,
    ) -> bool:
        """
        Return whether the context exceeds the configured
        input-token budget.
        """

        available = self.available_input_tokens()

        if available is None:
            return False

        return (
            self.token_count(messages)
            > available
        )

    # =========================================================
    # Context reduction
    # =========================================================

    def get_messages_for_inference(
        self,
    ) -> list[dict[str, Any]]:
        """
        Return the context that should be sent to inference.

        If no budget is configured, the complete context is
        returned.

        If the context exceeds the configured budget, older
        messages are removed while preserving the system
        message and the most recent context possible.
        """

        messages = self.get_messages()

        if not messages:
            return []

        if not self.exceeds_budget(messages):
            return messages

        return self._trim_messages(
            messages
        )

    def trim_to_budget(self) -> list[dict[str, Any]]:
        """
        Trim the currently stored message history in-place so
        that it fits within the configured context budget.

        Returns the resulting messages.
        """

        trimmed = self.get_messages_for_inference()

        self._context.messages[:] = trimmed

        return self.get_messages()

    def _trim_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        available = self.available_input_tokens()

        if available is None:
            return list(messages)

        if not messages:
            return []

        system_message: dict[str, Any] | None = None
        remaining_messages: list[
            dict[str, Any]
        ] = []

        for message in messages:
            if (
                system_message is None
                and message.get("role") == "system"
            ):
                system_message = message
                continue

            remaining_messages.append(message)

        # Preserve the most recent messages first.
        selected: list[
            dict[str, Any]
        ] = []

        if system_message is not None:
            system_tokens = self.token_count(
                [system_message]
            )

            if system_tokens > available:
                # The system message itself is larger than the
                # entire input budget. There is no valid way to
                # preserve it while satisfying the budget.
                return []

            selected.append(system_message)

            remaining_budget = (
                available - system_tokens
            )
        else:
            remaining_budget = available

        for message in reversed(
            remaining_messages
        ):
            message_tokens = self.token_count(
                [message]
            )

            if message_tokens > remaining_budget:
                continue

            selected.insert(
                1 if system_message is not None else 0,
                message,
            )

            remaining_budget -= message_tokens

            if remaining_budget <= 0:
                break

        return selected

    def clear(self) -> None:
        self._context.messages.clear()
        self._context.tool_calls.clear()
        self._context.observations.clear()
