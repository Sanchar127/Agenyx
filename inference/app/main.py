from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from app.backend import OpenAICompatibleBackend
from app.config import get_settings


settings = get_settings()


backend = OpenAICompatibleBackend(
    base_url=settings.backend_base_url,
    api_key=settings.backend_api_key,
    timeout=settings.request_timeout_seconds,
    max_connections=settings.max_connections,
    max_keepalive_connections=settings.max_keepalive_connections,
    max_retries=settings.max_retries,
)
@asynccontextmanager
async def lifespan(app: FastAPI):

    yield

    await backend.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:

    return {
        "status": "ok",
    }


@app.get("/ready")
async def ready() -> dict[str, str]:

    if not await backend.health():
        raise HTTPException(
            status_code=503,
            detail="Inference backend unavailable",
        )

    return {
        "status": "ready",
    }


@app.get("/v1/models")
async def models() -> dict[str, Any]:

    return {
        "object": "list",
        "data": [
            {
                "id": settings.model,
                "object": "model",
                "owned_by": "agenyx",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
) -> dict[str, Any]:

    try:
        payload = await request.json()

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON request",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="Request body must be a JSON object",
        )

    if "messages" not in payload:
        raise HTTPException(
            status_code=400,
            detail="Missing required field: messages",
        )

    payload.setdefault(
        "model",
        settings.model,
    )

    return await backend.chat_completion(payload)
