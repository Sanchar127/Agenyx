from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from app.agent_runtime.runtime import AgentRuntime
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

    return router
