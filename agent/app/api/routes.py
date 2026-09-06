from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent_runtime.runtime import AgentRuntime
from app.api.streaming import event_stream_to_sse
from app.models.requests import AgentRequest
from app.models.responses import AgentResponse


def create_router(
    runtime_provider: Callable[[], AgentRuntime],
) -> APIRouter:

    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post(
        "/v1/agent/run",
        response_model=AgentResponse,
    )
    async def run_agent(
        request: AgentRequest,
    ) -> AgentResponse:

        runtime = runtime_provider()

        return await runtime.run(
            request.intent,
        )

    @router.get(
        "/v1/agent/{execution_id}/events",
    )
    async def stream_agent_events(
        execution_id: str,
    ) -> StreamingResponse:

        runtime = runtime_provider()

        stream = runtime.get_event_stream(
            execution_id,
        )

        if stream is None:
            raise HTTPException(
                status_code=404,
                detail="Execution not found or no longer active",
            )

        return StreamingResponse(
            event_stream_to_sse(stream),
            media_type="text/event-stream",
        )

    return router
