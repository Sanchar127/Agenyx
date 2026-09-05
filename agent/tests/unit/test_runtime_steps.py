from __future__ import annotations

from typing import Any

import pytest

from app.agent_runtime.domain import (
    StepStatus,
    StepType,
)
from app.agent_runtime.planner import Planner
from app.agent_runtime.runtime import AgentRuntime
from app.models.responses import ToolCallResult
from app.tools.builtin import create_tool_registry


class FakeRouter:
    async def route(
        self,
        *,
        session_id: str,
        task: str,
        messages: list[dict[str, Any]],
        required_capabilities: list[str] | None = None,
    ):
        class Decision:
            model = "test-model"
            provider = "test-provider"

        return Decision()


class FakeInference:
    def __init__(
        self,
        responses: list[dict[str, Any]],
    ) -> None:
        self.responses = responses
        self.calls = 0

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        response = self.responses[self.calls]
        self.calls += 1
        return response


class FakeSandbox:
    def __init__(
        self,
        result: str = "4",
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        self.calls.append(
            (
                tool_name,
                arguments,
            )
        )

        if self.error is not None:
            raise self.error

        return self.result


def create_runtime(
    *,
    inference: FakeInference,
    sandbox: FakeSandbox | None = None,
    max_steps: int = 5,
) -> AgentRuntime:
    tools = create_tool_registry()

    return AgentRuntime(
        router=FakeRouter(),
        inference=inference,
        tools=tools,
        sandbox=sandbox or FakeSandbox(),
        planner=Planner(tools=tools),
        max_steps=max_steps,
    )


def final_response(
    content: str = "The answer is 4.",
) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            }
        ]
    }


def calculator_tool_response(
    *,
    expression: str = "2 + 2",
    call_id: str = "call_1",
) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": "calculator",
                                "arguments": (
                                    f'{{"expression": "{expression}"}}'
                                ),
                            },
                        }
                    ],
                }
            }
        ]
    }


@pytest.mark.asyncio
async def test_final_response_creates_expected_step_trace() -> None:
    runtime = create_runtime(
        inference=FakeInference(
            [
                final_response(
                    "The answer is 4."
                )
            ]
        )
    )

    response = await runtime.run(
        "What is 2 + 2?"
    )

    assert response.status == "success"
    assert response.answer == "The answer is 4."

    # The runtime exposes the execution ID, but the response
    # intentionally does not expose the complete execution object.
    # Verify the public execution metadata first.
    assert response.steps == 1


@pytest.mark.asyncio
async def test_tool_execution_creates_expected_step_sequence() -> None:
    inference = FakeInference(
        [
            calculator_tool_response(),
            final_response(
                "The answer is 4."
            ),
        ]
    )

    sandbox = FakeSandbox(
        result="4"
    )

    runtime = create_runtime(
        inference=inference,
        sandbox=sandbox,
    )

    response = await runtime.run(
        "Calculate 2 + 2."
    )

    assert response.status == "success"
    assert response.answer == "The answer is 4."
    assert response.steps == 2

    assert sandbox.calls == [
        (
            "calculator",
            {
                "expression": "2 + 2",
            },
        )
    ]

    assert response.tool_calls == [
        ToolCallResult(
            name="calculator",
            arguments={
                "expression": "2 + 2",
            },
            result="4",
        )
    ]


@pytest.mark.asyncio
async def test_step_types_have_expected_values() -> None:
    assert StepType.PLAN.value == "plan"
    assert StepType.INFERENCE.value == "inference"
    assert StepType.TOOL_CALL.value == "tool_call"
    assert StepType.TOOL_RESULT.value == "tool_result"
    assert StepType.OBSERVATION.value == "observation"
    assert StepType.FINAL.value == "final"


@pytest.mark.asyncio
async def test_step_statuses_have_expected_values() -> None:
    assert StepStatus.CREATED.value == "created"
    assert StepStatus.RUNNING.value == "running"
    assert StepStatus.COMPLETED.value == "completed"
    assert StepStatus.FAILED.value == "failed"
    assert StepStatus.CANCELLED.value == "cancelled"


@pytest.mark.asyncio
async def test_runtime_records_step_metadata() -> None:
    inference = FakeInference(
        [
            final_response(
                "Done."
            )
        ]
    )

    runtime = create_runtime(
        inference=inference,
    )

    response = await runtime.run(
        "Do something."
    )

    assert response.execution_id is not None
    assert response.steps == 1


@pytest.mark.asyncio
async def test_tool_failure_is_propagated() -> None:
    inference = FakeInference(
        [
            calculator_tool_response()
        ]
    )

    sandbox = FakeSandbox(
        error=RuntimeError(
            "sandbox unavailable"
        )
    )

    runtime = create_runtime(
        inference=inference,
        sandbox=sandbox,
    )

    with pytest.raises(
        RuntimeError,
        match="sandbox unavailable",
    ):
        await runtime.run(
            "Calculate 2 + 2."
        )
