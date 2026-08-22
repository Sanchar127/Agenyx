from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class QueueClient(Protocol):
    """Interface required by the orchestrator queue."""

    def create_execution(
        self,
        *,
        execution_id: str,
        intent: str,
    ) -> None:
        ...

    def enqueue(
        self,
        *,
        execution_id: str,
        intent: str,
    ) -> str:
        ...

    def get_execution(
        self,
        execution_id: str,
    ) -> dict[str, Any] | None:
        ...


class AgentRequest(BaseModel):
    """Incoming agent execution request."""

    intent: str = Field(
        min_length=1,
        description="The user's intent to execute.",
    )


def create_router(queue: QueueClient) -> APIRouter:
    """Create the orchestrator API router."""

    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, str]:
        """Return orchestrator health status."""
        return {"status": "ok"}

    @router.post(
        "/v1/agent/run",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def run_agent(
        request: AgentRequest,
    ) -> dict[str, str]:
        """Create and enqueue an agent execution."""

        intent = request.intent.strip()

        if not intent:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Intent must not be empty",
            )

        execution_id = str(uuid.uuid4())

        try:
            logger.info(
                "creating_agent_execution execution_id=%s",
                execution_id,
            )

            queue.create_execution(
                execution_id=execution_id,
                intent=intent,
            )

            logger.info(
                "enqueueing_agent_execution execution_id=%s",
                execution_id,
            )

            message_id = queue.enqueue(
                execution_id=execution_id,
                intent=intent,
            )

            logger.info(
                "agent_execution_enqueued execution_id=%s message_id=%s",
                execution_id,
                message_id,
            )

        except Exception:
            logger.exception(
                "agent_execution_enqueue_failed execution_id=%s",
                execution_id,
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Task queue unavailable",
            ) from None

        return {
            "execution_id": execution_id,
            "status": "queued",
        }

    @router.get("/v1/agent/runs/{execution_id}")
    async def get_agent_run(
        execution_id: str,
    ) -> dict[str, Any]:
        """Return the current state of an agent execution."""

        try:
            execution = queue.get_execution(execution_id)
        except Exception:
            logger.exception(
                "agent_execution_lookup_failed execution_id=%s",
                execution_id,
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Execution state unavailable",
            ) from None

        if execution is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execution not found",
            )

        return execution

    return router
