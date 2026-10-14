from __future__ import annotations

from typing import Any

import pytest

from app.agent_runtime.event_stream import EventStream
from app.agent_runtime.event_types import AgentEventType
from app.agent_runtime.events import AgentEvent
from app.agent_runtime.runtime import AgentRuntime

from test_runtime import (
    create_runtime,
    final_response,
    tool_call_response,
)


# ============================================================
# Helpers
# ============================================================


@pytest.fixture
def published_events(
    monkeypatch: pytest.MonkeyPatch,
) -> list[AgentEvent]:
    """
    Capture every event published by AgentRuntime.

    EventStream itself is tested separately in
    tests/unit/test_event_stream.py.

    These tests therefore focus only on whether Runtime
    publishes the correct events.
    """

    events: list[AgentEvent] = []

    async def capture_publish(
        self: EventStream,
        event: AgentEvent,
    ) -> None:
        events.append(event)

    monkeypatch.setattr(
        EventStream,
        "publish",
        capture_publish,
    )

    return events


# ============================================================
# Execution lifecycle
# ============================================================


@pytest.mark.asyncio
async def test_runtime_emits_execution_started_and_completed(
    published_events: list[AgentEvent],
) -> None:
    runtime, _, _, _ = create_runtime(
        [
            final_response("Hello!"),
        ]
    )

    result = await runtime.run(
        "Say hello",
    )

    assert result.status == "success"

    assert [
        event.type
        for event in published_events
    ] == [
        AgentEventType.EXECUTION_STARTED.value,
        AgentEventType.INFERENCE_STARTED.value,
        AgentEventType.INFERENCE_COMPLETED.value,
        AgentEventType.EXECUTION_COMPLETED.value,
    ]

    assert (
        published_events[0].execution_id
        == result.execution_id
    )

    assert (
        published_events[-1].execution_id
        == result.execution_id
    )


# ============================================================
# Inference lifecycle
# ============================================================


@pytest.mark.asyncio
async def test_runtime_emits_inference_lifecycle_events(
    published_events: list[AgentEvent],
) -> None:
    runtime, _, _, _ = create_runtime(
        [
            final_response("Hello!"),
        ]
    )

    result = await runtime.run(
        "Say hello",
    )

    assert result.status == "success"

    inference_events = [
        event
        for event in published_events
        if event.type
        in {
            AgentEventType.INFERENCE_STARTED.value,
            AgentEventType.INFERENCE_COMPLETED.value,
        }
    ]

    assert [
        event.type
        for event in inference_events
    ] == [
        AgentEventType.INFERENCE_STARTED.value,
        AgentEventType.INFERENCE_COMPLETED.value,
    ]

    assert inference_events[0].data["step"] == 1
    assert inference_events[0].data["model"] == "test-model"

    assert inference_events[1].data["step"] == 1
    assert inference_events[1].data["model"] == "test-model"


# ============================================================
# Tool lifecycle
# ============================================================


@pytest.mark.asyncio
async def test_runtime_emits_tool_call_lifecycle_events(
    published_events: list[AgentEvent],
) -> None:
    runtime, _, _, _ = create_runtime(
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

    tool_events = [
        event
        for event in published_events
        if event.type
        in {
            AgentEventType.TOOL_CALL_STARTED.value,
            AgentEventType.TOOL_CALL_COMPLETED.value,
        }
    ]

    assert [
        event.type
        for event in tool_events
    ] == [
        AgentEventType.TOOL_CALL_STARTED.value,
        AgentEventType.TOOL_CALL_COMPLETED.value,
    ]

    started = tool_events[0]
    completed = tool_events[1]

    assert started.data["call_id"] == "call-1"
    assert started.data["tool_name"] == "calculator"

    assert completed.data["call_id"] == "call-1"
    assert completed.data["tool_name"] == "calculator"
    assert completed.data["success"] is True


# ============================================================
# Failed execution
# ============================================================


@pytest.mark.asyncio
async def test_runtime_emits_execution_failed(
    published_events: list[AgentEvent],
) -> None:
    runtime, _, _, _ = create_runtime(
        [
            {
                "invalid": "response",
            }
        ]
    )

    with pytest.raises(Exception):
        await runtime.run(
            "Do something",
        )

    failed_events = [
        event
        for event in published_events
        if event.type
        == AgentEventType.EXECUTION_FAILED.value
    ]

    assert len(failed_events) == 1

    failed = failed_events[0]

    assert failed.data["error_type"] == (
        "AgentProtocolError"
    )

    assert failed.data["error"]


# ============================================================
# Cancellation
# ============================================================


@pytest.mark.asyncio
async def test_runtime_emits_execution_cancelled(
    published_events: list[AgentEvent],
) -> None:
    runtime, _, _, _ = create_runtime(
        [
            final_response("unused"),
        ]
    )

    from test_runtime import HangingInference

    hanging_inference = HangingInference()

    runtime.inference = hanging_inference

    task = pytest.importorskip("asyncio").create_task(
        runtime.run(
            "Hang until cancelled",
        )
    )

    await pytest.importorskip("asyncio").wait_for(
        hanging_inference.started.wait(),
        timeout=1.0,
    )

    execution_id = next(
        iter(runtime._active_executions)
    )

    cancelled = await runtime.cancel(
        execution_id,
    )

    assert cancelled is True

    result = await pytest.importorskip("asyncio").wait_for(
        task,
        timeout=1.0,
    )

    assert result.status == "cancelled"

    cancelled_events = [
        event
        for event in published_events
        if event.type
        == AgentEventType.EXECUTION_CANCELLED.value
    ]

    assert len(cancelled_events) == 1

    event = cancelled_events[0]

    assert event.execution_id == execution_id
    assert event.data["reason"] in {
        "task_cancelled",
        "execution_cancelled",
    }


# ============================================================
# Execution identity
# ============================================================


@pytest.mark.asyncio
async def test_runtime_event_contains_execution_id(
    published_events: list[AgentEvent],
) -> None:
    runtime, _, _, _ = create_runtime(
        [
            final_response("Hello!"),
        ]
    )

    result = await runtime.run(
        "Say hello",
    )

    assert result.status == "success"
    assert result.execution_id

    assert all(
        event.execution_id == result.execution_id
        for event in published_events
    )


# ============================================================
# Raw inference output protection
# ============================================================


@pytest.mark.asyncio
async def test_runtime_does_not_stream_raw_inference_output(
    published_events: list[AgentEvent],
) -> None:
    private_response = (
        "THIS_IS_A_PRIVATE_LLM_RESPONSE"
    )

    runtime, _, _, _ = create_runtime(
        [
            final_response(private_response),
        ]
    )

    result = await runtime.run(
        "Say hello",
    )

    assert result.status == "success"
    assert result.answer == private_response

    serialized_events = str(
        [
            {
                "type": event.type,
                "execution_id": event.execution_id,
                "data": event.data,
            }
            for event in published_events
        ]
    )

    assert private_response not in serialized_events


# ============================================================
# Observability isolation
# ============================================================


@pytest.mark.asyncio
async def test_event_stream_failure_does_not_fail_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_publish(
        self: EventStream,
        event: Any,
    ) -> None:
        raise RuntimeError(
            "event stream unavailable"
        )

    monkeypatch.setattr(
        EventStream,
        "publish",
        failing_publish,
    )

    runtime, _, _, _ = create_runtime(
        [
            final_response("Hello!"),
        ]
    )

    result = await runtime.run(
        "Say hello",
    )

    assert result.status == "success"
    assert result.answer == "Hello!"
