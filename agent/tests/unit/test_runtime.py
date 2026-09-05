from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.agent_runtime.domain import (
    AgentDecision,
    DecisionType,
)
from app.agent_runtime.execution_limits import ExecutionLimits
from app.agent_runtime.planner import Planner
from app.agent_runtime.runtime import AgentRuntime
from app.core.errors import (
    AgentMaxStepsError,
    AgentProtocolError,
    ExecutionLimitExceeded,
    ToolExecutionError,
)
from app.tools.builtin import create_tool_registry
from app.tools.executor import ToolExecutor

class FakeInference:
    """In-memory fake for the InferenceClient boundary."""

    def __init__(
        self,
        responses: list[dict[str, Any]],
    ) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "tools": tools,
            }
        )

        if not self.responses:
            raise AssertionError(
                "FakeInference has no responses left"
            )

        return self.responses.pop(0)

class HangingInference:
    """
    Inference fake that never completes unless Runtime
    cancels the coroutine because the execution timeout expires.
    """

    def __init__(self) -> None:
        self.started = False
        self.cancelled = False

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.started = True

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise

class FakeRouter:
    """In-memory fake for semantic model routing."""

    class Decision:
        model = "test-model"
        provider = "test-provider"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def route(
        self,
        *,
        session_id: str,
        task: str,
        messages: list[dict[str, Any]],
        required_capabilities: list[str] | None = None,
    ) -> Decision:
        self.calls.append(
            {
                "session_id": session_id,
                "task": task,
                "messages": messages,
                "required_capabilities": required_capabilities,
            }
        )

        return self.Decision()


class FakeToolSandbox:
    """
    In-memory fake for the ToolSandboxClient boundary.

    The fake simulates the sandbox while keeping runtime tests
    independent from HTTP and the real sandbox service.
    """

    def __init__(
        self,
        *,
        tools: Any,
    ) -> None:
        self.tools = tools
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        self.calls.append(
            (
                name,
                arguments,
            )
        )

        return self.tools.execute(
            name,
            arguments,
        )


class FakePlanner:
    """
    In-memory Planner used to test Runtime decision handling.

    The real Planner is responsible for interpreting inference
    responses. These tests focus specifically on whether Runtime
    correctly handles each AgentDecision.
    """

    def __init__(
        self,
        decisions: list[AgentDecision],
    ) -> None:
        self.decisions = decisions
        self.calls: list[dict[str, Any]] = []

    def plan(
        self,
        *,
        response: dict[str, Any],
        context: Any,
    ) -> AgentDecision:
        self.calls.append(
            {
                "response": response,
                "context": context,
            }
        )

        if not self.decisions:
            raise AssertionError(
                "FakePlanner has no decisions left"
            )

        return self.decisions.pop(0)

class HangingToolExecutor:
    """
    Tool executor fake that never completes unless Runtime
    cancels the coroutine because the execution timeout expires.
    """

    def __init__(self) -> None:
        self.started = False
        self.cancelled = False

    async def execute(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        self.started = True

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise

def create_runtime(
    responses: list[dict[str, Any]],
    *,
    max_steps: int = 8,
) -> tuple[
    AgentRuntime,
    FakeInference,
    FakeRouter,
    FakeToolSandbox,
]:
    """
    Create a fully wired AgentRuntime for unit tests.

    Planner, ToolExecutor, and Runtime intentionally receive
    the same ToolRegistry instance so they operate against the
    same registered tool definitions.

    The Runtime talks only to ToolExecutor. The ToolExecutor
    delegates actual execution to the fake sandbox.
    """

    inference = FakeInference(responses)
    router = FakeRouter()

    tools = create_tool_registry()

    sandbox = FakeToolSandbox(
        tools=tools,
    )

    tool_executor = ToolExecutor(
        registry=tools,
        sandbox=sandbox,
    )

    planner = Planner(
        tools=tools,
    )

    runtime = AgentRuntime(
        router=router,
        inference=inference,
        tools=tools,
        tool_executor=tool_executor,
        max_steps=max_steps,
        planner=planner,
    )

    return (
        runtime,
        inference,
        router,
        sandbox,
    )


def tool_call_response(
    name: str,
    arguments: str,
    call_id: str = "call-1",
) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": arguments,
                            },
                        }
                    ],
                }
            }
        ]
    }


def final_response(
    answer: str,
) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": answer,
                }
            }
        ]
    }


