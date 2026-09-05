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
from app.inference.client import InferenceClient
from app.models.responses import AgentResponse, ToolCallResult
from app.router.client import SemanticRouterClient
from app.sandbox.client import ToolSandboxClient
from app.tools.registry import ToolRegistry


class AgentRuntime:
    """
    Agent orchestration layer.

    Responsibilities:
    - maintain the reasoning loop
    - ask semantic router for model selection
    - call inference service
    - process model tool calls
    - send tool execution to sandbox
    - maintain conversation messages

    Not responsible for:
    - model inference
    - model/provider selection logic
    - tool implementation
    - tool isolation
    - HTTP gateway concerns
    - persistence
    """

    def __init__(
        self,
        *,
        router: SemanticRouterClient,
        inference: InferenceClient,
        tools: ToolRegistry,
        sandbox: ToolSandboxClient,
        max_steps: int,
    ) -> None:
        self.router = router
        self.inference = inference
        self.tools = tools
        self.sandbox = sandbox
        self.max_steps = max_steps

    async def run(
        self,
        intent: str,
        *,
        session_id: str = "",
        task: str = "",
        required_capabilities: list[str] | None = None,
    ) -> AgentResponse:

        execution_id = str(uuid.uuid4())

        if not session_id:
            session_id = execution_id

        if not task:
            task = intent

        logger.info(
            "agent_execution_started "
            "execution_id=%s session_id=%s",
            execution_id,
            session_id,
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

        tool_definitions = self.tools.definitions()

        decision = await self.router.route(
            session_id=session_id,
            task=task,
            messages=messages,
            required_capabilities=required_capabilities,
        )

        selected_model = decision.model

        logger.info(
            "agent_model_selected "
            "execution_id=%s model=%s provider=%s",
            execution_id,
            decision.model,
            decision.provider,
        )

        executed_tools: list[ToolCallResult] = []

        for step in range(1, self.max_steps + 1):

            logger.info(
                "agent_step_started "
                "execution_id=%s step=%s model=%s",
                execution_id,
                step,
                selected_model,
            )

            response = await self.inference.complete(
                model=selected_model,
                messages=messages,
                tools=tool_definitions,
            )

            choice = self._extract_choice(response)

            message = choice.get("message")

            if not isinstance(message, dict):
                raise AgentProtocolError(
                    "Inference response is missing message"
                )

            tool_calls = message.get("tool_calls", [])

            if not isinstance(tool_calls, list):
                raise AgentProtocolError(
                    "Inference tool_calls must be a list"
                )

            # Final model response.
            if not tool_calls:

                content = message.get("content")

                if not isinstance(content, str):
                    raise AgentProtocolError(
                        "Inference returned neither "
                        "tool calls nor content"
                    )

                logger.info(
                    "agent_execution_completed "
                    "execution_id=%s steps=%s tools=%s",
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

            # Preserve assistant tool-call message.
            messages.append(message)

            for tool_call in tool_calls:

                name, arguments, call_id = (
                    self._parse_tool_call(tool_call)
                )

                logger.info(
                    "agent_tool_execution_started "
                    "execution_id=%s step=%s tool=%s",
                    execution_id,
                    step,
                    name,
                )

                result = await self.sandbox.execute(
                    name,
                    arguments,
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
                        "tool_call_id": call_id,
                        "name": name,
                        "content": result,
                    }
                )

                logger.info(
                    "agent_tool_execution_completed "
                    "execution_id=%s step=%s tool=%s",
                    execution_id,
                    step,
                    name,
                )

        raise AgentMaxStepsError(
            f"Agent exceeded maximum steps: {self.max_steps}"
        )

    @staticmethod
    def _parse_tool_call(
        tool_call: Any,
    ) -> tuple[str, dict[str, Any], str]:

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

        return name, arguments, call_id

    @staticmethod
    def _extract_choice(
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

        return choice
