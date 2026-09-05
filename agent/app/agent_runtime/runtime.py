from __future__ import annotations

from typing import Any

from app.agent_runtime.domain import (
    Execution,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
)
from app.agent_runtime.planner import Planner
from app.agent_runtime.prompts import SYSTEM_PROMPT
from app.core.errors import AgentMaxStepsError
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
    - ask Planner to interpret inference responses
    - execute approved tool decisions through the sandbox
    - maintain conversation messages
    - produce an execution result

    Not responsible for:
    - model inference
    - model/provider implementation
    - interpreting raw inference responses
    - parsing tool calls
    - validating tool calls
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
        planner: Planner,
        max_steps: int,
    ) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be greater than zero")

        self.router = router
        self.inference = inference
        self.tools = tools
        self.sandbox = sandbox
        self.planner = planner
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
        context.add_message(
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        )

        context.add_message(
            {
                "role": "user",
                "content": intent,
            }
        )

        tool_definitions = self.tools.definitions()

        decision = await self.router.route(
            session_id=session_id,
            task=task,
            messages=context.messages,
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

        execution.metadata.update(
            {
                "model": decision.model,
                "provider": decision.provider,
            }
        )

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
                messages=context.messages,
                tools=tool_definitions,
            )

            decision = self.planner.plan(
                response=response,
                context=context,
            )

            if decision.is_final:
                return self._complete_execution(
                    context=context,
                    output=decision.content,
                    step=step,
                    executed_tools=executed_tools,
                )

            if decision.is_tool_call:
                assert decision.tool_name is not None
                assert decision.call_id is not None

                tool_name = decision.tool_name
                arguments = decision.arguments
                call_id = decision.call_id

                assistant_message = self._extract_assistant_message(
                    response
                )

                context.add_message(assistant_message)

                context.add_tool_call(
                    {
                        "name": tool_name,
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
                    tool_name,
                )

                result = await self.sandbox.execute(
                    tool_name,
                    arguments,
                )

                executed_tools.append(
                    ToolCallResult(
                        name=tool_name,
                        arguments=arguments,
                        result=result,
                    )
                )

                context.add_observation(
                    f"Tool '{tool_name}' returned: {result}"
                )

                context.add_message(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": tool_name,
                        "content": result,
                    }
                )

                logger.info(
                    "agent_tool_execution_completed "
                    "execution_id=%s step=%s tool=%s",
                    execution.id,
                    step,
                    tool_name,
                )

                continue

            raise RuntimeError(
                f"Unsupported agent decision type: {decision.type}"
            )

        raise AgentMaxStepsError(
            f"Agent exceeded maximum steps: {self.max_steps}"
        )

    @staticmethod
    def _extract_assistant_message(
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Extract the assistant message after Planner has already
        validated the inference response.

        This is intentionally a small transport extraction helper.
        All protocol validation belongs to Planner.
        """

        choices = response.get("choices")

        if not isinstance(choices, list) or not choices:
            raise RuntimeError(
                "Planner accepted an inference response without choices"
            )

        choice = choices[0]

        if not isinstance(choice, dict):
            raise RuntimeError(
                "Planner accepted an invalid inference choice"
            )

        message = choice.get("message")

        if not isinstance(message, dict):
            raise RuntimeError(
                "Planner accepted an inference response without message"
            )

        return message

    @staticmethod
    def _complete_execution(
        *,
        context: ExecutionContext,
        output: str | None,
        step: int,
        executed_tools: list[ToolCallResult],
    ) -> ExecutionResult:
        if not isinstance(output, str):
            raise RuntimeError(
                "Planner produced a final decision without string content"
            )

        context.metadata.update(
            {
                "steps": step,
                "tool_calls": list(executed_tools),
            }
        )

        context.execution.metadata.update(
            {
                "steps": step,
                "tool_calls": list(executed_tools),
            }
        )

        return ExecutionResult.from_execution(
            context.execution,
            output=output,
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
