from __future__ import annotations

from typing import Any

from app.agent_runtime.domain import (
    AgentDecision,
    DecisionType,
    Execution,
    ExecutionContext,
    ExecutionResult,
    ExecutionState,
    ExecutionStatus,
    Step,
    StepType,
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
    - record execution steps
    - maintain conversation messages
    - drive the execution state machine
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

    Execution lifecycle:

        CREATED
           |
           v
        PLANNING
           |
           v
        INFERENCE
         /      \
        v        v
    TOOL_EXECUTION  COMPLETED
        |
        v
    OBSERVING
        |
        v
    INFERENCE

    Decision handling:

        FINAL
          -> COMPLETED

        TOOL_CALL
          -> TOOL_EXECUTION
          -> OBSERVING
          -> INFERENCE

        CONTINUE
          -> INFERENCE

        FAIL
          -> FAILED

    Any active state may transition to FAILED or CANCELLED.
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
            raise ValueError(
                "max_steps must be greater than zero"
            )

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
        """
        Run one complete agent execution.

        Runtime owns the top-level execution lifecycle.

        Initial transition:

            CREATED -> PLANNING

        Successful execution:

            ... -> INFERENCE -> COMPLETED

        Failure:

            active state -> FAILED
        """

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

        # ---------------------------------------------------------
        # EXECUTION STATE: CREATED -> PLANNING
        # ---------------------------------------------------------

        execution.transition_to(
            ExecutionState.PLANNING
        )

        try:
            result = await self._execute(
                context=context,
                intent=intent,
                session_id=session_id,
                task=task,
                required_capabilities=required_capabilities,
            )

        except Exception as exc:
            # -----------------------------------------------------
            # EXECUTION STATE: ACTIVE -> FAILED
            # -----------------------------------------------------

            execution.mark_failed(
                error=str(exc),
                error_type=type(exc).__name__,
            )

            context.add_error(
                str(exc)
            )

            logger.exception(
                "agent_execution_failed "
                "execution_id=%s error_type=%s",
                execution.id,
                type(exc).__name__,
            )

            raise

        # ---------------------------------------------------------
        # EXECUTION STATE: INFERENCE -> COMPLETED
        # ---------------------------------------------------------

        execution.transition_to(
            ExecutionState.COMPLETED
        )

        # Rebuild the result after the lifecycle transition so the
        # returned result contains the authoritative COMPLETED state.
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
            steps=int(
                result.metadata.get(
                    "steps",
                    0,
                )
            ),
            tool_calls=result.metadata.get(
                "tool_calls",
                [],
            ),
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
        execution = context.execution

        # ---------------------------------------------------------
        # STEP: PLAN
        # ---------------------------------------------------------

        plan_step = self._start_step(
            context=context,
            step_type=StepType.PLAN,
            input={
                "intent": intent,
                "task": task,
                "required_capabilities": (
                    required_capabilities or []
                ),
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

        tool_definitions = self.tools.definitions()

        # Router selection belongs to the planning phase.
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

        execution.metadata.update(
            {
                "model": decision.model,
                "provider": decision.provider,
            }
        )

        plan_step.mark_completed(
            output={
                "model": decision.model,
                "provider": decision.provider,
                "tool_count": len(tool_definitions),
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

        for step in range(
            1,
            self.max_steps + 1,
        ):
            context.current_step = step

            logger.info(
                "agent_step_started "
                "execution_id=%s step=%s model=%s state=%s",
                execution.id,
                step,
                selected_model,
                execution.state,
            )

            # -----------------------------------------------------
            # EXECUTION STATE -> INFERENCE
            # -----------------------------------------------------

            if execution.state is ExecutionState.PLANNING:
                execution.transition_to(
                    ExecutionState.INFERENCE
                )

            elif execution.state is ExecutionState.OBSERVING:
                execution.transition_to(
                    ExecutionState.INFERENCE
                )

            elif execution.state is not ExecutionState.INFERENCE:
                raise RuntimeError(
                    "Agent runtime reached inference loop "
                    "from invalid execution state "
                    f"'{execution.state.value}'"
                )

            # -----------------------------------------------------
            # STEP: INFERENCE
            # -----------------------------------------------------

            inference_step = self._start_step(
                context=context,
                step_type=StepType.INFERENCE,
                input={
                    "model": selected_model,
                    "messages": list(
                        context.messages
                    ),
                    "tools": tool_definitions,
                },
            )

            try:
                response = await self.inference.complete(
                    model=selected_model,
                    messages=context.messages,
                    tools=tool_definitions,
                )

            except Exception as exc:
                inference_step.mark_failed(
                    error=str(exc),
                )
                raise

            else:
                inference_step.mark_completed(
                    output=response,
                )

            # Planner owns inference-response interpretation.
            decision = self.planner.plan(
                response=response,
                context=context,
            )

            # -----------------------------------------------------
            # FINAL RESPONSE
            # -----------------------------------------------------

            if decision.is_final:
                final_step = self._start_step(
                    context=context,
                    step_type=StepType.FINAL,
                    input={
                        "content": decision.content,
                    },
                )

                final_step.mark_completed(
                    output=decision.content,
                )

                return self._complete_execution(
                    context=context,
                    output=decision.content,
                    step=step,
                    executed_tools=executed_tools,
                )

            # -----------------------------------------------------
            # TOOL CALL
            # -----------------------------------------------------

            if decision.is_tool_call:
                assert decision.tool_name is not None
                assert decision.call_id is not None

                tool_name = decision.tool_name
                arguments = decision.arguments
                call_id = decision.call_id

                # -------------------------------------------------
                # EXECUTION STATE:
                #
                # INFERENCE -> TOOL_EXECUTION
                # -------------------------------------------------

                execution.transition_to(
                    ExecutionState.TOOL_EXECUTION
                )

                assistant_message = (
                    self._extract_assistant_message(
                        response
                    )
                )

                context.add_message(
                    assistant_message
                )

                context.add_tool_call(
                    {
                        "name": tool_name,
                        "arguments": arguments,
                        "call_id": call_id,
                        "step": step,
                    }
                )

                # -------------------------------------------------
                # STEP: TOOL CALL
                # -------------------------------------------------

                tool_step = self._start_step(
                    context=context,
                    step_type=StepType.TOOL_CALL,
                    input={
                        "name": tool_name,
                        "arguments": arguments,
                        "call_id": call_id,
                    },
                )

                logger.info(
                    "agent_tool_execution_started "
                    "execution_id=%s step=%s tool=%s state=%s",
                    execution.id,
                    step,
                    tool_name,
                    execution.state,
                )

                try:
                    result = await self.sandbox.execute(
                        tool_name,
                        arguments,
                    )

                except Exception as exc:
                    tool_step.mark_failed(
                        error=str(exc),
                    )
                    raise

                else:
                    tool_step.mark_completed(
                        output=result,
                    )

                # -------------------------------------------------
                # STEP: TOOL RESULT
                # -------------------------------------------------

                tool_result_step = self._start_step(
                    context=context,
                    step_type=StepType.TOOL_RESULT,
                    input={
                        "tool_call_id": call_id,
                        "tool_name": tool_name,
                    },
                )

                tool_result_step.mark_completed(
                    output=result,
                )

                executed_tools.append(
                    ToolCallResult(
                        name=tool_name,
                        arguments=arguments,
                        result=result,
                    )
                )

                # -------------------------------------------------
                # EXECUTION STATE:
                #
                # TOOL_EXECUTION -> OBSERVING
                # -------------------------------------------------

                execution.transition_to(
                    ExecutionState.OBSERVING
                )

                # -------------------------------------------------
                # STEP: OBSERVATION
                # -------------------------------------------------

                observation = (
                    f"Tool '{tool_name}' returned: {result}"
                )

                context.add_observation(
                    observation
                )

                observation_step = self._start_step(
                    context=context,
                    step_type=StepType.OBSERVATION,
                    input={
                        "tool_name": tool_name,
                    },
                )

                observation_step.mark_completed(
                    output=observation,
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
                    "execution_id=%s step=%s tool=%s state=%s",
                    execution.id,
                    step,
                    tool_name,
                    execution.state,
                )

                # The next iteration performs:
                #
                # OBSERVING -> INFERENCE
                #
                # before calling the inference service again.
                continue

            # -----------------------------------------------------
            # CONTINUE
            # -----------------------------------------------------
            #
            # CONTINUE means that the Planner has determined that
            # the agent should perform another inference iteration.
            #
            # We deliberately do NOT transition through PLANNING or
            # OBSERVING here.
            #
            # The execution is already in INFERENCE, therefore the
            # next loop iteration simply performs another inference.
            #
            # max_steps remains the hard safety boundary.
            # -----------------------------------------------------

            if decision.is_continue:
                logger.info(
                    "agent_decision_continue "
                    "execution_id=%s step=%s state=%s",
                    execution.id,
                    step,
                    execution.state,
                )

                continue

            # -----------------------------------------------------
            # FAIL
            # -----------------------------------------------------
            #
            # FAIL is an explicit decision from the Planner telling
            # the Runtime that execution cannot continue.
            #
            # Runtime raises an exception here instead of directly
            # changing the execution state.
            #
            # The top-level run() method owns:
            #
            #       ACTIVE -> FAILED
            #
            # This keeps failure lifecycle management centralized.
            # -----------------------------------------------------

            if decision.is_failure:
                error = (
                    decision.error
                    or "Agent returned a failure decision"
                )

                logger.error(
                    "agent_decision_failure "
                    "execution_id=%s step=%s error=%s",
                    execution.id,
                    step,
                    error,
                )

                raise RuntimeError(
                    error
                )

            # -----------------------------------------------------
            # UNKNOWN DECISION
            # -----------------------------------------------------

            raise RuntimeError(
                "Unsupported agent decision type: "
                f"{decision.type}"
            )

        # ---------------------------------------------------------
        # MAX STEPS EXCEEDED
        # ---------------------------------------------------------

        raise AgentMaxStepsError(
            "Agent exceeded maximum steps: "
            f"{self.max_steps}"
        )

    @staticmethod
    def _start_step(
        *,
        context: ExecutionContext,
        step_type: StepType,
        input: Any = None,
    ) -> Step:
        """
        Create, start, and attach a Step to the current execution.
        """

        step = Step(
            number=len(
                context.execution.steps
            ) + 1,
            type=step_type,
            input=input,
        )

        step.mark_started()

        context.execution.add_step(
            step
        )

        return step

    @staticmethod
    def _extract_assistant_message(
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Extract the assistant message after Planner has already
        validated the inference response.

        Planner remains responsible for protocol validation.
        """

        choices = response.get(
            "choices"
        )

        if (
            not isinstance(choices, list)
            or not choices
        ):
            raise RuntimeError(
                "Planner accepted an inference response "
                "without choices"
            )

        choice = choices[0]

        if not isinstance(
            choice,
            dict,
        ):
            raise RuntimeError(
                "Planner accepted an invalid "
                "inference choice"
            )

        message = choice.get(
            "message"
        )

        if not isinstance(
            message,
            dict,
        ):
            raise RuntimeError(
                "Planner accepted an inference response "
                "without message"
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
        """
        Build the execution result payload.

        The actual transition to COMPLETED is intentionally performed
        by run() after _execute() succeeds.

        This keeps lifecycle ownership centralized in run().
        """

        if not isinstance(
            output,
            str,
        ):
            raise RuntimeError(
                "Planner produced a final decision "
                "without string content"
            )

        context.metadata.update(
            {
                "steps": step,
                "tool_calls": list(
                    executed_tools
                ),
            }
        )

        context.execution.metadata.update(
            {
                "steps": step,
                "tool_calls": list(
                    executed_tools
                ),
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
                "Cannot create successful AgentResponse "
                "from execution with status "
                f"'{result.status}'"
            )

        if not isinstance(
            result.output,
            str,
        ):
            raise RuntimeError(
                "Execution completed without string output"
            )

        return AgentResponse(
            execution_id=str(
                result.execution_id
            ),
            status="success",
            answer=result.output,
            steps=steps,
            tool_calls=tool_calls,
        )
