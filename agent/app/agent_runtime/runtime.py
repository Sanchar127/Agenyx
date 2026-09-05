from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from app.agent_runtime.domain import (
    AgentDecision,
    Execution,
    ExecutionContext,
    ExecutionResult,
    ExecutionState,
    Step,
    StepType,
)
from app.agent_runtime.execution_limits import ExecutionLimits
from app.agent_runtime.planner import Planner
from app.agent_runtime.prompts import SYSTEM_PROMPT
from app.core.errors import (
    AgentMaxStepsError,
    AgentProtocolError,
    ExecutionLimitExceeded,
    ToolExecutionError,
)
from app.core.logging import logger
from app.inference.client import InferenceClient
from app.models.responses import AgentResponse, ToolCallResult
from app.router.client import SemanticRouterClient
from app.sandbox.client import ToolSandboxClient
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry


class AgentRuntime:
    """
    Orchestrates a complete agent execution.

    Responsibilities:
    - create and manage execution state
    - build the execution context
    - route the request to an appropriate model
    - call the inference service
    - interpret inference output through the Planner
    - execute requested tools
    - feed tool observations back into inference
    - enforce execution limits
    - produce the public AgentResponse

    Provider/model-specific logic does not belong here.
    The runtime communicates with the separate InferenceClient
    abstraction.

    Execution limit semantics:

        max_steps = N

    means the runtime permits at most N reasoning/inference
    iterations.

        max_tool_calls = N

    means the runtime permits at most N total tool executions.

        max_repeated_tool_calls = N

    means the runtime permits at most N executions of the same
    tool with the same arguments during one execution.

        per_tool_limits = {
            "calculator": 5,
            "code_executor": 2,
        }

    means individual tools may have their own execution limits.

    Tools not present in per_tool_limits have no individual
    tool-specific limit and are still subject to max_tool_calls.

        timeout_seconds = N

    means the runtime permits the entire execution to continue
    for at most N seconds of wall-clock execution time.

    The timeout is an execution-wide budget.

    Hard timeout enforcement is performed around asynchronous
    routing, inference, and tool-execution boundaries using
    asyncio.wait_for().

    This means a long-running asynchronous operation is cancelled
    when the remaining execution budget is exhausted.
    """

    def __init__(
        self,
        *,
        router: SemanticRouterClient,
        inference: InferenceClient,
        tools: ToolRegistry,
        planner: Planner,
        max_steps: int,
        tool_executor: ToolExecutor | None = None,
        sandbox: ToolSandboxClient | None = None,
        max_tool_calls: int = 20,
        max_repeated_tool_calls: int = 3,
        timeout_seconds: float = 60.0,
        per_tool_limits: dict[str, int] | None = None,
    ) -> None:
        if max_steps <= 0:
            raise ValueError(
                "max_steps must be greater than zero"
            )

        self.limits = ExecutionLimits(
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
            max_repeated_tool_calls=max_repeated_tool_calls,
            timeout_seconds=timeout_seconds,
            per_tool_limits=dict(
                per_tool_limits or {}
            ),
        )

        self.router = router
        self.inference = inference
        self.tools = tools
        self.planner = planner

        # Retained for backward compatibility with existing
        # callers and tests.
        self.max_steps = max_steps

        if tool_executor is not None:
            self.tool_executor = tool_executor
        else:
            if sandbox is None:
                raise ValueError(
                    "Either tool_executor or sandbox must be provided"
                )

            self.tool_executor = ToolExecutor(
                registry=tools,
                sandbox=sandbox,
            )

    async def run(
        self,
        intent: str,
        *,
        session_id: str | None = None,
        task: str | None = None,
        required_capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentResponse:
        """
        Execute an agent request from start to finish.

        Any failure is recorded on the Execution before being
        propagated to the caller.
        """

        execution = Execution()

        context = ExecutionContext(
            execution=execution,
            metadata=dict(metadata or {}),
        )

        resolved_session_id = (
            session_id or str(execution.id)
        )

        resolved_task = (
            task if task is not None else intent
        )

        context.metadata["session_id"] = resolved_session_id
        context.metadata["task"] = resolved_task

        try:
            execution.transition_to(
                ExecutionState.PLANNING
            )

            output = await self._execute(
                execution=execution,
                context=context,
                intent=intent,
                session_id=resolved_session_id,
                task=resolved_task,
                required_capabilities=required_capabilities,
            )

            execution.transition_to(
                ExecutionState.COMPLETED
            )

            result = ExecutionResult.from_execution(
                execution,
                output=output,
            )

            return self._to_agent_response(
                result=result,
                context=context,
            )

        except Exception as exc:
            execution.mark_failed(
                error=str(exc),
                error_type=type(exc).__name__,
            )

            context.add_error(
                str(exc)
            )

            logger.exception(
                "Agent execution failed",
                extra={
                    "execution_id": str(execution.id),
                    "error_type": type(exc).__name__,
                },
            )

            raise

    def _remaining_timeout(
        self,
        started_at: float,
    ) -> float:
        """
        Return the remaining execution timeout.

        The timeout is an execution-wide budget rather than a
        per-operation timeout.

        Raises:
            ExecutionLimitExceeded:
                If the execution budget has already expired.
        """

        elapsed = time.monotonic() - started_at

        remaining = (
            self.limits.timeout_seconds - elapsed
        )

        if remaining <= 0:
            raise ExecutionLimitExceeded(
                "Agent execution exceeded timeout: "
                f"{self.limits.timeout_seconds} seconds"
            )

        return remaining

    async def _execute(
        self,
        *,
        execution: Execution,
        context: ExecutionContext,
        intent: str,
        session_id: str,
        task: str,
        required_capabilities: list[str] | None,
    ) -> str:
        """
        Execute the agent reasoning loop.

        Returns:
            Final answer generated by the agent.

        Raises:
            AgentMaxStepsError:
                When the configured execution step limit is
                exhausted without producing a final answer.

            ExecutionLimitExceeded:
                When the execution timeout or another execution
                limit is exceeded.
        """

        # =========================================================
        # EXECUTION TIMER
        # =========================================================

        execution_started_at = time.monotonic()

        # =========================================================
        # REPEATED TOOL CALL TRACKING
        # =========================================================
        #
        # Key:
        #
        #     (tool_name, serialized_arguments)
        #
        # This state belongs to one execution only.
        # =========================================================

        repeated_tool_calls: dict[
            tuple[str, str],
            int,
        ] = {}

        # =========================================================
        # PER-TOOL CALL TRACKING
        # =========================================================
        #
        # Key:
        #
        #     tool_name
        #
        # Example:
        #
        #     calculator -> 3
        #     code_executor -> 1
        #
        # This allows each configured tool to have its own
        # execution limit.
        # =========================================================

        tool_call_counts: dict[
            str,
            int,
        ] = {}

        # =========================================================
        # PLAN
        # =========================================================

        plan_step = self._start_step(
            execution=execution,
            step_type=StepType.PLAN,
            input={
                "intent": intent,
                "task": task,
                "session_id": session_id,
                "required_capabilities": required_capabilities,
            },
        )

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

        context.current_plan = task

        plan_step.output = {
            "task": task,
            "session_id": session_id,
        }

        plan_step.mark_completed()

        # =========================================================
        # TIMEOUT CHECK AFTER PLANNING
        # =========================================================

        self.limits.validate_timeout(
            execution_started_at
        )

        # =========================================================
        # TOOL DEFINITIONS
        # =========================================================

        tool_definitions = self.tools.definitions()

        # =========================================================
        # ROUTING
        # =========================================================

        self.limits.validate_timeout(
            execution_started_at
        )

        try:
            remaining_timeout = self._remaining_timeout(
                execution_started_at
            )

            route = await asyncio.wait_for(
                self.router.route(
                    session_id=session_id,
                    task=task,
                    messages=context.messages,
                    required_capabilities=required_capabilities,
                ),
                timeout=remaining_timeout,
            )

        except asyncio.TimeoutError as exc:
            error = (
                "Agent routing exceeded execution timeout: "
                f"{self.limits.timeout_seconds} seconds"
            )

            raise ExecutionLimitExceeded(
                error
            ) from exc

        self.limits.validate_timeout(
            execution_started_at
        )

        selected_model = route.model

        context.metadata["model"] = selected_model
        context.metadata["provider"] = route.provider

        logger.info(
            "Agent request routed",
            extra={
                "execution_id": str(execution.id),
                "session_id": session_id,
                "model": selected_model,
                "provider": route.provider,
            },
        )

        # =========================================================
        # REASONING LOOP
        # =========================================================

        for step_number in range(
            1,
            self.limits.max_steps + 1,
        ):
            context.current_step = step_number

            # -----------------------------------------------------
            # STEP LIMIT
            # -----------------------------------------------------

            self.limits.validate_step(
                step_number
            )

            # -----------------------------------------------------
            # EXECUTION TIME LIMIT
            # -----------------------------------------------------

            self.limits.validate_timeout(
                execution_started_at
            )

            # -----------------------------------------------------
            # INFERENCE STATE
            # -----------------------------------------------------

            if execution.state is not ExecutionState.INFERENCE:
                execution.transition_to(
                    ExecutionState.INFERENCE
                )

            # -----------------------------------------------------
            # INFERENCE STEP
            # -----------------------------------------------------

            inference_step = self._start_step(
                execution=execution,
                step_type=StepType.INFERENCE,
                input={
                    "model": selected_model,
                    "messages": list(context.messages),
                    "tools": tool_definitions,
                    "step": step_number,
                },
            )

            try:
                remaining_timeout = self._remaining_timeout(
                    execution_started_at
                )

                inference_response = await asyncio.wait_for(
                    self.inference.complete(
                        model=selected_model,
                        messages=context.messages,
                        tools=tool_definitions,
                    ),
                    timeout=remaining_timeout,
                )

                inference_step.output = (
                    inference_response
                )

                inference_step.mark_completed()

            except asyncio.TimeoutError as exc:
                error = (
                    "Agent inference exceeded execution timeout: "
                    f"{self.limits.timeout_seconds} seconds"
                )

                inference_step.mark_failed(
                    error=error
                )

                raise ExecutionLimitExceeded(
                    error
                ) from exc

            except Exception as exc:
                inference_step.mark_failed(
                    error=str(exc)
                )

                raise

            # -----------------------------------------------------
            # TIMEOUT CHECK AFTER INFERENCE
            # -----------------------------------------------------

            self.limits.validate_timeout(
                execution_started_at
            )

            # -----------------------------------------------------
            # PLANNER
            # -----------------------------------------------------

            decision = self.planner.plan(
                response=inference_response,
                context=context,
            )

            logger.debug(
                "Agent planner decision",
                extra={
                    "execution_id": str(execution.id),
                    "step": step_number,
                    "decision_type": str(
                        decision.type
                    ),
                },
            )

            # =====================================================
            # FINAL
            # =====================================================

            if decision.is_final:
                final_step = self._start_step(
                    execution=execution,
                    step_type=StepType.FINAL,
                    input={
                        "decision": decision.type.value,
                    },
                )

                output = decision.content or ""

                final_step.output = output

                final_step.mark_completed()

                return output

            # =====================================================
            # CONTINUE
            # =====================================================

            if decision.is_continue:
                logger.info(
                    "Agent requested another inference step",
                    extra={
                        "execution_id": str(execution.id),
                        "step": step_number,
                    },
                )

                continue

            # =====================================================
            # FAILURE
            # =====================================================

            if decision.is_failure:
                error = (
                    decision.error
                    or "Agent returned a failure decision"
                )

                logger.error(
                    "Agent planner returned failure",
                    extra={
                        "execution_id": str(execution.id),
                        "step": step_number,
                        "error": error,
                    },
                )

                raise RuntimeError(error)

            # =====================================================
            # TOOL CALL
            # =====================================================

            if decision.is_tool_call:
                await self._execute_tool_call(
                    execution=execution,
                    context=context,
                    inference_response=inference_response,
                    decision=decision,
                    execution_started_at=execution_started_at,
                    repeated_tool_calls=repeated_tool_calls,
                    tool_call_counts=tool_call_counts,
                )

                continue

            # =====================================================
            # UNKNOWN DECISION
            # =====================================================

            raise AgentProtocolError(
                "Unsupported agent decision type: "
                f"{decision.type}"
            )

        # =========================================================
        # EXECUTION LIMIT
        # =========================================================

        raise AgentMaxStepsError(
            "Agent exceeded maximum steps: "
            f"{self.max_steps}"
        )

    async def _execute_tool_call(
        self,
        *,
        execution: Execution,
        context: ExecutionContext,
        inference_response: Any,
        decision: AgentDecision,
        execution_started_at: float,
        repeated_tool_calls: dict[
            tuple[str, str],
            int,
        ],
        tool_call_counts: dict[
            str,
            int,
        ],
    ) -> None:
        """
        Execute one tool call and append its observation to context.

        Limits are checked before the actual ToolExecutor
        invocation:

        1. Global tool-call limit
        2. Per-tool call limit
        3. Repeated identical tool-call limit
        4. Execution timeout

        A rejected call never reaches the ToolExecutor or Sandbox.
        """

        tool_name = decision.tool_name
        call_id = decision.call_id
        arguments = dict(
            decision.arguments
        )

        # =========================================================
        # VALIDATE TOOL CALL
        # =========================================================

        if not tool_name:
            raise AgentProtocolError(
                "Tool call is missing tool name"
            )

        if not call_id:
            raise AgentProtocolError(
                "Tool call is missing call_id"
            )

        if not self.tools.has(tool_name):
            raise AgentProtocolError(
                "Unknown tool requested by model: "
                f"{tool_name}"
            )

        # =========================================================
        # GLOBAL TOOL CALL LIMIT
        # =========================================================

        self.limits.validate_tool_call(
            context.tool_call_count
        )

        # =========================================================
        # PER-TOOL CALL LIMIT
        # =========================================================
        #
        # Example:
        #
        #     per_tool_limits = {
        #         "calculator": 3,
        #     }
        #
        # Calls:
        #
        #     calculator #1 -> allowed
        #     calculator #2 -> allowed
        #     calculator #3 -> allowed
        #     calculator #4 -> rejected
        #
        # The rejected call never reaches the sandbox.
        # =========================================================

        tool_call_count = tool_call_counts.get(
            tool_name,
            0,
        )

        self.limits.validate_per_tool_call(
            tool_name,
            tool_call_count,
        )

        # =========================================================
        # REPEATED TOOL CALL LIMIT
        # =========================================================
        #
        # JSON serialization with sorted keys ensures equivalent
        # dictionaries produce the same identity even when their
        # insertion order differs.
        # =========================================================

        tool_call_key = (
            tool_name,
            json.dumps(
                arguments,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

        repeated_count = repeated_tool_calls.get(
            tool_call_key,
            0,
        )

        self.limits.validate_repeated_tool_call(
            repeated_count
        )

        # =========================================================
        # REGISTER THE ATTEMPT
        # =========================================================
        #
        # The call is registered only after all policy checks have
        # passed. Therefore rejected calls are not counted.
        # =========================================================

        repeated_tool_calls[tool_call_key] = (
            repeated_count + 1
        )

        tool_call_counts[tool_name] = (
            tool_call_count + 1
        )

        # =========================================================
        # EXECUTION TIME LIMIT
        # =========================================================

        self.limits.validate_timeout(
            execution_started_at
        )

        # =========================================================
        # ASSISTANT MESSAGE
        # =========================================================

        assistant_message = (
            self._extract_assistant_message(
                inference_response
            )
        )

        context.add_message(
            assistant_message
        )

        # =========================================================
        # TOOL CALL STEP
        # =========================================================

        tool_call_step = self._start_step(
            execution=execution,
            step_type=StepType.TOOL_CALL,
            input={
                "call_id": call_id,
                "tool_name": tool_name,
                "arguments": arguments,
            },
        )

        tool_call_step.output = {
            "call_id": call_id,
            "tool_name": tool_name,
        }

        tool_call_step.mark_completed()

        # =========================================================
        # TOOL EXECUTION
        # =========================================================

        execution.transition_to(
            ExecutionState.TOOL_EXECUTION
        )

        tool_result_step = self._start_step(
            execution=execution,
            step_type=StepType.TOOL_RESULT,
            input={
                "call_id": call_id,
                "tool_name": tool_name,
                "arguments": arguments,
            },
        )

        # ---------------------------------------------------------
        # TIMEOUT CHECK BEFORE TOOL EXECUTION
        # ---------------------------------------------------------

        self.limits.validate_timeout(
            execution_started_at
        )

        try:
            remaining_timeout = self._remaining_timeout(
                execution_started_at
            )

            tool_result = await asyncio.wait_for(
                self.tool_executor.execute(
                    name=tool_name,
                    arguments=arguments,
                ),
                timeout=remaining_timeout,
            )

        except asyncio.TimeoutError as exc:
            error = (
                "Agent tool execution exceeded execution timeout: "
                f"{self.limits.timeout_seconds} seconds"
            )

            tool_result_step.mark_failed(
                error=error
            )

            raise ExecutionLimitExceeded(
                error
            ) from exc

        except Exception as exc:
            tool_result_step.mark_failed(
                error=str(exc)
            )

            raise

        # =========================================================
        # TIMEOUT CHECK AFTER TOOL EXECUTION
        # =========================================================

        self.limits.validate_timeout(
            execution_started_at
        )

        # =========================================================
        # TOOL FAILURE
        # =========================================================

        if tool_result.failed:
            error = (
                tool_result.error
                or f"Tool execution failed: {tool_name}"
            )

            error_type = tool_result.metadata.get(
                "error_type"
            )

            tool_result_step.mark_failed(
                error=error
            )

            if error_type == "unknown_tool":
                raise AgentProtocolError(
                    "Unknown tool requested by model: "
                    f"{tool_name}"
                )

            raise ToolExecutionError(
                error
            )

        # =========================================================
        # TOOL SUCCESS
        # =========================================================

        tool_result_step.output = (
            tool_result.output
        )

        tool_result_step.mark_completed()

        context.add_tool_call(
            {
                "id": call_id,
                "name": tool_name,
                "arguments": arguments,
                "result": tool_result.output,
            }
        )

        # =========================================================
        # OBSERVATION
        # =========================================================

        execution.transition_to(
            ExecutionState.OBSERVING
        )

        observation = (
            self._normalize_tool_output(
                tool_result.output
            )
        )

        observation_step = self._start_step(
            execution=execution,
            step_type=StepType.OBSERVATION,
            input={
                "call_id": call_id,
                "tool_name": tool_name,
            },
        )

        observation_step.output = observation

        observation_step.mark_completed()

        context.add_observation(
            observation
        )

        # =========================================================
        # TOOL MESSAGE
        # =========================================================

        context.add_message(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": tool_name,
                "content": observation,
            }
        )

    @staticmethod
    def _start_step(
        *,
        execution: Execution,
        step_type: StepType,
        input: Any = None,
    ) -> Step:
        """
        Create, start, and attach a new execution step.
        """

        step = Step(
            number=len(execution.steps) + 1,
            type=step_type,
            input=input,
        )

        step.mark_started()

        execution.add_step(
            step
        )

        return step

    @staticmethod
    def _extract_assistant_message(
        inference_response: Any,
    ) -> dict[str, Any]:
        """
        Extract the assistant message from an inference response.
        """

        # =========================================================
        # DICT RESPONSE
        # =========================================================

        if isinstance(
            inference_response,
            dict,
        ):
            direct_message = inference_response.get(
                "message"
            )

            if isinstance(
                direct_message,
                dict,
            ):
                return direct_message

            choices = inference_response.get(
                "choices"
            )

            if (
                isinstance(choices, list)
                and choices
            ):
                first_choice = choices[0]

                if not isinstance(
                    first_choice,
                    dict,
                ):
                    raise AgentProtocolError(
                        "Inference choice must be an object"
                    )

                message = first_choice.get(
                    "message"
                )

                if isinstance(
                    message,
                    dict,
                ):
                    return message

            raise AgentProtocolError(
                "Inference response does not contain "
                "a valid assistant message"
            )

        # =========================================================
        # OBJECT RESPONSE
        # =========================================================

        direct_message = getattr(
            inference_response,
            "message",
            None,
        )

        if direct_message is not None:
            return AgentRuntime._message_to_dict(
                direct_message
            )

        choices = getattr(
            inference_response,
            "choices",
            None,
        )

        if choices:
            first_choice = choices[0]

            message = getattr(
                first_choice,
                "message",
                None,
            )

            if message is not None:
                return AgentRuntime._message_to_dict(
                    message
                )

        raise AgentProtocolError(
            "Inference response does not contain "
            "a valid assistant message"
        )

    @staticmethod
    def _message_to_dict(
        message: Any,
    ) -> dict[str, Any]:
        """
        Convert an inference message object into a dictionary.
        """

        if isinstance(
            message,
            dict,
        ):
            return message

        if hasattr(
            message,
            "model_dump",
        ):
            dumped = message.model_dump()

            if isinstance(
                dumped,
                dict,
            ):
                return dumped

        if hasattr(
            message,
            "dict",
        ):
            dumped = message.dict()

            if isinstance(
                dumped,
                dict,
            ):
                return dumped

        role = getattr(
            message,
            "role",
            None,
        )

        content = getattr(
            message,
            "content",
            None,
        )

        tool_calls = getattr(
            message,
            "tool_calls",
            None,
        )

        if role is None:
            raise AgentProtocolError(
                "Assistant message is missing role"
            )

        result: dict[str, Any] = {
            "role": role,
            "content": content,
        }

        if tool_calls is not None:
            result["tool_calls"] = tool_calls

        return result

    @staticmethod
    def _normalize_tool_output(
        output: Any,
    ) -> str:
        """
        Normalize arbitrary tool output into a string.
        """

        if isinstance(
            output,
            str,
        ):
            return output

        if output is None:
            return ""

        return str(output)

    @staticmethod
    def _to_agent_response(
        *,
        result: ExecutionResult,
        context: ExecutionContext,
    ) -> AgentResponse:
        """
        Convert the internal execution result into the public
        API response model.
        """

        tool_calls: list[ToolCallResult] = []

        for tool_call in context.tool_calls:
            if not isinstance(
                tool_call,
                dict,
            ):
                continue

            name = tool_call.get(
                "name"
            )

            arguments = tool_call.get(
                "arguments"
            )

            output = tool_call.get(
                "result"
            )

            if not isinstance(
                name,
                str,
            ):
                continue

            if not isinstance(
                arguments,
                dict,
            ):
                arguments = {}

            tool_calls.append(
                ToolCallResult(
                    name=name,
                    arguments=arguments,
                    result=AgentRuntime._normalize_tool_output(
                        output
                    ),
                )
            )

        status = (
            "success"
            if result.succeeded
            else str(result.status)
        )

        return AgentResponse(
            execution_id=str(
                result.execution_id
            ),
            status=status,
            answer=AgentRuntime._normalize_tool_output(
                result.output
            ),
            steps=context.current_step,
            tool_calls=tool_calls,
        )
