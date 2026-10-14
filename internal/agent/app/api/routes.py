from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.submission import ExecutionSubmission
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

    @router.post(
        "/v1/agent/submit",
        response_model=ExecutionSubmission,
    )
    async def submit_agent(
        request: AgentRequest,
    ) -> ExecutionSubmission:

        runtime = runtime_provider()

        return await runtime.submit(
            request.intent,
        )

    @router.post(
        "/v1/agent/stream",
    )
    async def stream_agent(
        request: AgentRequest,
    ) -> StreamingResponse:

        runtime = runtime_provider()

        stream = await runtime.stream(
            request.intent,
        )

        return StreamingResponse(
            event_stream_to_sse(stream),
            media_type="text/event-stream",
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
