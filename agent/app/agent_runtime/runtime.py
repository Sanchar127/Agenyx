from __future__ import annotations

import json
from typing import Any

from app.agent_runtime.domain import (
    Execution,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
)
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
    - create and manage an agent execution
    - create and maintain execution context
    - maintain the reasoning loop
    - ask semantic router for model selection
    - call inference service
    - process model tool calls
    - send tool execution to sandbox
    - maintain conversation messages
    - produce an execution result

    Not responsible for:
    - model inference
    - model/provider implementation
    - tool implementation
    - tool isolation
    - HTTP gateway concerns
    - persistence
    - lifecycle transition policy
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
        if max_steps <= 0:
            raise ValueError("max_steps must be greater than zero")

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

        execution = Execution()

        context = ExecutionContext(
            execution=execution,
        )

        if not session_id:
            session_id = str(execution.id)

        if not task:
            task = intent

        context.metadata.update(
            {
                "session_id": session_id,
                "task": task,
            }
        )

        execution.metadata.update(
            {
                "session_id": session_id,
                "task": task,
            }
        )

        logger.info(
            "agent_execution_started "
            "execution_id=%s session_id=%s",
            execution.id,
            session_id,
        )

        execution.mark_started()

        try:
            result = await self._execute(
                context=context,
                intent=intent,
                session_id=session_id,
                task=task,
                required_capabilities=required_capabilities,
            )

        except Exception as exc:
            execution.mark_failed(
                error=str(exc),
                error_type=type(exc).__name__,
            )

            context.add_error(str(exc))

            logger.exception(
                "agent_execution_failed "
                "execution_id=%s error_type=%s",
                execution.id,
                type(exc).__name__,
            )

            raise

        execution.mark_completed()

        result = ExecutionResult.from_execution(
            execution,
            output=result.output,
        )

        logger.info(
            "agent_execution_completed "
            "execution_id=%s status=%s duration_seconds=%s",
            result.execution_id,
            result.status,
            result.duration_seconds,
        )

        return self._to_agent_response(
            result=result,
            steps=int(result.metadata.get("steps", 0)),
            tool_calls=result.metadata.get("tool_calls", []),
        )

    async def _execute(
        self,
        *,
        context: ExecutionContext,
        intent: str,
        session_id: str,
        task: str,
        required_capabilities: list[str] | None,
    ) -> ExecutionResult:

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

        for message in messages:
            context.add_message(message)

        tool_definitions = self.tools.definitions()

        decision = await self.router.route(
            session_id=session_id,
            task=task,
            messages=messages,
            required_capabilities=required_capabilities,
        )

        selected_model = decision.model

        context.metadata.update(
            {
                "model": decision.model,
                "provider": decision.provider,
            }
        )

        execution = context.execution

        execution.metadata["model"] = decision.model
        execution.metadata["provider"] = decision.provider

        logger.info(
            "agent_model_selected "
            "execution_id=%s model=%s provider=%s",
            execution.id,
            decision.model,
            decision.provider,
        )

        executed_tools: list[ToolCallResult] = []

        for step in range(1, self.max_steps + 1):

            context.current_step = step

            logger.info(
                "agent_step_started "
                "execution_id=%s step=%s model=%s",
                execution.id,
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

            context.add_message(message)

            tool_calls = message.get("tool_calls", [])

            if not isinstance(tool_calls, list):
                raise AgentProtocolError(
                    "Inference tool_calls must be a list"
                )

            if not tool_calls:

                content = message.get("content")

                if not isinstance(content, str):
                    raise AgentProtocolError(
                        "Inference returned neither "
                        "tool calls nor content"
                    )

                execution.metadata["steps"] = step
                execution.metadata["tool_calls"] = list(
                    executed_tools
                )

                context.metadata["steps"] = step
                context.metadata["tool_calls"] = list(
                    executed_tools
                )

                return ExecutionResult.from_execution(
                    execution,
                    output=content,
                )

            messages.append(message)

            for tool_call in tool_calls:

                name, arguments, call_id = (
                    self._parse_tool_call(tool_call)
                )

                context.add_tool_call(
                    {
                        "name": name,
                        "arguments": arguments,
                        "call_id": call_id,
                        "step": step,
                    }
                )

                logger.info(
                    "agent_tool_execution_started "
                    "execution_id=%s step=%s tool=%s",
                    execution.id,
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

                context.add_observation(
                    f"Tool '{name}' returned: {result}"
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": result,
                    }
                )

                context.add_message(
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
                    execution.id,
                    step,
                    name,
                )

        raise AgentMaxStepsError(
            f"Agent exceeded maximum steps: {self.max_steps}"
        )

    @staticmethod
    def _to_agent_response(
        *,
        result: ExecutionResult,
        steps: int,
        tool_calls: list[ToolCallResult],
    ) -> AgentResponse:

        if result.status is not ExecutionStatus.COMPLETED:
            raise RuntimeError(
                "Cannot create successful AgentResponse from "
                f"execution with status '{result.status}'"
            )

        if not isinstance(result.output, str):
            raise RuntimeError(
                "Execution completed without string output"
            )

        return AgentResponse(
            execution_id=str(result.execution_id),
            status="success",
            answer=result.output,
            steps=steps,
            tool_calls=tool_calls,
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