@pytest.mark.asyncio
async def test_agent_returns_final_answer() -> None:
    runtime, inference, router, sandbox = create_runtime(
        [
            final_response("Hello!"),
        ]
    )

    result = await runtime.run(
        "Say hello",
    )

    assert result.status == "success"
    assert result.answer == "Hello!"
    assert result.steps == 1
    assert result.tool_calls == []

    assert sandbox.calls == []

    assert len(router.calls) == 1
    assert router.calls[0]["task"] == "Say hello"

    assert len(inference.calls) == 1
    assert inference.calls[0]["model"] == "test-model"


@pytest.mark.asyncio
async def test_agent_executes_tool_through_tool_executor() -> None:
    runtime, inference, _, sandbox = create_runtime(
        [
            tool_call_response(
                "calculator",
                '{"expression":"25 * 17"}',
            ),
            final_response(
                "The answer is 425.",
            ),
        ]
    )

    result = await runtime.run(
        "What is 25 * 17?",
    )

    assert result.status == "success"
    assert result.answer == "The answer is 425."
    assert result.steps == 2

    assert len(result.tool_calls) == 1

    assert result.tool_calls[0].name == "calculator"

    assert result.tool_calls[0].arguments == {
        "expression": "25 * 17",
    }

    assert result.tool_calls[0].result == "425"

    assert sandbox.calls == [
        (
            "calculator",
            {
                "expression": "25 * 17",
            },
        )
    ]

    assert len(inference.calls) == 2


