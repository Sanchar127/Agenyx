import asyncio

import pytest

from app.agent_runtime.event_stream import EventStream
from app.agent_runtime.events import AgentEvent


@pytest.mark.asyncio
async def test_publish_and_consume_event() -> None:
    stream = EventStream()

    event = AgentEvent(
        type="execution_started",
        execution_id="exec-1",
    )

    await stream.publish(event)
    await stream.close()

    received = [item async for item in stream.events()]

    assert received == [event]


@pytest.mark.asyncio
async def test_events_preserve_publication_order() -> None:
    stream = EventStream()

    events = [
        AgentEvent(
            type="execution_started",
            execution_id="exec-1",
        ),
        AgentEvent(
            type="inference_started",
            execution_id="exec-1",
        ),
        AgentEvent(
            type="inference_completed",
            execution_id="exec-1",
        ),
    ]

    for event in events:
        await stream.publish(event)

    await stream.close()

    received = [item async for item in stream.events()]

    assert received == events


@pytest.mark.asyncio
async def test_consumer_waits_for_future_event() -> None:
    stream = EventStream()

    async def consume_first_event() -> AgentEvent:
        async for event in stream.events():
            return event

        raise AssertionError("Stream closed before event was received")

    consumer = asyncio.create_task(consume_first_event())

    await asyncio.sleep(0)

    assert not consumer.done()

    event = AgentEvent(
        type="tool_call_started",
        execution_id="exec-1",
    )

    await stream.publish(event)

    assert await consumer == event

    await stream.close()


@pytest.mark.asyncio
async def test_close_terminates_consumer() -> None:
    stream = EventStream()

    await stream.close()

    received = [item async for item in stream.events()]

    assert received == []


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    stream = EventStream()

    await stream.close()
    await stream.close()

    assert stream.closed is True


@pytest.mark.asyncio
async def test_publish_after_close_is_rejected() -> None:
    stream = EventStream()

    await stream.close()

    with pytest.raises(RuntimeError, match="closed event stream"):
        await stream.publish(
            AgentEvent(
                type="execution_started",
                execution_id="exec-1",
            )
        )


@pytest.mark.asyncio
async def test_stream_reports_closed_state() -> None:
    stream = EventStream()

    assert stream.closed is False

    await stream.close()

    assert stream.closed is True
