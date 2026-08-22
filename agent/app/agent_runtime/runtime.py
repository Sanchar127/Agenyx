from __future__ import annotations

import json
import uuid
from typing import Any

from app.agent_runtime.prompts import SYSTEM_PROMPT
from app.core.errors import (
    AgentMaxStepsError,
    AgentProtocolError,
)
from app.core.logging import logger
from app.llm.base import LLMProvider
from app.models.responses import AgentResponse, ToolCallResult
from app.sandbox.client import ToolSandboxClient
from app.tools.registry import ToolRegistry


class AgentRuntime:
    """Coordinate LLM reasoning and isolated tool execution."""

    def __init__(
        self,
        *,
        llm: LLMProvider,
        tools: ToolRegistry,
        max_steps: int,
        sandbox: ToolSandboxClient | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.sandbox = sandbox

    async def run(
        self,
        intent: str,
    ) -> AgentResponse:
        """Run the agent until it produces a final answer."""

        execution_id = str(uuid.uuid4())

        logger.info(
            "agent_execution_started execution_id=%s",
            execution_id,
        )

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": intent,
            },
        ]

        executed_tools: list[ToolCallResult] = []

        tool_definitions = self.tools.definitions()

        logger.info(
            "agent_tools_loaded "
            "execution_id=%s tools=%s",
            execution_id,
            len(tool_definitions),
        )

        for step in range(1, self.max_steps + 1):
            logger.info(
                "agent_step_started "
                "execution_id=%s step=%s",
                execution_id,
                step,
            )

            logger.info(
                "agent_calling_llm "
                "execution_id=%s step=%s tools=%s",
                execution_id,
                step,
                len(tool_definitions),
            )

            response = await self.llm.complete(
                messages,
                tool_definitions,
            )

            logger.info(
                "agent_llm_completed "
                "execution_id=%s step=%s",
                execution_id,
                step,
            )

            choice = self._extract_choice(response)
            message = choice.get("message")

            if not isinstance(message, dict):
                logger.error(
                    "agent_invalid_llm_message "
                    "execution_id=%s step=%s",
                    execution_id,
                    step,
                )

                raise AgentProtocolError(
                    "LLM response is missing message"
                )

            tool_calls = message.get("tool_calls", [])

            if not isinstance(tool_calls, list):
                logger.error(
                    "agent_invalid_tool_calls "
                    "execution_id=%s step=%s",
                    execution_id,
                    step,
                )

                raise AgentProtocolError(
                    "LLM tool_calls must be a list"
                )

            if not tool_calls:
                content = message.get("content")

                if not isinstance(content, str):
                    logger.error(
                        "agent_invalid_final_response "
                        "execution_id=%s step=%s",
                        execution_id,
                        step,
                    )

                    raise AgentProtocolError(
                        "LLM returned neither "
                        "tool calls nor content"
                    )

                logger.info(
                    "agent_execution_completed "
                    "execution_id=%s steps=%s tools_executed=%s",
                    execution_id,
                    step,
                    len(executed_tools),
                )

                return AgentResponse(
                    execution_id=execution_id,
                    status="success",
                    answer=content,
                    steps=step,
                    tool_calls=executed_tools,
                )

            logger.info(
                "agent_tool_calls_received "
                "execution_id=%s step=%s count=%s",
                execution_id,
                step,
                len(tool_calls),
            )

            messages.append(message)

            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    raise AgentProtocolError(
                        "Tool call must be an object"
                    )

                function = tool_call.get(
                    "function",
                    {},
                )

                if not isinstance(function, dict):
                    raise AgentProtocolError(
                        "Tool call has invalid function payload"
                    )

                name = function.get("name")

                raw_arguments = function.get(
                    "arguments",
                    "{}",
                )

                if not isinstance(name, str) or not name:
                    logger.error(
                        "agent_invalid_tool_name "
                        "execution_id=%s step=%s",
                        execution_id,
                        step,
                    )

                    raise AgentProtocolError(
                        "Tool call has no valid name"
                    )

                if not isinstance(raw_arguments, str):
                    logger.error(
                        "agent_invalid_tool_arguments "
                        "execution_id=%s step=%s tool=%s",
                        execution_id,
                        step,
                        name,
                    )

                    raise AgentProtocolError(
                        f"Invalid arguments for tool '{name}'"
                    )

                try:
                    arguments = json.loads(
                        raw_arguments,
                    )

                except json.JSONDecodeError as exc:
                    logger.error(
                        "agent_invalid_tool_arguments_json "
                        "execution_id=%s step=%s tool=%s",
                        execution_id,
                        step,
                        name,
                    )

                    raise AgentProtocolError(
                        f"Invalid arguments for tool '{name}'"
                    ) from exc

                if not isinstance(arguments, dict):
                    raise AgentProtocolError(
                        "Tool arguments must be an object"
                    )

                tool_call_id = tool_call.get("id")

                if not isinstance(tool_call_id, str):
                    raise AgentProtocolError(
                        "Tool call has no valid ID"
                    )

                logger.info(
                    "tool_execution_started "
                    "execution_id=%s step=%s tool=%s "
                    "tool_call_id=%s",
                    execution_id,
                    step,
                    name,
                    tool_call_id,
                )

                result = await self._execute_tool(
                    name=name,
                    arguments=arguments,
                )

                logger.info(
                    "tool_execution_completed "
                    "execution_id=%s step=%s tool=%s",
                    execution_id,
                    step,
                    name,
                )

                executed_tools.append(
                    ToolCallResult(
                        name=name,
                        arguments=arguments,
                        result=result,
                    )
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": name,
                        "content": result,
                    }
                )

        logger.error(
            "agent_max_steps_exceeded "
            "execution_id=%s max_steps=%s",
            execution_id,
            self.max_steps,
        )

        raise AgentMaxStepsError(
            f"Agent exceeded maximum steps: {self.max_steps}"
        )

    async def _execute_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Execute a tool through the isolated sandbox."""

        if self.sandbox is None:
            logger.error(
                "sandbox_not_configured tool=%s",
                name,
            )

            raise AgentProtocolError(
                "Tool sandbox is not configured"
            )

        try:
            return await self.sandbox.execute(
                name,
                arguments,
            )

        except Exception:
            logger.exception(
                "sandbox_tool_execution_failed "
                "tool=%s",
                name,
            )
            raise

    @staticmethod
    def _extract_choice(
        response: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            choices = response["choices"]
            choice = choices[0]

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise AgentProtocolError(
                "LLM response does not contain choices"
            ) from exc

        if not isinstance(choice, dict):
            raise AgentProtocolError(
                "Invalid LLM choice"
            )

        return choice
