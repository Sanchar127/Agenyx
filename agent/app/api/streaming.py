from __future__ import annotations

import json
from collections.abc import AsyncIterator

from app.agent_runtime.event_stream import EventStream
from app.agent_runtime.events import AgentEvent


async def event_stream_to_sse(
    stream: EventStream,
) -> AsyncIterator[str]:
    """
    Convert runtime events into Server-Sent Events.

    The runtime remains transport-independent. This adapter is
    responsible only for translating AgentEvent instances into
    SSE frames.
    """

    async for event in stream.events():
        payload = {
            "execution_id": event.execution_id,
            "data": event.data,
        }

        yield (
            f"event: {event.type}\n"
            f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
        )
