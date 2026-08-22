
from __future__ import annotations

import pytest

from app.agent_runtime.runtime import AgentRuntime
from app.core.errors import (
    AgentMaxStepsError,
    AgentProtocolError,
    ToolExecutionError,
)
from app.llm.fake import FakeLLMProvider
from app.sandbox.client import ToolSandboxClient
from app.tools.builtin import create_tool_registry


class FakeToolSandbox(ToolSandboxClient):
    """In-memory sandbox used by runtime unit tests."""

    def __init__(self) -> None:
        self.tools = create_tool_registry()
        self.calls: list[tuple[str, dict]] = []

    async def execute(
        self,
        name: str,
        arguments: dict,
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


def create_runtime(
    llm: FakeLLMProvider,
    *,
    max_steps: int = 8,
) -> tuple[AgentRuntime, FakeToolSandbox]:
    sandbox = FakeToolSandbox()

    runtime = AgentRuntime(
        llm=llm,
        tools=create_tool_registry(),
        max_steps=max_steps,
        sandbox=sandbox,
    )

    return runtime, sandbox


def tool_call_response(
    name: str,
    arguments: str,
    call_id: str = "call-1",
) -> dict:
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


def final_response(answer: str) -> dict:
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
    llm = FakeLLMProvider(
        [
            final_response("Hello!"),
        ]
    )

    runtime, sandbox = create_runtime(llm)

    result = await runtime.run("Say hello")

    assert result.status == "success"
    assert result.answer == "Hello!"
    assert result.steps == 1
    assert result.tool_calls == []
    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_agent_executes_tool_through_sandbox() -> None:
    llm = FakeLLMProvider(
        [
            tool_call_response(
                "calculator",
                '{"expression":"25 * 17"}',
            ),
            final_response(
                "The answer is 425."
            ),
        ]
    )

    runtime, sandbox = create_runtime(llm)

    result = await runtime.run(
        "What is 25 * 17?"
    )

    assert result.status == "success"
    assert result.answer == "The answer is 425."
    assert result.steps == 2

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "calculator"
    assert result.tool_calls[0].result == "425"

    assert sandbox.calls == [
        (
            "calculator",
            {"expression": "25 * 17"},
        )
    ]


@pytest.mark.asyncio
async def test_agent_supports_multiple_steps() -> None:
    llm = FakeLLMProvider(
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
                "The final result is 435."
            ),
        ]
    )

    runtime, sandbox = create_runtime(llm)

    result = await runtime.run(
        "Calculate 25 * 17 and then add 10."
    )

    assert result.steps == 3
    assert len(result.tool_calls) == 2

    assert result.tool_calls[0].result == "425"
    assert result.tool_calls[1].result == "435"

    assert result.answer == (
        "The final result is 435."
    )

    assert sandbox.calls == [
        (
            "calculator",
            {"expression": "25 * 17"},
        ),
        (
            "calculator",
            {"expression": "425 + 10"},
        ),
    ]


@pytest.mark.asyncio
async def test_agent_enforces_max_steps() -> None:
    llm = FakeLLMProvider(
        [
            tool_call_response(
                "calculator",
                '{"expression":"1 + 1"}',
                f"call-{i}",
            )
            for i in range(8)
        ]
    )

    runtime, sandbox = create_runtime(
        llm,
        max_steps=3,
    )

    with pytest.raises(AgentMaxStepsError):
        await runtime.run(
            "Keep calculating forever"
        )

    assert len(sandbox.calls) == 3


@pytest.mark.asyncio
async def test_agent_rejects_invalid_llm_response() -> None:
    llm = FakeLLMProvider(
        [
            {
                "invalid": "response"
            }
        ]
    )

    runtime, sandbox = create_runtime(llm)

    with pytest.raises(AgentProtocolError):
        await runtime.run("Do something")

    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_tool_failure_is_not_silently_ignored() -> None:
    llm = FakeLLMProvider(
        [
            tool_call_response(
                "calculator",
                '{"expression":"import os"}',
            ),
        ]
    )

    runtime, sandbox = create_runtime(llm)

    with pytest.raises(ToolExecutionError):
        await runtime.run(
            "Execute something dangerous"
        )

    assert len(sandbox.calls) == 1
    assert sandbox.calls[0] == (
        "calculator",
        {"expression": "import os"},
    )
