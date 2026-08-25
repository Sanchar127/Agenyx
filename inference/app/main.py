from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.registry import ProviderRegistry
from app.reliability.manager import ReliabilityManager

settings = get_settings()
registry = ProviderRegistry()

reliability = ReliabilityManager(
    degraded_failure_threshold=1,
    unhealthy_failure_threshold=3,
)

provider = OpenAICompatibleProvider(
    provider_name=settings.provider_name,
    base_url=settings.backend_base_url,
    api_key=settings.backend_api_key,
    timeout=settings.request_timeout_seconds,
    max_connections=settings.max_connections,
    max_keepalive_connections=settings.max_keepalive_connections,
    max_retries=settings.max_retries,
)

registry.register(provider)
reliability.register(provider.name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle.

    Provider resources are released when the application shuts down.
    """

    yield

    await registry.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""

    return {
        "status": "ok",
    }


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """Readiness probe."""

    provider = registry.get(settings.provider_name)

    if not await provider.health():
        raise HTTPException(
            status_code=503,
            detail="Inference backend unavailable",
        )

    return {
        "status": "ready",
        "provider": provider.name,
    }


@app.get("/v1/providers")
async def providers() -> dict[str, Any]:
    """List registered inference providers."""

    return {
        "object": "list",
        "data": [
            {
                "id": name,
                "object": "provider",
            }
            for name in registry.list()
        ],
    }


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    """OpenAI-compatible model listing."""

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

@app.post(
    "/v1/chat/completions",
    response_model=None,
)
async def chat_completions(
    request: Request,
) -> JSONResponse:
    """
    OpenAI-compatible chat completion endpoint.
    """

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

    messages = payload.get("messages")

    if not isinstance(messages, list) or not messages:
        raise HTTPException(
            status_code=400,
            detail="Field 'messages' must be a non-empty list",
        )

    payload.setdefault(
        "model",
        settings.model,
    )

    if payload.get("stream") is True:
        raise HTTPException(
            status_code=501,
            detail="Streaming is not implemented yet",
        )

    provider = registry.get(settings.provider_name)

    # Check circuit-breaker / reliability state.
    if not reliability.is_available(provider.name):
        raise HTTPException(
            status_code=503,
            detail=f"Provider '{provider.name}' is currently unavailable",
        )

    try:
        response = await provider.chat_completion(payload)

    except Exception as exc:
        reliability.record_failure(provider.name)

        raise HTTPException(
            status_code=502,
            detail=f"Inference provider request failed: {exc}",
        ) from exc

    reliability.record_success(provider.name)

    return JSONResponse(
        content=response,
    )

@app.get("/v1/reliability")
async def reliability_status() -> dict[str, Any]:
    """
    Return provider reliability state.
    """

    return {
        "object": "reliability",
        "providers": [
            {
                "provider": state.provider_name,
                "status": state.status.value,
                "consecutive_failures": state.consecutive_failures,
                "total_failures": state.total_failures,
                "total_successes": state.total_successes,
                "last_failure_at": (
                    state.last_failure_at.isoformat()
                    if state.last_failure_at
                    else None
                ),
                "last_success_at": (
                    state.last_success_at.isoformat()
                    if state.last_success_at
                    else None
                ),
            }
            for state in reliability.list_states()
        ],
    }
