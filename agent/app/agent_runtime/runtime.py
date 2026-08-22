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
from app.tools.registry import ToolRegistry


class AgentRuntime:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        tools: ToolRegistry,
        max_steps: int,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps

    async def run(self, intent: str) -> AgentResponse:
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

        for step in range(1, self.max_steps + 1):
            logger.info(
                "agent_step_started execution_id=%s step=%s",
                execution_id,
                step,
            )

            response = await self.llm.complete(
                messages,
                self.tools.definitions(),
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
                        "LLM returned neither tool calls nor content"
                    )

                logger.info(
                    "agent_execution_completed "
                    "execution_id=%s steps=%s",
                    execution_id,
                    step,
                )

                return AgentResponse(
                    execution_id=execution_id,
                    status="success",
                    answer=content,
                    steps=step,
                    tool_calls=executed_tools,
                )

            messages.append(message)

            for tool_call in tool_calls:
                function = tool_call.get("function", {})

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
                    arguments = json.loads(raw_arguments)
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
                    logger.error(
                        "agent_invalid_tool_arguments_type "
                        "execution_id=%s step=%s tool=%s",
                        execution_id,
                        step,
                        name,
                    )

                    raise AgentProtocolError(
                        "Tool arguments must be an object"
                    )

                logger.info(
                    "tool_execution_started "
                    "execution_id=%s step=%s tool=%s",
                    execution_id,
                    step,
                    name,
                )

                result = self.tools.execute(
                    name,
                    arguments,
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

                tool_call_id = tool_call.get("id")

                if not isinstance(tool_call_id, str):
                    raise AgentProtocolError(
                        "Tool call has no valid ID"
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

    @staticmethod
    def _extract_choice(
        response: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            choices = response["choices"]
            choice = choices[0]
        except (KeyError, IndexError, TypeError) as exc:
            raise AgentProtocolError(
                "LLM response does not contain choices"
            ) from exc

        if not isinstance(choice, dict):
            raise AgentProtocolError(
                "Invalid LLM choice"
            )

        return choice