@pytest.mark.asyncio
async def test_agent_supports_multiple_steps() -> None:
    runtime, _, _, sandbox = create_runtime(
        [
            tool_call_response(
                "calculator",
                '{"expression":"25 * 17"}',
                "call-1",
            ),
            tool_call_response(
                "calculator",
                '{"expression":"425 + 10"}',
                "call-2",
            ),
            final_response(
                "The final result is 435.",
            ),
        ]
    )

    result = await runtime.run(
        "Calculate 25 * 17 and then add 10.",
    )

    assert result.status == "success"
    assert result.steps == 3

    assert len(result.tool_calls) == 2

    assert result.tool_calls[0].name == "calculator"
    assert result.tool_calls[0].arguments == {
        "expression": "25 * 17",
    }
    assert result.tool_calls[0].result == "425"

    assert result.tool_calls[1].name == "calculator"
    assert result.tool_calls[1].arguments == {
        "expression": "425 + 10",
    }
    assert result.tool_calls[1].result == "435"

    assert result.answer == (
        "The final result is 435."
    )

    assert sandbox.calls == [
        (
            "calculator",
            {
                "expression": "25 * 17",
            },
        ),
        (
            "calculator",
            {
                "expression": "425 + 10",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_agent_enforces_max_steps() -> None:
    runtime, inference, _, sandbox = create_runtime(
        [
            tool_call_response(
                "calculator",
                '{"expression":"1 + 1"}',
                f"call-{i}",
            )
            for i in range(8)
        ],
        max_steps=3,
    )

    with pytest.raises(
        AgentMaxStepsError,
        match="maximum steps",
    ):
        await runtime.run(
            "Keep calculating forever",
        )

    assert len(sandbox.calls) == 3
    assert len(inference.calls) == 3


@pytest.mark.asyncio
async def test_agent_rejects_invalid_inference_response() -> None:
    runtime, _, _, sandbox = create_runtime(
        [
            {
                "invalid": "response",
            }
        ]
    )

    with pytest.raises(
        AgentProtocolError,
    ):
        await runtime.run(
            "Do something",
        )

    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_agent_rejects_unknown_tool() -> None:
    runtime, _, _, sandbox = create_runtime(
        [
            tool_call_response(
                "unknown_tool",
                "{}",
            ),
        ]
    )

    with pytest.raises(
        AgentProtocolError,
        match="Unknown tool requested by model",
    ):
        await runtime.run(
            "Use an unknown tool",
        )

    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_tool_failure_is_not_silently_ignored() -> None:
    runtime, _, _, sandbox = create_runtime(
        [
            tool_call_response(
                "calculator",
                '{"expression":"import os"}',
            ),
        ]
    )

    with pytest.raises(
        ToolExecutionError,
    ):
        await runtime.run(
            "Execute something dangerous",
        )

    assert len(sandbox.calls) == 1

    assert sandbox.calls[0] == (
        "calculator",
        {
            "expression": "import os",
        },
    )


@pytest.mark.asyncio
async def test_agent_passes_tool_messages_back_to_inference() -> None:
    runtime, inference, _, _ = create_runtime(
        [
            tool_call_response(
                "calculator",
                '{"expression":"2 + 2"}',
                "call-123",
            ),
            final_response(
                "The answer is 4.",
            ),
        ]
    )

    result = await runtime.run(
        "What is 2 + 2?",
    )

    assert result.answer == "The answer is 4."
    assert len(inference.calls) == 2

    second_call_messages = inference.calls[1]["messages"]

    assert any(
        message.get("role") == "assistant"
        and message.get("tool_calls")
        for message in second_call_messages
    )

    assert any(
        message.get("role") == "tool"
        and message.get("tool_call_id") == "call-123"
        and message.get("name") == "calculator"
        and message.get("content") == "4"
        for message in second_call_messages
    )


@pytest.mark.asyncio
async def test_agent_passes_required_capabilities_to_router() -> None:
    runtime, _, router, _ = create_runtime(
        [
            final_response("Done."),
        ]
    )

    result = await runtime.run(
        "Do something",
        session_id="session-123",
        task="special task",
        required_capabilities=[
            "calculator",
        ],
    )

    assert result.status == "success"

    assert len(router.calls) == 1

    assert router.calls[0]["session_id"] == "session-123"

    assert router.calls[0]["task"] == "special task"

    assert router.calls[0]["required_capabilities"] == [
        "calculator",
    ]


@pytest.mark.asyncio
async def test_agent_generates_session_id_when_missing() -> None:
    runtime, _, router, _ = create_runtime(
        [
            final_response("Hello."),
        ]
    )

    result = await runtime.run(
        "Say hello",
    )

    assert result.status == "success"

    assert len(router.calls) == 1

    session_id = router.calls[0]["session_id"]

    assert isinstance(session_id, str)
    assert session_id != ""
    assert session_id == result.execution_id


@pytest.mark.asyncio
async def test_agent_uses_intent_as_task_when_task_missing() -> None:
    runtime, _, router, _ = create_runtime(
        [
            final_response("Done."),
        ]
    )

    await runtime.run(
        "Calculate something",
    )

    assert len(router.calls) == 1

    assert router.calls[0]["task"] == (
        "Calculate something"
    )


@pytest.mark.asyncio
async def test_agent_records_multiple_tool_calls() -> None:
    runtime, _, _, sandbox = create_runtime(
        [
            tool_call_response(
                "calculator",
                '{"expression":"10 + 5"}',
                "call-1",
            ),
            tool_call_response(
                "calculator",
                '{"expression":"15 * 2"}',
                "call-2",
            ),
            final_response(
                "The final answer is 30.",
            ),
        ]
    )

    result = await runtime.run(
        "Calculate 10 + 5 and multiply by 2.",
    )

    assert result.status == "success"
    assert result.steps == 3
    assert len(result.tool_calls) == 2

    assert len(sandbox.calls) == 2

    assert result.tool_calls[0].name == "calculator"
    assert result.tool_calls[0].arguments == {
        "expression": "10 + 5",
    }
    assert result.tool_calls[0].result == "15"

    assert result.tool_calls[1].name == "calculator"
    assert result.tool_calls[1].arguments == {
        "expression": "15 * 2",
    }
    assert result.tool_calls[1].result == "30"


@pytest.mark.asyncio
async def test_agent_does_not_execute_unknown_tool() -> None:
    runtime, _, _, sandbox = create_runtime(
        [
            tool_call_response(
                "delete_all_files",
                "{}",
            ),
        ]
    )

    with pytest.raises(
        AgentProtocolError,
        match="Unknown tool requested by model",
    ):
        await runtime.run(
            "Delete all files",
        )

    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_agent_continues_when_planner_returns_continue() -> None:
    runtime, inference, _, sandbox = create_runtime(
        [
            final_response("Intermediate response."),
            final_response("Final response."),
        ]
    )

    runtime.planner = FakePlanner(
        [
            AgentDecision(
                type=DecisionType.CONTINUE,
            ),
            AgentDecision(
                type=DecisionType.FINAL,
                content="Continued successfully.",
            ),
        ]
    )

    result = await runtime.run(
        "Continue this task",
    )

    assert result.status == "success"
    assert result.answer == "Continued successfully."

    assert len(inference.calls) == 2
    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_agent_fails_when_planner_returns_fail() -> None:
    runtime, inference, _, sandbox = create_runtime(
        [
            final_response("Failure response."),
        ]
    )

    runtime.planner = FakePlanner(
        [
            AgentDecision(
                type=DecisionType.FAIL,
                error="The agent cannot safely continue.",
            ),
        ]
    )

    with pytest.raises(
        RuntimeError,
        match="The agent cannot safely continue",
    ):
        await runtime.run(
            "Do something unsafe",
        )

    assert len(inference.calls) == 1
    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_agent_fail_uses_default_error_when_missing() -> None:
    runtime, _, _, sandbox = create_runtime(
        [
            final_response("Failure response."),
        ]
    )

    runtime.planner = FakePlanner(
        [
            AgentDecision(
                type=DecisionType.FAIL,
            ),
        ]
    )

    with pytest.raises(
        RuntimeError,
        match="Agent returned a failure decision",
    ):
        await runtime.run(
            "Fail this task",
        )

    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_agent_continue_still_respects_max_steps() -> None:
    runtime, inference, _, sandbox = create_runtime(
        [
            final_response("Intermediate 1"),
            final_response("Intermediate 2"),
            final_response("Intermediate 3"),
        ],
        max_steps=3,
    )

    runtime.planner = FakePlanner(
        [
            AgentDecision(
                type=DecisionType.CONTINUE,
            ),
            AgentDecision(
                type=DecisionType.CONTINUE,
            ),
            AgentDecision(
                type=DecisionType.CONTINUE,
            ),
        ]
    )

    with pytest.raises(
        AgentMaxStepsError,
        match="maximum steps",
    ):
        await runtime.run(
            "Keep going",
        )

    assert len(inference.calls) == 3
    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_agent_continue_does_not_execute_tools() -> None:
    runtime, _, _, sandbox = create_runtime(
        [
            final_response("Continue."),
            final_response("Done."),
        ]
    )

    runtime.planner = FakePlanner(
        [
            AgentDecision(
                type=DecisionType.CONTINUE,
            ),
            AgentDecision(
                type=DecisionType.FINAL,
                content="Done.",
            ),
        ]
    )

    result = await runtime.run(
        "Continue without tools",
    )

    assert result.status == "success"
    assert result.answer == "Done."
    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_agent_decision_fail_does_not_execute_tools() -> None:
    runtime, _, _, sandbox = create_runtime(
        [
            final_response("Stop."),
        ]
    )

    runtime.planner = FakePlanner(
        [
            AgentDecision(
                type=DecisionType.FAIL,
                error="Execution must stop.",
            ),
        ]
    )

    with pytest.raises(
        RuntimeError,
        match="Execution must stop",
    ):
        await runtime.run(
            "Stop this execution",
        )

    assert sandbox.calls == []

@pytest.mark.asyncio
async def test_agent_hard_cancels_hanging_inference() -> None:
    runtime, _, router, sandbox = create_runtime(
        [
            final_response("unused"),
        ]
    )

    inference = HangingInference()

    runtime.inference = inference

    runtime.limits = ExecutionLimits(
        max_steps=8,
        max_tool_calls=20,
        timeout_seconds=0.05,
    )

    with pytest.raises(
        ExecutionLimitExceeded,
        match="inference exceeded execution timeout",
    ):
        await runtime.run(
            "Hang forever",
        )

    assert inference.started is True
    assert inference.cancelled is True

    assert sandbox.calls == []

    assert len(router.calls) == 1

@pytest.mark.asyncio
async def test_agent_hard_cancels_hanging_tool_execution() -> None:
    runtime, inference, _, sandbox = create_runtime(
        [
            tool_call_response(
                "calculator",
                '{"expression":"1 + 1"}',
            ),
        ]
    )

    hanging_executor = HangingToolExecutor()

    runtime.tool_executor = hanging_executor

    runtime.limits = ExecutionLimits(
        max_steps=8,
        max_tool_calls=20,
        timeout_seconds=0.05,
    )

    with pytest.raises(
        ExecutionLimitExceeded,
        match="tool execution exceeded execution timeout",
    ):
        await runtime.run(
            "Calculate 1 + 1",
        )

    assert hanging_executor.started is True
    assert hanging_executor.cancelled is True

    assert len(inference.calls) == 1

    assert sandbox.calls == []
