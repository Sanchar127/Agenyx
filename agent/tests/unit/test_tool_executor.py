from __future__ import annotations

import pytest

from app.sandbox.client import ToolSandboxClient
from app.tools.executor import ToolExecutor
from app.tools.registry import Tool, ToolRegistry
from app.tools.result import ToolResult


class FakeSandbox:
    """Fake sandbox used to test ToolExecutor without HTTP."""

    def __init__(
        self,
        *,
        result: str = "hello",
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    async def execute(
        self,
        name: str,
        arguments: dict,
    ) -> str:
        self.calls.append((name, arguments))

        if self.error is not None:
            raise self.error

        return self.result


def create_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        Tool(
            name="echo",
            description="Returns the provided value.",
            input_schema={
                "type": "object",
                "properties": {
                    "value": {
                        "type": "string",
                    }
                },
                "required": ["value"],
            },
            execute=lambda value: value,
        )
    )

    return registry


@pytest.mark.asyncio
async def test_executor_returns_successful_tool_result() -> None:
    registry = create_registry()
    sandbox = FakeSandbox(result="hello")

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
    )

    result = await executor.execute(
        name="echo",
        arguments={"value": "hello"},
    )

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.output == "hello"
    assert result.error is None
    assert result.duration_seconds is not None
    assert result.duration_seconds >= 0

    assert sandbox.calls == [
        ("echo", {"value": "hello"}),
    ]


@pytest.mark.asyncio
async def test_executor_handles_sandbox_failure() -> None:
    registry = create_registry()
    sandbox = FakeSandbox(
        error=RuntimeError("sandbox execution failed"),
    )

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
    )

    result = await executor.execute(
        name="echo",
        arguments={"value": "hello"},
    )

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.output is None
    assert result.error is not None
    assert "sandbox execution failed" in result.error.lower()
    assert result.duration_seconds is not None
    assert result.duration_seconds >= 0

    assert sandbox.calls == [
        ("echo", {"value": "hello"}),
    ]


@pytest.mark.asyncio
async def test_executor_handles_unknown_tool() -> None:
    registry = create_registry()
    sandbox = FakeSandbox()

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
    )

    result = await executor.execute(
        name="does_not_exist",
        arguments={},
    )

    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.output is None
    assert result.error is not None
    assert "unknown tool" in result.error.lower()
    assert result.duration_seconds is not None
    assert result.duration_seconds >= 0

    # Unknown tools must never reach the sandbox.
    assert sandbox.calls == []


@pytest.mark.asyncio
async def test_executor_passes_arguments_to_sandbox() -> None:
    registry = create_registry()
    sandbox = FakeSandbox(result="42")

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
    )

    result = await executor.execute(
        name="echo",
        arguments={"value": "42"},
    )

    assert result.success is True
    assert result.output == "42"

    assert sandbox.calls == [
        ("echo", {"value": "42"}),
    ]


@pytest.mark.asyncio
async def test_executor_records_duration() -> None:
    registry = create_registry()
    sandbox = FakeSandbox()

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
    )

    result = await executor.execute(
        name="echo",
        arguments={"value": "hello"},
    )

    assert result.duration_seconds is not None
    assert result.duration_seconds >= 0
