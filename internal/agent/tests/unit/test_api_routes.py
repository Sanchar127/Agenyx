from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_runtime.event_stream import EventStream
from app.agent_runtime.events import AgentEvent
from app.api.routes import create_router


class FakeRuntime:
    def __init__(self) -> None:
        self.streams: dict[str, EventStream] = {}

    def get_event_stream(
        self,
        execution_id: str,
    ) -> EventStream | None:
        return self.streams.get(execution_id)


def create_test_app(
    runtime: FakeRuntime,
) -> FastAPI:
    app = FastAPI()

    app.include_router(
        create_router(
            lambda: runtime,
        )
    )

    return app


def test_event_stream_endpoint_returns_sse() -> None:
    runtime = FakeRuntime()
    stream = EventStream()

    execution_id = "execution-123"

    runtime.streams[execution_id] = stream

    import asyncio

    asyncio.run(
        stream.publish(
            AgentEvent(
                type="execution_started",
                execution_id=execution_id,
                data={
                    "session_id": "session-123",
                },
            )
        )
    )

    asyncio.run(stream.close())

    app = create_test_app(runtime)

    with TestClient(app) as client:
        response = client.get(
            f"/v1/agent/{execution_id}/events"
        )

    assert response.status_code == 200

    assert response.headers["content-type"].startswith(
        "text/event-stream"
    )

    assert response.text == (
        "event: execution_started\n"
        'data: {"execution_id":"execution-123","data":{"session_id":"session-123"}}\n\n'
    )


def test_event_stream_endpoint_returns_404_for_unknown_execution() -> None:
    runtime = FakeRuntime()

    app = create_test_app(runtime)

    with TestClient(app) as client:
        response = client.get(
            "/v1/agent/does-not-exist/events"
        )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Execution not found or no longer active"
    }
