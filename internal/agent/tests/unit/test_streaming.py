from __future__ import annotations

import pytest

from app.agent_runtime.event_stream import EventStream
from app.agent_runtime.events import AgentEvent
from app.api.streaming import event_stream_to_sse


@pytest.mark.asyncio
async def test_event_stream_to_sse() -> None:
    stream = EventStream()

    await stream.publish(
        AgentEvent(
            type="execution_started",
            execution_id="execution-123",
            data={
                "session_id": "session-456",
            },
        )
    )

    await stream.close()

    events = [
        item
        async for item in event_stream_to_sse(stream)
    ]

    assert events == [
        (
            "event: execution_started\n"
            'data: {"execution_id":"execution-123","data":{"session_id":"session-456"}}\n\n'
        )
    ]
