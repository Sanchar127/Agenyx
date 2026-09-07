from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from app.agent_runtime.approval import (
    ApprovalAlreadyResolvedError,
    ApprovalManager,
    ApprovalNotFoundError,
    ApprovalPolicy,
    ApprovalStatus,
)
from app.agent_runtime.cancellation import CancellationToken
from app.agent_runtime.context_manager import (
    ContextBudget,
    ContextManager,
)
from app.agent_runtime.domain import (
    AgentDecision,
    Execution,
    ExecutionContext,
    ExecutionResult,
    ExecutionState,
    Step,
    StepType,
    ToolCall,
)
from app.agent_runtime.event_stream import EventStream
from app.agent_runtime.event_types import AgentEventType
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.execution_limits import ExecutionLimits
from app.agent_runtime.persistence.service import (
    ExecutionPersistence,
)
from app.agent_runtime.planner import Planner
from app.agent_runtime.prompts import SYSTEM_PROMPT
from app.agent_runtime.submission import ExecutionSubmission
from app.core.errors import (
    AgentMaxStepsError,
    AgentProtocolError,
    ExecutionCancelled,
    ExecutionLimitExceeded,
    ToolExecutionError,
)
from app.core.logging import logger
from app.inference.client import InferenceClient
from app.models.responses import (
    AgentResponse,
    ToolCallResult,
)
from app.router.client import SemanticRouterClient
from app.sandbox.client import ToolSandboxClient
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry


@dataclass
class _ExecutionRecord:
    """
    Runtime-owned record for one agent execution.

    The record groups together:

    - domain execution state
    - cancellation state
    - asyncio task
    - event stream
    - completed execution result

    Unlike _ActiveExecution, this record can represent both
    running and completed executions.

    This is intentionally an in-memory runtime abstraction.
    Persistent execution storage can be introduced later without
    changing the execution domain model.
    """

    execution: Execution
    token: CancellationToken
    task: asyncio.Task[Any] | None = None
    event_stream: EventStream | None = None
    result: ExecutionResult | None = None


@dataclass(frozen=True)
class _ToolExecutionResult:
    """
    Internal result produced by one concurrently executed tool.

    Concurrent tool execution does not mutate shared
    ExecutionContext.

    Results are applied later in deterministic model-request order.
    """

    tool_call: ToolCall
    output: Any


