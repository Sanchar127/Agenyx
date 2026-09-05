from __future__ import annotations

from typing import Any

import pytest

from app.agent_runtime.domain import (
    StepStatus,
    StepType,
)
from app.agent_runtime.planner import Planner
from app.agent_runtime.runtime import AgentRuntime
from app.core.errors import (
    AgentMaxStepsError,
    ExecutionLimitExceeded,
)
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

@pytest.mark.asyncio
async def test_runtime_stops_after_max_steps() -> None:
    """
    The runtime must not perform inference beyond max_steps.
    """

    inference = FakeInference(
        [
            calculator_tool_response(
                expression="2 + 2",
                call_id="call_1",
            ),
            # This response must never be consumed.
            final_response(
                "This must never execute."
            ),
        ]
    )

    runtime = create_runtime(
        inference=inference,
        max_steps=1,
    )

    with pytest.raises(
        AgentMaxStepsError,
        match="maximum steps",
    ):
        await runtime.run(
            "Keep calculating."
        )

    # Exactly one inference iteration was permitted.
    assert inference.calls == 1


@pytest.mark.asyncio
async def test_max_steps_error_is_execution_limit_error() -> None:
    """
    AgentMaxStepsError must remain compatible with the
    higher-level ExecutionLimitExceeded abstraction.
    """

    inference = FakeInference(
        [
            calculator_tool_response(
                expression="2 + 2",
                call_id="call_1",
            )
        ]
    )

    runtime = create_runtime(
        inference=inference,
        max_steps=1,
    )

    with pytest.raises(
        ExecutionLimitExceeded
    ) as exc_info:
        await runtime.run(
            "Keep calculating."
        )

    assert isinstance(
        exc_info.value,
        AgentMaxStepsError,
    )

    assert inference.calls == 1


@pytest.mark.asyncio
async def test_max_steps_allows_exactly_configured_iterations() -> None:
    """
    max_steps=2 permits exactly two inference iterations,
    but never starts a third.
    """

    inference = FakeInference(
        [
            # Step 1.
            calculator_tool_response(
                expression="2 + 2",
                call_id="call_1",
            ),
            # Step 2.
            calculator_tool_response(
                expression="3 + 3",
                call_id="call_2",
            ),
            # Must never be consumed.
            final_response(
                "This must never execute."
            ),
        ]
    )

    runtime = create_runtime(
        inference=inference,
        max_steps=2,
    )

    with pytest.raises(
        AgentMaxStepsError,
        match="maximum steps",
    ):
        await runtime.run(
            "Keep calculating."
        )

    # Exactly two inference iterations were permitted.
    assert inference.calls == 2


@pytest.mark.asyncio
async def test_max_steps_failure_is_recorded_by_runtime() -> None:
    """
    When the execution limit is exceeded, AgentRuntime must
    record the failure before propagating the exception.

    The current public API raises the exception instead of
    returning the internal Execution object, so this test verifies
    the externally observable failure contract.
    """

    inference = FakeInference(
        [
            calculator_tool_response(
                expression="2 + 2",
                call_id="call_1",
            )
        ]
    )

    runtime = create_runtime(
        inference=inference,
        max_steps=1,
    )

    with pytest.raises(
        AgentMaxStepsError
    ) as exc_info:
        await runtime.run(
            "Keep calculating."
        )

    assert (
        "maximum steps"
        in str(exc_info.value).lower()
    )

    # No second inference was started.
    assert inference.calls == 1
