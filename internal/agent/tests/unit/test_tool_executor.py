from __future__ import annotations

import asyncio

import pytest

from app.agent_runtime.idempotency import (
    InMemoryIdempotencyStore,
)
from app.tools.executor import ToolExecutor
from app.tools.registry import Tool, ToolRegistry
from app.tools.result import ToolResult

from app.agent_runtime.authorization import (
    AllowListToolAuthorization,
)
from app.agent_runtime.domain.context import ExecutionContext
from app.agent_runtime.domain.execution import Execution
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


class BlockingSandbox(FakeSandbox):
    """
    Fake sandbox that blocks execution until explicitly released.

    Used to verify that concurrent requests with the same
    idempotency key do not execute the sandbox more than once.
    """

    def __init__(self, *, result: str = "hello") -> None:
        super().__init__(result=result)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(
        self,
        name: str,
        arguments: dict,
    ) -> str:
        self.calls.append((name, arguments))
        self.started.set()

        await self.release.wait()

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

    assert result.metadata["tool_name"] == "echo"

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

    assert result.metadata["error_type"] == "RuntimeError"
    assert result.metadata["tool_name"] == "echo"

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

    assert result.metadata["error_type"] == "unknown_tool"
    assert result.metadata["tool_name"] == "does_not_exist"

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


# ------------------------------------------------------------------
# IDEMPOTENCY
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_idempotency_first_call_executes_tool() -> None:
    registry = create_registry()
    sandbox = FakeSandbox(result="hello")
    store = InMemoryIdempotencyStore()

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
        idempotency_store=store,
    )

    result = await executor.execute(
        name="echo",
        arguments={"value": "hello"},
        idempotency_key="operation-1",
    )

    assert result.success is True
    assert result.output == "hello"

    assert sandbox.calls == [
        ("echo", {"value": "hello"}),
    ]


@pytest.mark.asyncio
async def test_executor_idempotency_returns_previous_result() -> None:
    registry = create_registry()
    sandbox = FakeSandbox(result="hello")
    store = InMemoryIdempotencyStore()

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
        idempotency_store=store,
    )

    first_result = await executor.execute(
        name="echo",
        arguments={"value": "hello"},
        idempotency_key="operation-1",
    )

    second_result = await executor.execute(
        name="echo",
        arguments={"value": "hello"},
        idempotency_key="operation-1",
    )

    assert second_result is first_result

    # The side effect happened only once.
    assert sandbox.calls == [
        ("echo", {"value": "hello"}),
    ]


@pytest.mark.asyncio
async def test_executor_same_key_does_not_execute_different_arguments() -> None:
    registry = create_registry()
    sandbox = FakeSandbox(result="first")
    store = InMemoryIdempotencyStore()

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
        idempotency_store=store,
    )

    first_result = await executor.execute(
        name="echo",
        arguments={"value": "first"},
        idempotency_key="operation-1",
    )

    second_result = await executor.execute(
        name="echo",
        arguments={"value": "second"},
        idempotency_key="operation-1",
    )

    assert first_result.output == "first"
    assert second_result.output == "first"

    # Idempotency is based on the logical operation key, not
    # the arguments supplied by the duplicate request.
    assert sandbox.calls == [
        ("echo", {"value": "first"}),
    ]


@pytest.mark.asyncio
async def test_executor_different_keys_execute_independently() -> None:
    registry = create_registry()
    sandbox = FakeSandbox(result="hello")
    store = InMemoryIdempotencyStore()

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
        idempotency_store=store,
    )

    first_result = await executor.execute(
        name="echo",
        arguments={"value": "one"},
        idempotency_key="operation-1",
    )

    second_result = await executor.execute(
        name="echo",
        arguments={"value": "two"},
        idempotency_key="operation-2",
    )

    assert first_result.success is True
    assert second_result.success is True

    assert sandbox.calls == [
        ("echo", {"value": "one"}),
        ("echo", {"value": "two"}),
    ]


@pytest.mark.asyncio
async def test_executor_failed_operation_releases_idempotency_key() -> None:
    registry = create_registry()
    store = InMemoryIdempotencyStore()

    failing_sandbox = FakeSandbox(
        error=RuntimeError("temporary failure"),
    )

    failing_executor = ToolExecutor(
        registry=registry,
        sandbox=failing_sandbox,
        idempotency_store=store,
    )

    first_result = await failing_executor.execute(
        name="echo",
        arguments={"value": "hello"},
        idempotency_key="operation-1",
    )

    assert first_result.success is False

    # A later attempt using the same key must be allowed to
    # execute because the original operation failed.
    successful_sandbox = FakeSandbox(result="recovered")

    successful_executor = ToolExecutor(
        registry=registry,
        sandbox=successful_sandbox,
        idempotency_store=store,
    )

    second_result = await successful_executor.execute(
        name="echo",
        arguments={"value": "hello"},
        idempotency_key="operation-1",
    )

    assert second_result.success is True
    assert second_result.output == "recovered"

    assert successful_sandbox.calls == [
        ("echo", {"value": "hello"}),
    ]


@pytest.mark.asyncio
async def test_executor_concurrent_same_key_executes_once() -> None:
    registry = create_registry()
    sandbox = BlockingSandbox(result="hello")
    store = InMemoryIdempotencyStore()

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
        idempotency_store=store,
    )

    first_task = asyncio.create_task(
        executor.execute(
            name="echo",
            arguments={"value": "hello"},
            idempotency_key="operation-1",
        )
    )

    # Wait until the first caller has actually entered the sandbox.
    await sandbox.started.wait()

    second_task = asyncio.create_task(
        executor.execute(
            name="echo",
            arguments={"value": "hello"},
            idempotency_key="operation-1",
        )
    )

    # Give the second task an opportunity to reach the idempotency
    # wait path before allowing the first operation to finish.
    await asyncio.sleep(0)

    sandbox.release.set()

    first_result, second_result = await asyncio.gather(
        first_task,
        second_task,
    )

    assert first_result.success is True
    assert second_result.success is True

    assert first_result.output == "hello"
    assert second_result.output == "hello"

    # Critical idempotency guarantee:
    # only one caller reached the sandbox.
    assert sandbox.calls == [
        ("echo", {"value": "hello"}),
    ]


@pytest.mark.asyncio
async def test_executor_allows_authorized_tool() -> None:
    sandbox = FakeSandbox()
    registry = create_registry()

    authorization = AllowListToolAuthorization.from_tools(
        {"echo"},
    )

    executor = ToolExecutor(
        registry=registry,
        sandbox=sandbox,
        authorization=authorization,
    )

    context = ExecutionContext(
        execution=Execution(),
    )

    result = await executor.execute(
        name="echo",
        arguments={"message": "hello"},
        context=context,
    )

    assert result.success is True
    assert len(sandbox.calls) == 1