class AgentRuntime:
    """
    Orchestrates a complete agent execution.

    Responsibilities:
    - create and manage execution state
    - create and manage ExecutionContext
    - manage LLM-facing context through ContextManager
    - enforce context-window/token budgets
    - route the request to an appropriate model
    - call the inference service
    - interpret inference output through the Planner
    - execute requested tools
    - execute independent tool calls concurrently
    - manage human approval for configured tools
    - feed tool observations back into inference
    - enforce execution limits
    - support explicit execution cancellation
    - emit runtime execution events
    - retain an in-process execution record
    - optionally persist durable execution state/results/events
    - produce the public AgentResponse

    Provider/model-specific logic does not belong here.

    The runtime communicates with the separate InferenceClient
    abstraction.

    Context management:

        ExecutionContext
            owns execution state/history.

        ContextManager
            owns LLM-facing context construction and token
            management.

    The complete ExecutionContext history is preserved, while
    ContextManager creates a bounded inference view when the
    configured context budget is exceeded.

    Execution limits:

        max_steps = N

    permits at most N reasoning/inference iterations.

        max_tool_calls = N

    permits at most N total tool executions.

        max_repeated_tool_calls = N

    permits at most N executions of the same tool with the same
    arguments during one execution.

        per_tool_limits = {
            "calculator": 5,
            "code_executor": 2,
        }

    gives individual tools their own execution limits.

        timeout_seconds = N

    defines the execution-wide wall-clock budget.

        max_parallel_tool_calls = N

    limits how many tool executions from one model decision may
    execute concurrently.

    Context limits:

        max_context_tokens = N

    defines the maximum input context budget.

        reserved_output_tokens = N

    reserves part of the model context window for generated output.

    Therefore:

        available_input_tokens =
            max_context_tokens - reserved_output_tokens

    Human approval:

        ApprovalPolicy
            decides whether a tool call requires approval.

        ApprovalManager
            creates and resolves approval requests.

    A tool requiring approval is never sent to ToolExecutor until
    its approval request has been explicitly approved.

    Approval is associated with the exact execution_id and call_id
    so that approval cannot accidentally authorize another tool
    invocation.

    Parallel execution semantics:

        - The Planner validates the complete tool-call batch.
        - The runtime validates the complete batch against budgets.
        - Approval requirements are evaluated before execution.
        - A batch containing an approval-required tool waits before
          any tool in that batch executes.
        - Approved calls may execute concurrently.
        - Concurrency is bounded by max_parallel_tool_calls.
        - The execution-wide timeout applies to the complete batch.
        - Normal tool failure does not cancel sibling tool calls.
        - Cancellation cancels all active sibling calls.
        - Results are applied to ExecutionContext in original model
          order.

    Event streaming semantics:

        - Every execution receives its own EventStream.
        - Runtime events are published through _publish_event().
        - Event-stream failures never fail agent execution.
        - Terminal execution events are emitted before the stream
          is closed.
        - Raw inference responses and raw tool outputs are not
          exposed through runtime events.
        - Parallel tool events represent actual execution timing,
          not deterministic model ordering.

    Execution registry semantics:

        _active_executions
            Contains only executions currently running.

        _executions
            Contains the runtime record for executions known to this
            process, including completed/failed/cancelled executions.

        This separation allows existing cancellation and streaming
        semantics to remain unchanged while preparing the runtime
        for asynchronous execution submission and execution-status
        APIs.

    Persistence semantics:

        persistence=None
            Persistence is disabled. This preserves lightweight
            unit-test and local-runtime behavior.

        persistence=<ExecutionPersistence>
            Durable execution state, events, and terminal results
            can be persisted without coupling the runtime directly
            to PostgreSQL or SQLAlchemy.
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
        max_parallel_tool_calls: int = 4,
        max_context_tokens: int | None = None,
        reserved_output_tokens: int = 0,
        approval_policy: ApprovalPolicy | None = None,
        approval_manager: ApprovalManager | None = None,
        persistence: ExecutionPersistence | None = None,
    ) -> None:
        if max_steps <= 0:
            raise ValueError(
                "max_steps must be greater than zero"
            )

        if max_parallel_tool_calls <= 0:
            raise ValueError(
                "max_parallel_tool_calls must be greater "
                "than zero"
            )

        if max_context_tokens is not None and max_context_tokens <= 0:
            raise ValueError(
                "max_context_tokens must be greater "
                "than zero when provided"
            )

        if reserved_output_tokens < 0:
            raise ValueError(
                "reserved_output_tokens cannot be negative"
            )

        if (
            max_context_tokens is not None
            and reserved_output_tokens >= max_context_tokens
        ):
            raise ValueError(
                "reserved_output_tokens must be smaller "
                "than max_context_tokens"
            )

        self.limits = ExecutionLimits(
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
            max_repeated_tool_calls=max_repeated_tool_calls,
            timeout_seconds=timeout_seconds,
            per_tool_limits=dict(
                per_tool_limits or {}
            ),
            max_parallel_tool_calls=max_parallel_tool_calls,
        )

        self.router = router
        self.inference = inference
        self.tools = tools
        self.planner = planner

        # ---------------------------------------------------------
        # Optional durable persistence.
        #
        # The runtime depends only on the persistence abstraction.
        # It does not know about PostgreSQL or SQLAlchemy.
        #
        # None keeps existing unit tests and local callers
        # persistence-independent.
        # ---------------------------------------------------------

        self.persistence = persistence

        # Backward compatibility with existing callers/tests.
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

        if max_context_tokens is None:
            self.context_budget: ContextBudget | None = None
        else:
            self.context_budget = ContextBudget(
                max_context_tokens=max_context_tokens,
                reserved_output_tokens=reserved_output_tokens,
            )

        # ---------------------------------------------------------
        # Human approval.
        # ---------------------------------------------------------

        self.approval_policy = approval_policy

        self.approval_manager = (
            approval_manager
            if approval_manager is not None
            else ApprovalManager()
        )

        # ---------------------------------------------------------
        # Runtime execution registries.
        #
        # _executions:
        #     Retains the runtime record for executions known to
        #     this process.
        #
        # _active_executions:
        #     Contains only executions currently running.
        #
        # Keeping these concepts separate is important:
        #
        #     execution exists
        #             !=
        #     execution is active
        # ---------------------------------------------------------

        self._executions: dict[
            str,
            _ExecutionRecord,
        ] = {}

        self._active_executions: dict[
            str,
            _ExecutionRecord,
        ] = {}

    async def _create_persistent_execution(
        self,
        execution: Execution,
    ) -> None:
        if self.persistence is None:
            return

        await self.persistence.create_execution(execution)

    async def _persist_execution(
        self,
        execution: Execution,
    ) -> None:
        if self.persistence is None:
            return

        await self.persistence.update_execution(execution)

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

        run() is the synchronous execution API from the caller's
        perspective: it does not return until execution reaches a
        terminal state.
        """

        (
            execution,
            context,
            context_manager,
            cancellation,
            _record,
            resolved_session_id,
            resolved_task,
        ) = self._create_execution(
            intent=intent,
            session_id=session_id,
            task=task,
            metadata=metadata,
        )

        return await self._run_execution(
            execution=execution,
            context=context,
            context_manager=context_manager,
            cancellation=cancellation,
            intent=intent,
            session_id=resolved_session_id,
            task=resolved_task,
            required_capabilities=required_capabilities,
        )

    def _create_execution(
        self,
        *,
        intent: str,
        session_id: str | None,
        task: str | None,
        metadata: dict[str, Any] | None,
    ) -> tuple[
        Execution,
        ExecutionContext,
        ContextManager,
        CancellationToken,
        _ExecutionRecord,
        str,
        str,
    ]:
        """
        Create and register all runtime-owned state for one execution.

        This method is shared by both run() and submit() so that
        synchronous and asynchronous execution have identical
        execution state.

        The execution is registered before any background task is
        scheduled or any event is emitted.
        """

        execution = Execution()

        context = ExecutionContext(
            execution=execution,
            metadata=dict(metadata or {}),
        )

        context_manager = ContextManager(
            context,
            budget=self.context_budget,
        )

        resolved_session_id = (
            session_id or str(execution.id)
        )

        resolved_task = (
            task if task is not None else intent
        )

        context.metadata["session_id"] = (
            resolved_session_id
        )

        context.metadata["task"] = resolved_task

        cancellation = CancellationToken()
        event_stream = EventStream()

        execution_id = str(execution.id)

        record = _ExecutionRecord(
            execution=execution,
            token=cancellation,
            event_stream=event_stream,
        )

        # Register before the execution becomes runnable.
        self._executions[
            execution_id
        ] = record

        self._active_executions[
            execution_id
        ] = record

        return (
            execution,
            context,
            context_manager,
            cancellation,
            record,
            resolved_session_id,
            resolved_task,
        )

    async def _run_execution(
        self,
        *,
        execution: Execution,
        context: ExecutionContext,
        context_manager: ContextManager,
        cancellation: CancellationToken,
        intent: str,
        session_id: str,
        task: str,
        required_capabilities: list[str] | None,
    ) -> AgentResponse:
        """
        Execute the common runtime lifecycle.

        Both run() and submit() eventually enter this method.

        This is the single source of truth for:

        - execution start
        - cancellation handling
        - execution state transitions
        - agent execution
        - terminal result creation
        - terminal event emission
        - stream cleanup
        - active-registry cleanup
        - result retention
        """

        execution_id = str(execution.id)

        record = self._executions.get(
            execution_id
        )

        if record is None:
            raise RuntimeError(
                "Execution record is missing from runtime registry"
            )

        await self._create_persistent_execution(
            execution,
        )

        await self._publish_event(
            execution_id=execution_id,
            event_type=AgentEventType.EXECUTION_STARTED,
            data={
                "session_id": session_id,
            },
        )

        current_task = asyncio.current_task()

        if current_task is not None:
            record.task = current_task

        try:
            cancellation.raise_if_cancelled()

            execution.transition_to(
                ExecutionState.PLANNING
            )

            await self._persist_execution(
                execution,
            )

            output = await self._execute(
                execution=execution,
                context=context,
                context_manager=context_manager,
                intent=intent,
                session_id=session_id,
                task=task,
                required_capabilities=required_capabilities,
                cancellation=cancellation,
            )

            cancellation.raise_if_cancelled()

            execution.transition_to(
                ExecutionState.COMPLETED
            )

            await self._persist_execution(
                execution,
            )

            result = ExecutionResult.from_execution(
                execution,
                output=output,
            )

            record.result = result

            await self._publish_event(
                execution_id=execution_id,
                event_type=AgentEventType.EXECUTION_COMPLETED,
                data={
                    "status": "success",
                    "steps": len(execution.steps),
                },
            )

            return self._to_agent_response(
                result=result,
                execution=execution,
                context=context,
            )

        except ExecutionCancelled as exc:
            context.add_error(str(exc))

            if execution.state not in {
                ExecutionState.COMPLETED,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
            }:
                execution.transition_to(
                    ExecutionState.CANCELLED
                )
                await self._persist_execution(
                    execution,
                )

            await self._publish_event(
                execution_id=execution_id,
                event_type=AgentEventType.EXECUTION_CANCELLED,
                data={
                    "reason": "execution_cancelled",
                },
            )

            logger.info(
                "Agent execution cancelled",
                extra={
                    "execution_id": execution_id,
                    "error_type": type(exc).__name__,
                },
            )

            result = ExecutionResult.from_execution(
                execution,
                output=None,
            )

            record.result = result

            return self._to_agent_response(
                result=result,
                execution=execution,
                context=context,
            )

        except asyncio.CancelledError as exc:
            cancellation.cancel()

            error = "Agent execution was cancelled"

            context.add_error(error)

            if execution.state not in {
                ExecutionState.COMPLETED,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
            }:
                execution.transition_to(
                    ExecutionState.CANCELLED
                )

            await self._publish_event(
                execution_id=execution_id,
                event_type=AgentEventType.EXECUTION_CANCELLED,
                data={
                    "reason": "task_cancelled",
                },
            )

            logger.info(
                "Agent execution task cancelled",
                extra={
                    "execution_id": execution_id,
                    "error_type": type(exc).__name__,
                },
            )

            result = ExecutionResult.from_execution(
                execution,
                output=None,
            )

            record.result = result

            return self._to_agent_response(
                result=result,
                execution=execution,
                context=context,
            )

        except Exception as exc:
            if execution.state not in {
                ExecutionState.COMPLETED,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
            }:
                execution.mark_failed(
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

                await self._persist_execution(
                    execution,
                )

            context.add_error(str(exc))

            await self._publish_event(
                execution_id=execution_id,
                event_type=AgentEventType.EXECUTION_FAILED,
                data={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )

            logger.exception(
                "Agent execution failed",
                extra={
                    "execution_id": execution_id,
                    "error_type": type(exc).__name__,
                },
            )

            record.result = ExecutionResult.from_execution(
                execution,
                output=None,
            )

            raise

        finally:
            # -----------------------------------------------------
            # Close the event stream before removing the execution
            # from the active registry.
            #
            # Order:
            #
            #     terminal event
            #          ↓
            #     stream close
            #          ↓
            #     active registry removal
            #
            # The completed record remains in _executions.
            # -----------------------------------------------------

            current_record = self._executions.get(
                execution_id
            )

            if current_record is not None:
                stream = current_record.event_stream

                if stream is not None:
                    await stream.close()

                current_record.event_stream = None
                current_record.task = None

            self._active_executions.pop(
                execution_id,
                None,
            )

    async def _publish_event(
        self,
        *,
        execution_id: str,
        event_type: AgentEventType,
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Publish an execution event without allowing streaming failures
        to affect the agent execution itself.
        """

        active = self._active_executions.get(
            execution_id
        )

        if (
            active is None
            or active.event_stream is None
        ):
            return

        try:
            await active.event_stream.publish(
                AgentEvent(
                    type=event_type.value,
                    execution_id=execution_id,
                    data=data or {},
                )
            )

        except RuntimeError:
            logger.debug(
                "Event stream unavailable for execution %s",
                execution_id,
            )

    def get_event_stream(
        self,
        execution_id: str,
    ) -> EventStream | None:
        """
        Return the event stream for an active execution.

        Completed executions remain in _executions for result/status
        inspection, but their event stream is no longer available.
        """

        active = self._active_executions.get(
            str(execution_id)
        )

        if active is None:
            return None

        stream = active.event_stream

        if stream is None or stream.closed:
            return None

        return stream

    async def submit(
        self,
        task: str,
        *,
        session_id: str | None = None,
        required_capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionSubmission:
        """
        Submit an agent execution for background processing.

        Unlike run(), this method returns immediately after the
        execution has been created, registered, and scheduled.

        The actual execution lifecycle is identical to run().
        """

        (
            execution,
            context,
            context_manager,
            cancellation,
            record,
            resolved_session_id,
            resolved_task,
        ) = self._create_execution(
            intent=task,
            session_id=session_id,
            task=task,
            metadata=metadata,
        )

        # NOTE: the public execution_id returned here is the raw
        # UUID, matching ExecutionResult.execution_id (also a UUID)
        # so that `result.execution_id == submission.execution_id`
        # holds for callers. Internally, _executions /
        # _active_executions are keyed by str(execution.id); the
        # lookup methods (is_active, get_result, cancel,
        # get_event_stream) normalize incoming ids via str(...) so
        # they accept either a UUID or a string here.
        execution_id = execution.id

        task_handle = asyncio.create_task(
            self._run_submitted(
                execution=execution,
                context=context,
                context_manager=context_manager,
                cancellation=cancellation,
                intent=task,
                session_id=resolved_session_id,
                task=task,
                required_capabilities=required_capabilities,
            )
        )

        record.task = task_handle

        return ExecutionSubmission(
            execution_id=execution_id,
            status="submitted",
        )

    async def _run_submitted(
        self,
        *,
        execution: Execution,
        context: ExecutionContext,
        context_manager: ContextManager,
        cancellation: CancellationToken,
        intent: str,
        session_id: str,
        task: str,
        required_capabilities: list[str] | None,
    ) -> None:
        """
        Run one submitted execution in the background.

        _run_execution() owns execution correctness and records failures.

        Because this coroutine is detached from the submit() caller,
        normal execution failures are swallowed here after they have
        already been persisted into the in-memory execution record.

        This prevents "Task exception was never retrieved" warnings.
        """

        try:
            await self._run_execution(
                execution=execution,
                context=context,
                context_manager=context_manager,
                cancellation=cancellation,
                intent=intent,
                session_id=session_id,
                task=task,
                required_capabilities=required_capabilities,
            )

        except asyncio.CancelledError:
            # _run_execution() normally converts cancellation into
            # a terminal execution result. This is a final guard
            # for cancellation occurring outside that lifecycle.
            return

        except Exception:
            # _run_execution() has already:
            #
            #     - marked execution failed
            #     - created ExecutionResult
            #     - emitted EXECUTION_FAILED
            #     - retained the result
            #
            # Therefore the detached task must not re-raise.
            return

    async def stream(
        self,
        task: str,
        *,
        session_id: str | None = None,
        required_capabilities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventStream:
        """
        Start an agent execution and return its live event stream.

        Unlike submit(), this method returns the EventStream itself so
        callers can immediately consume execution events.

        The execution is registered before the background task starts,
        preventing a race where a fast execution could finish before
        the caller obtains its event stream.
        """

        (
            execution,
            context,
            context_manager,
            cancellation,
            record,
            resolved_session_id,
            resolved_task,
        ) = self._create_execution(
            intent=task,
            session_id=session_id,
            task=task,
            metadata=metadata,
        )

        event_stream = record.event_stream

        if event_stream is None:
            raise RuntimeError(
                "Execution event stream was not created"
            )

        task_handle = asyncio.create_task(
            self._run_submitted(
                execution=execution,
                context=context,
                context_manager=context_manager,
                cancellation=cancellation,
                intent=task,
                session_id=resolved_session_id,
                task=resolved_task,
                required_capabilities=required_capabilities,
            )
        )

        record.task = task_handle

        return event_stream

    def get_result(
        self,
        execution_id: str,
    ) -> ExecutionResult | None:
        """
        Return the terminal result for a known execution.

        Returns None when:

        - the execution does not exist, or
        - the execution is still running.
        """

        record = self._executions.get(
            str(execution_id)
        )

        if record is None:
            return None

        return record.result

    async def cancel(
        self,
        execution_id: str,
    ) -> bool:
        """
        Request cancellation of an active execution.

        Cancellation is intentionally idempotent.

        A completed/failed/cancelled execution is not considered
        active and therefore cannot be cancelled again.
        """

        active_execution = (
            self._active_executions.get(
                str(execution_id)
            )
        )

        if active_execution is None:
            return False

        active_execution.token.cancel()

        task = active_execution.task

        if task is not None and not task.done():
            task.cancel()

        logger.info(
            "Agent execution cancellation requested",
            extra={
                "execution_id": str(execution_id),
            },
        )

        return True

    def is_active(
        self,
        execution_id: str,
    ) -> bool:
        """
        Return whether an execution is currently active.
        """

        return str(execution_id) in self._active_executions

    def _check_cancellation(
        self,
        cancellation: CancellationToken,
    ) -> None:
        """
        Check the cooperative cancellation signal.
        """

        cancellation.raise_if_cancelled()

    def _remaining_timeout(
        self,
        started_at: float,
    ) -> float:
        """
        Return the remaining execution-wide timeout.
        """

        remaining = self.limits.remaining_timeout(
            started_at
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
        context_manager: ContextManager,
        intent: str,
        session_id: str,
        task: str,
        required_capabilities: list[str] | None,
        cancellation: CancellationToken,
    ) -> str:
        """
        Execute the agent reasoning loop.

        ExecutionContext remains the source of execution state.

        ContextManager is the source of all LLM-facing messages.
        """

        execution_started_at = time.monotonic()

        execution_id = str(execution.id)

        repeated_tool_calls: dict[
            tuple[str, str],
            int,
        ] = {}

        tool_call_counts: dict[
            str,
            int,
        ] = {}

        # =========================================================
        # PLAN
        # =========================================================

        self._check_cancellation(cancellation)

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

        context_manager.add_system_message(
            SYSTEM_PROMPT
        )

        context_manager.add_user_message(
            intent
        )

        context.current_plan = task

        plan_step.output = {
            "task": task,
            "session_id": session_id,
        }

        plan_step.mark_completed()

        self._check_cancellation(cancellation)

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

        self._check_cancellation(cancellation)

        self.limits.validate_timeout(
            execution_started_at
        )

        try:
            remaining_timeout = (
                self._remaining_timeout(
                    execution_started_at
                )
            )

            routing_messages = (
                context_manager.get_messages_for_inference()
            )

            route = await asyncio.wait_for(
                self.router.route(
                    session_id=session_id,
                    task=task,
                    messages=routing_messages,
                    required_capabilities=(
                        required_capabilities
                    ),
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

        except asyncio.CancelledError as exc:
            cancellation.cancel()

            raise ExecutionCancelled(
                "Agent execution was cancelled during routing"
            ) from exc

        self._check_cancellation(cancellation)

        self.limits.validate_timeout(
            execution_started_at
        )

        selected_model = route.model

        context.metadata["model"] = selected_model
        context.metadata["provider"] = route.provider

        logger.info(
            "Agent request routed",
            extra={
                "execution_id": execution_id,
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
            self._check_cancellation(cancellation)

            context.current_step = step_number

            self.limits.validate_step(
                step_number
            )

            self.limits.validate_timeout(
                execution_started_at
            )

            if execution.state is not ExecutionState.INFERENCE:
                execution.transition_to(
                    ExecutionState.INFERENCE
                )

            # -----------------------------------------------------
            # BUILD BOUNDED INFERENCE CONTEXT
            # -----------------------------------------------------

            inference_messages = (
                context_manager.get_messages_for_inference()
            )

            # -----------------------------------------------------
            # INFERENCE
            # -----------------------------------------------------

            inference_step = self._start_step(
                execution=execution,
                step_type=StepType.INFERENCE,
                input={
                    "model": selected_model,
                    "messages": list(
                        inference_messages
                    ),
                    "tools": tool_definitions,
                    "step": step_number,
                    "context_tokens": (
                        context_manager.token_count(
                            inference_messages
                        )
                    ),
                    "remaining_input_tokens": (
                        context_manager.remaining_input_tokens(
                            inference_messages
                        )
                    ),
                },
            )

            try:
                remaining_timeout = (
                    self._remaining_timeout(
                        execution_started_at
                    )
                )

                deadline = (
                    time.monotonic()
                    + remaining_timeout
                )

                await self._publish_event(
                    execution_id=execution_id,
                    event_type=AgentEventType.INFERENCE_STARTED,
                    data={
                        "step": step_number,
                        "model": selected_model,
                    },
                )

                inference_response = (
                    await asyncio.wait_for(
                        self.inference.complete(
                            model=selected_model,
                            messages=inference_messages,
                            tools=tool_definitions,
                            deadline=deadline,
                        ),
                        timeout=remaining_timeout,
                    )
                )

                self._check_cancellation(
                    cancellation
                )

                inference_step.output = (
                    inference_response
                )

                inference_step.mark_completed()

                await self._publish_event(
                    execution_id=execution_id,
                    event_type=AgentEventType.INFERENCE_COMPLETED,
                    data={
                        "step": step_number,
                        "model": selected_model,
                    },
                )

            except asyncio.TimeoutError as exc:
                error = (
                    "Agent inference exceeded execution "
                    "timeout: "
                    f"{self.limits.timeout_seconds} seconds"
                )

                inference_step.mark_failed(
                    error=error
                )

                raise ExecutionLimitExceeded(
                    error
                ) from exc

            except asyncio.CancelledError as exc:
                cancellation.cancel()

                error = (
                    "Agent execution was cancelled "
                    "during inference"
                )

                inference_step.mark_failed(
                    error=error
                )

                raise ExecutionCancelled(
                    error
                ) from exc

            except Exception as exc:
                inference_step.mark_failed(
                    error=str(exc)
                )
                raise

            # -----------------------------------------------------
            # PLANNER
            # -----------------------------------------------------

            self.limits.validate_timeout(
                execution_started_at
            )

            self._check_cancellation(
                cancellation
            )

            decision = self.planner.plan(
                response=inference_response,
                context=context,
            )

            self._check_cancellation(
                cancellation
            )

            normalized_tool_calls = (
                decision.normalized_tool_calls()
            )

            logger.debug(
                "Agent planner decision",
                extra={
                    "execution_id": execution_id,
                    "step": step_number,
                    "decision_type": str(
                        decision.type
                    ),
                    "tool_call_count": len(
                        normalized_tool_calls
                    ),
                },
            )

            # =====================================================
            # FINAL
            # =====================================================

            if decision.is_final:
                self._check_cancellation(
                    cancellation
                )

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
                self._check_cancellation(
                    cancellation
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

                raise RuntimeError(error)

            # =====================================================
            # TOOL CALL
            # =====================================================

            if decision.is_tool_call:
                self._check_cancellation(
                    cancellation
                )

                await self._execute_tool_calls(
                    execution=execution,
                    context=context,
                    context_manager=context_manager,
                    inference_response=inference_response,
                    decision=decision,
                    execution_started_at=(
                        execution_started_at
                    ),
                    repeated_tool_calls=(
                        repeated_tool_calls
                    ),
                    tool_call_counts=(
                        tool_call_counts
                    ),
                    cancellation=cancellation,
                )

                self._check_cancellation(
                    cancellation
                )

                continue

            # =====================================================
            # UNKNOWN DECISION
            # =====================================================

            raise AgentProtocolError(
                "Unsupported agent decision type: "
                f"{decision.type}"
            )

        raise AgentMaxStepsError(
            "Agent exceeded maximum steps: "
            f"{self.max_steps}"
        )

    async def _execute_tool_calls(
        self,
        *,
        execution: Execution,
        context: ExecutionContext,
        context_manager: ContextManager,
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
        cancellation: CancellationToken,
    ) -> None:
        """
        Execute one or more tool calls from a single model decision.

        The complete batch is admitted before any tool starts.

        Human approval is evaluated after budget admission but before
        any tool execution.

        Approved calls may execute concurrently.

        Results are applied to shared ExecutionContext sequentially
        in original model order.
        """

        tool_calls = decision.normalized_tool_calls()

        if not tool_calls:
            raise AgentProtocolError(
                "Tool decision contains no tool calls"
            )

        self._check_cancellation(
            cancellation
        )

        admissions: list[
            tuple[
                ToolCall,
                tuple[str, str],
            ]
        ] = []

        projected_global_calls = (
            context.tool_call_count
        )

        projected_tool_counts = dict(
            tool_call_counts
        )

        projected_repeated_calls = dict(
            repeated_tool_calls
        )

        for tool_call in tool_calls:
            self._check_cancellation(
                cancellation
            )

            tool_name = tool_call.name
            arguments = dict(
                tool_call.arguments
            )
            call_id = tool_call.call_id

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

            self.limits.validate_tool_call(
                projected_global_calls
            )

            current_tool_count = (
                projected_tool_counts.get(
                    tool_name,
                    0,
                )
            )

            self.limits.validate_per_tool_call(
                tool_name,
                current_tool_count,
            )

            tool_call_key = (
                tool_name,
                json.dumps(
                    arguments,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )

            repeated_count = (
                projected_repeated_calls.get(
                    tool_call_key,
                    0,
                )
            )

            self.limits.validate_repeated_tool_call(
                repeated_count
            )

            self.limits.validate_timeout(
                execution_started_at
            )

            projected_global_calls += 1

            projected_tool_counts[
                tool_name
            ] = current_tool_count + 1

            projected_repeated_calls[
                tool_call_key
            ] = repeated_count + 1

            admissions.append(
                (
                    ToolCall(
                        name=tool_name,
                        arguments=arguments,
                        call_id=call_id,
                    ),
                    tool_call_key,
                )
            )

        for tool_call, tool_call_key in admissions:
            tool_name = tool_call.name

            repeated_tool_calls[
                tool_call_key
            ] = (
                repeated_tool_calls.get(
                    tool_call_key,
                    0,
                )
                + 1
            )

            tool_call_counts[
                tool_name
            ] = (
                tool_call_counts.get(
                    tool_name,
                    0,
                )
                + 1
            )

        assistant_message = (
            self._extract_assistant_message(
                inference_response
            )
        )

        context_manager.add_assistant_message(
            assistant_message
        )

        for tool_call, _ in admissions:
            self._check_cancellation(
                cancellation
            )

            step = self._start_step(
                execution=execution,
                step_type=StepType.TOOL_CALL,
                input={
                    "call_id": tool_call.call_id,
                    "tool_name": tool_call.name,
                    "arguments": dict(
                        tool_call.arguments
                    ),
                },
            )

            step.output = {
                "call_id": tool_call.call_id,
                "tool_name": tool_call.name,
            }

            step.mark_completed()

        await self._handle_required_approvals(
            execution=execution,
            context=context,
            admissions=admissions,
            execution_started_at=execution_started_at,
            cancellation=cancellation,
        )

        self._check_cancellation(
            cancellation
        )

        execution.transition_to(
            ExecutionState.TOOL_EXECUTION
        )

        semaphore = asyncio.Semaphore(
            self.limits.max_parallel_tool_calls
        )

        async def execute_one(
            tool_call: ToolCall,
        ) -> _ToolExecutionResult:
            async with semaphore:
                self._check_cancellation(
                    cancellation
                )

                output = await self._execute_single_tool(
                    execution=execution,
                    tool_call=tool_call,
                    execution_started_at=(
                        execution_started_at
                    ),
                    cancellation=cancellation,
                )

                return _ToolExecutionResult(
                    tool_call=tool_call,
                    output=output,
                )

        tasks = [
            asyncio.create_task(
                execute_one(tool_call)
            )
            for tool_call, _ in admissions
        ]

        try:
            remaining_timeout = (
                self._remaining_timeout(
                    execution_started_at
                )
            )

            results = await asyncio.wait_for(
                asyncio.gather(
                    *tasks,
                    return_exceptions=True,
                ),
                timeout=remaining_timeout,
            )

        except asyncio.TimeoutError as exc:
            for task in tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            raise ExecutionLimitExceeded(
                "Agent parallel tool execution exceeded "
                "execution timeout: "
                f"{self.limits.timeout_seconds} seconds"
            ) from exc

        except asyncio.CancelledError as exc:
            cancellation.cancel()

            for task in tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            raise ExecutionCancelled(
                "Agent execution was cancelled during "
                "parallel tool execution"
            ) from exc

        if len(results) != len(admissions):
            raise RuntimeError(
                "Parallel tool execution returned an "
                "unexpected number of results"
            )

        ordered_results: list[
            _ToolExecutionResult | BaseException
        ] = []

        first_failure: BaseException | None = None

        for index, result in enumerate(results):
            expected_call = admissions[index][0]

            if isinstance(
                result,
                _ToolExecutionResult,
            ):
                if (
                    result.tool_call.call_id
                    != expected_call.call_id
                ):
                    raise RuntimeError(
                        "Parallel tool execution returned "
                        "results in an unexpected order"
                    )

                ordered_results.append(
                    result
                )

                continue

            if isinstance(
                result,
                BaseException,
            ):
                if first_failure is None:
                    first_failure = result

                ordered_results.append(
                    result
                )

                continue

            raise RuntimeError(
                "Parallel tool execution returned "
                "an invalid result"
            )

        execution.transition_to(
            ExecutionState.OBSERVING
        )

        for result in ordered_results:
            self._check_cancellation(
                cancellation
            )

            if not isinstance(
                result,
                _ToolExecutionResult,
            ):
                continue

            await self._record_tool_result(
                execution=execution,
                context=context,
                context_manager=context_manager,
                tool_call=result.tool_call,
                output=result.output,
                cancellation=cancellation,
            )

        if first_failure is not None:
            if isinstance(
                first_failure,
                ExecutionCancelled,
            ):
                raise first_failure

            if isinstance(
                first_failure,
                ExecutionLimitExceeded,
            ):
                raise first_failure

            if isinstance(
                first_failure,
                asyncio.CancelledError,
            ):
                cancellation.cancel()

                raise ExecutionCancelled(
                    "Agent execution was cancelled during "
                    "parallel tool execution"
                ) from first_failure

            raise first_failure

    async def _handle_required_approvals(
        self,
        *,
        execution: Execution,
        context: ExecutionContext,
        admissions: list[
            tuple[
                ToolCall,
                tuple[str, str],
            ]
        ],
        execution_started_at: float,
        cancellation: CancellationToken,
    ) -> None:
        """
        Determine whether any admitted tool calls require approval.
        """

        if self.approval_policy is None:
            return

        required: list[
            tuple[
                ToolCall,
                str,
            ]
        ] = []

        execution_id = str(
            execution.id
        )

        for tool_call, _ in admissions:
            self._check_cancellation(
                cancellation
            )

            self.limits.validate_timeout(
                execution_started_at
            )

            requires_approval = (
                await self.approval_policy.requires_approval(
                    tool_name=tool_call.name,
                    arguments=dict(
                        tool_call.arguments
                    ),
                    context=context,
                )
            )

            if not requires_approval:
                continue

            approval_id = (
                f"{execution_id}:"
                f"{tool_call.call_id}"
            )

            required.append(
                (
                    tool_call,
                    approval_id,
                )
            )

        if not required:
            return

        for tool_call, approval_id in required:
            self._check_cancellation(
                cancellation
            )

            await self.approval_manager.create_request(
                approval_id=approval_id,
                execution_id=execution_id,
                call_id=tool_call.call_id,
                tool_name=tool_call.name,
                arguments=dict(
                    tool_call.arguments
                ),
            )

            logger.info(
                "Human approval required",
                extra={
                    "execution_id": execution_id,
                    "approval_id": approval_id,
                    "call_id": tool_call.call_id,
                    "tool_name": tool_call.name,
                },
            )

        execution.transition_to(
            ExecutionState.WAITING_APPROVAL
        )

        async def wait_for_approval(
            approval_id: str,
        ) -> None:
            while True:
                self._check_cancellation(
                    cancellation
                )

                self.limits.validate_timeout(
                    execution_started_at
                )

                remaining_timeout = (
                    self._remaining_timeout(
                        execution_started_at
                    )
                )

                try:
                    request = await asyncio.wait_for(
                        self.approval_manager.wait_for_resolution(
                            approval_id
                        ),
                        timeout=remaining_timeout,
                    )

                except asyncio.TimeoutError as exc:
                    raise ExecutionLimitExceeded(
                        "Agent execution exceeded timeout "
                        "while waiting for human approval: "
                        f"{self.limits.timeout_seconds} seconds"
                    ) from exc

                except asyncio.CancelledError as exc:
                    cancellation.cancel()

                    raise ExecutionCancelled(
                        "Agent execution was cancelled while "
                        "waiting for human approval"
                    ) from exc

                if request.status is ApprovalStatus.APPROVED:
                    logger.info(
                        "Human approval granted",
                        extra={
                            "execution_id": execution_id,
                            "approval_id": approval_id,
                            "call_id": request.call_id,
                            "tool_name": request.tool_name,
                        },
                    )

                    return

                if request.status is ApprovalStatus.REJECTED:
                    raise ToolExecutionError(
                        "Human approval rejected for tool "
                        f"'{request.tool_name}' "
                        f"(call_id={request.call_id})"
                    )

                await asyncio.sleep(0)

        try:
            await asyncio.gather(
                *[
                    wait_for_approval(
                        approval_id
                    )
                    for _, approval_id in required
                ]
            )

        except (
            ApprovalNotFoundError,
            ApprovalAlreadyResolvedError,
        ):
            raise

        self._check_cancellation(
            cancellation
        )

        self.limits.validate_timeout(
            execution_started_at
        )

        logger.info(
            "All required human approvals granted",
            extra={
                "execution_id": execution_id,
                "approval_count": len(required),
            },
        )

    async def _execute_single_tool(
        self,
        *,
        execution: Execution,
        tool_call: ToolCall,
        execution_started_at: float,
        cancellation: CancellationToken,
    ) -> Any:
        """
        Execute one already-admitted and approved tool.
        """

        execution_id = str(
            execution.id
        )

        self._check_cancellation(
            cancellation
        )

        remaining_timeout = (
            self._remaining_timeout(
                execution_started_at
            )
        )

        await self._publish_event(
            execution_id=execution_id,
            event_type=AgentEventType.TOOL_CALL_STARTED,
            data={
                "call_id": tool_call.call_id,
                "tool_name": tool_call.name,
            },
        )

        try:
            tool_result = await asyncio.wait_for(
                self.tool_executor.execute(
                    name=tool_call.name,
                    arguments=dict(
                        tool_call.arguments
                    ),
                    context=None,
                ),
                timeout=remaining_timeout,
            )

        except asyncio.TimeoutError as exc:
            await self._publish_event(
                execution_id=execution_id,
                event_type=AgentEventType.TOOL_CALL_COMPLETED,
                data={
                    "call_id": tool_call.call_id,
                    "tool_name": tool_call.name,
                    "success": False,
                },
            )

            raise ExecutionLimitExceeded(
                "Agent tool execution exceeded "
                "execution timeout: "
                f"{self.limits.timeout_seconds} seconds"
            ) from exc

        except asyncio.CancelledError:
            raise

        except Exception:
            await self._publish_event(
                execution_id=execution_id,
                event_type=AgentEventType.TOOL_CALL_COMPLETED,
                data={
                    "call_id": tool_call.call_id,
                    "tool_name": tool_call.name,
                    "success": False,
                },
            )

            raise

        self._check_cancellation(
            cancellation
        )

        self.limits.validate_timeout(
            execution_started_at
        )

        if tool_result.failed:
            error = (
                tool_result.error
                or (
                    "Tool execution failed: "
                    f"{tool_call.name}"
                )
            )

            error_type = (
                tool_result.metadata.get(
                    "error_type"
                )
            )

            await self._publish_event(
                execution_id=execution_id,
                event_type=AgentEventType.TOOL_CALL_COMPLETED,
                data={
                    "call_id": tool_call.call_id,
                    "tool_name": tool_call.name,
                    "success": False,
                },
            )

            if error_type == "unknown_tool":
                raise AgentProtocolError(
                    "Unknown tool requested by model: "
                    f"{tool_call.name}"
                )

            raise ToolExecutionError(error)

        await self._publish_event(
            execution_id=execution_id,
            event_type=AgentEventType.TOOL_CALL_COMPLETED,
            data={
                "call_id": tool_call.call_id,
                "tool_name": tool_call.name,
                "success": True,
            },
        )

        return tool_result.output

    async def _record_tool_result(
        self,
        *,
        execution: Execution,
        context: ExecutionContext,
        context_manager: ContextManager,
        tool_call: ToolCall,
        output: Any,
        cancellation: CancellationToken,
    ) -> None:
        """
        Apply one completed tool result to execution state.
        """

        self._check_cancellation(
            cancellation
        )

        call_id = tool_call.call_id
        tool_name = tool_call.name
        arguments = dict(
            tool_call.arguments
        )

        if not call_id:
            raise AgentProtocolError(
                "Tool call is missing call_id"
            )

        result_step = self._start_step(
            execution=execution,
            step_type=StepType.TOOL_RESULT,
            input={
                "call_id": call_id,
                "tool_name": tool_name,
                "arguments": arguments,
            },
        )

        result_step.output = output
        result_step.mark_completed()

        context_manager.add_tool_call(
            {
                "id": call_id,
                "name": tool_name,
                "arguments": arguments,
                "result": output,
            }
        )

        observation = self._normalize_tool_output(
            output
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

        context_manager.add_observation(
            observation
        )

        context_manager.add_tool_message(
            call_id=call_id,
            name=tool_name,
            content=observation,
        )

        self._check_cancellation(
            cancellation
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

        execution.add_step(step)

        return step

    @staticmethod
    def _extract_assistant_message(
        inference_response: Any,
    ) -> dict[str, Any]:
        """
        Extract the assistant message from an inference response.
        """

        if isinstance(
            inference_response,
            dict,
        ):
            direct_message = (
                inference_response.get(
                    "message"
                )
            )

            if isinstance(
                direct_message,
                dict,
            ):
                return direct_message

            choices = (
                inference_response.get(
                    "choices"
                )
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
            return dict(message)

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
        execution: Execution,
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

            call_id = tool_call.get("id")
            name = tool_call.get("name")
            arguments = tool_call.get("arguments")
            output = tool_call.get("result")

            if not isinstance(
                call_id,
                str,
            ):
                continue

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
                    call_id=call_id,
                    name=name,
                    arguments=arguments,
                    result=AgentRuntime._normalize_tool_output(
                        output
                    ),
                )
            )

        status = result.status.value

        # Internal ExecutionStatus uses "completed",
        # while the public AgentResponse contract uses "success".
        if status == "completed":
            status = "success"

        return AgentResponse(
            execution_id=str(result.execution_id),
            status=status,
            answer=AgentRuntime._normalize_tool_output(
                result.output
            ),
            steps=context.current_step,
            tool_calls=tool_calls,
        )
