from __future__ import annotations

import json
from typing import Any

from app.agent_runtime.domain.decision import (
    AgentDecision,
    DecisionType,
)
from app.core.errors import AgentProtocolError


class Planner:
    """
    Converts raw inference responses into Agenyx domain decisions.

    The Planner understands the inference response protocol.
    AgentRuntime only understands AgentDecision.
    """

    def plan(
        self,
        response: dict[str, Any],
    ) -> AgentDecision:
        message = self._extract_message(response)

        tool_calls = message.get("tool_calls", [])

        if not isinstance(tool_calls, list):
            raise AgentProtocolError(
                "Inference tool_calls must be a list"
            )

        if tool_calls:
            return self._create_tool_decision(
                tool_calls[0]
            )

        content = message.get("content")

        if not isinstance(content, str):
            raise AgentProtocolError(
                "Inference returned neither "
                "tool calls nor content"
            )

        return AgentDecision(
            type=DecisionType.FINAL,
            content=content,
        )

    @staticmethod
    def _extract_message(
        response: dict[str, Any],
    ) -> dict[str, Any]:
        choices = response.get("choices")

        if not isinstance(choices, list) or not choices:
            raise AgentProtocolError(
                "Inference response does not contain choices"
            )

        choice = choices[0]

        if not isinstance(choice, dict):
            raise AgentProtocolError(
                "Inference response contains invalid choice"
            )

        message = choice.get("message")

        if not isinstance(message, dict):
            raise AgentProtocolError(
                "Inference response does not contain message"
            )

        return message

    @classmethod
    def _create_tool_decision(
        cls,
        tool_call: Any,
    ) -> AgentDecision:
        if not isinstance(tool_call, dict):
            raise AgentProtocolError(
                "Tool call must be an object"
            )

        call_id = tool_call.get("id")

        if not isinstance(call_id, str) or not call_id:
            raise AgentProtocolError(
                "Tool call has no valid ID"
            )

        function = tool_call.get("function")

        if not isinstance(function, dict):
            raise AgentProtocolError(
                "Tool call has invalid function"
            )

        name = function.get("name")

        if not isinstance(name, str) or not name:
            raise AgentProtocolError(
                "Tool call has no valid name"
            )

        raw_arguments = function.get(
            "arguments",
            "{}",
        )

        if not isinstance(raw_arguments, str):
            raise AgentProtocolError(
                f"Invalid arguments for tool '{name}'"
            )

        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise AgentProtocolError(
                f"Invalid arguments for tool '{name}'"
            ) from exc

        if not isinstance(arguments, dict):
            raise AgentProtocolError(
                "Tool arguments must be an object"
            )

        return AgentDecision(
            type=DecisionType.TOOL_CALL,
            tool_name=name,
            arguments=arguments,
            call_id=call_id,
        )
