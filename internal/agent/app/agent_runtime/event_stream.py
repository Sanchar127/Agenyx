from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.agent_runtime.events import AgentEvent


class EventStream:
    """
    Asynchronous in-memory event stream for one agent execution.

    The producer publishes events while consumers asynchronously
    iterate over them.

    This abstraction is intentionally independent of HTTP/SSE/WebSocket
    transport.
    """

    _CLOSED = object()

    def __init__(self) -> None:
        self._queue: asyncio.Queue[AgentEvent | object] = asyncio.Queue()
        self._closed = False

    async def publish(self, event: AgentEvent) -> None:
        """
        Publish an event to the stream.

        Publishing after the stream has been closed is rejected.
        """
        if self._closed:
            raise RuntimeError("Cannot publish to a closed event stream")

        await self._queue.put(event)

    async def close(self) -> None:
        """
        Close the stream.

        Consumers currently waiting for an event are released and
        terminate their iteration.
        """
        if self._closed:
            return

        self._closed = True
        await self._queue.put(self._CLOSED)

    async def events(self) -> AsyncIterator[AgentEvent]:
        """
        Consume events in publication order until the stream closes.
        """
        while True:
            item = await self._queue.get()

            if item is self._CLOSED:
                return

            yield item

    @property
    def closed(self) -> bool:
        return self._closed
