from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import time
from app.config import get_settings
from app.failover.manager import FailoverManager
from app.models import ModelDefinition, ModelRegistry
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.registry import ProviderRegistry
from app.reliability.manager import ReliabilityManager
from app.logger import logger
settings = get_settings()

provider_registry = ProviderRegistry()

model_registry = ModelRegistry()

reliability = ReliabilityManager(
    degraded_failure_threshold=1,
    unhealthy_failure_threshold=3,
    recovery_timeout_seconds=10.0,
)


# =========================================================
# PROVIDERS
# =========================================================

provider_registry.register(
    OpenAICompatibleProvider(
        provider_name="ollama-local",
        base_url=settings.backend_base_url,
        api_key=settings.backend_api_key,
        timeout=settings.request_timeout_seconds,
        max_connections=settings.max_connections,
        max_keepalive_connections=settings.max_keepalive_connections,
        max_retries=settings.max_retries,
    )
)


# Register every provider with reliability tracking.
for provider_name in provider_registry.list():
    reliability.register(provider_name)


# =========================================================
# MODELS
# =========================================================

# One provider can expose multiple models.

model_registry.register(
    ModelDefinition(
        model_id="qwen2.5:7b",
        provider_name="ollama-local",
    )
)

model_registry.register(
    ModelDefinition(
        model_id="llama3.2:3b",
        provider_name="ollama-local",
    )
)


# =========================================================
# FAILOVER
# =========================================================

failover = FailoverManager(
    registry=provider_registry,
    reliability=reliability,
    provider_order=settings.providers,
    max_attempts=settings.max_failover_attempts,
)


# =========================================================
# LIFECYCLE
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle.
    """

    logger.info(
        "Inference service starting",
        extra={
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "providers": settings.providers,
            "default_model": settings.default_model,
        },
    )

    yield
    logger.info("Inference service shutting down")
    await provider_registry.close()
    logger.info("Inference providers closed")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health() -> dict[str, str]:
    """
    Liveness probe.

    This endpoint only confirms that the process is alive.
    """

    return {
        "status": "ok",
    }


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """
    Readiness probe.

    At least one configured provider must be reachable.
    """

    for provider_name in settings.providers:
        try:
            provider = provider_registry.get(
                provider_name
            )

        except KeyError:
            continue

        if await provider.health():
            return {
                "status": "ready",
                "provider": provider.name,
            }
    logger.warning(
        "Inference service not ready: no providers available",
        extra={
            "providers": settings.providers,
        },
    )
    raise HTTPException(
        status_code=503,
        detail="No inference providers available",
    )


# =========================================================
# PROVIDERS
# =========================================================

@app.get("/v1/providers")
async def providers() -> dict[str, Any]:
    """
    List registered inference providers.
    """

    return {
        "object": "list",
        "data": [
            {
                "id": provider_name,
                "object": "provider",
            }
            for provider_name in provider_registry.list()
        ],
    }

    logger.info(
    "Inference providers registered",
    extra={
        "providers": provider_registry.list(),
    },
    )


# =========================================================
# MODELS
# =========================================================

@app.get("/v1/models")
async def models() -> dict[str, Any]:
    """
    List models exposed by Agenyx.
    """

    return {
        "object": "list",
        "data": [
            {
                "id": model.model_id,
                "object": model.object,
                "owned_by": model.owned_by,
            }
            for model in model_registry.list_models()
        ],
    }

    logger.info(
    "Inference models registered",
    extra={
        "models": [
            model.model_id
            for model in model_registry.list_models()
            ],
        },
    )

# =========================================================
# CHAT COMPLETIONS
# =========================================================

@app.post(
    "/v1/chat/completions",
    response_model=None,
)
async def chat_completions(
    request: Request,
) -> JSONResponse:
    """
    OpenAI-compatible chat completion endpoint.

    Request flow:

        client
          ↓
        validate request
          ↓
        resolve model
          ↓
        resolve provider
          ↓
        reliability check
          ↓
        provider request
          ↓
        response
    """
    start_time = time.perf_counter()
    # -----------------------------------------------------
    # Parse JSON
    # -----------------------------------------------------
    logger.info(
        "Inference request received",
        extra={
            "model": model.model_id,
            "provider": model.provider_name,
        },
    )
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
            detail=(
                "Request body must be a JSON object"
            ),
        )

    # -----------------------------------------------------
    # Validate messages
    # -----------------------------------------------------

    messages = payload.get("messages")

    if not isinstance(messages, list) or not messages:
        raise HTTPException(
            status_code=400,
            detail=(
                "Field 'messages' must be a "
                "non-empty list"
            ),
        )

    # -----------------------------------------------------
    # Resolve model
    # -----------------------------------------------------

    requested_model = payload.get(
        "model",
        settings.default_model,
    )

    if not isinstance(requested_model, str):
        raise HTTPException(
            status_code=400,
            detail="Field 'model' must be a string",
        )

    try:
        model = model_registry.get(
            requested_model
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    # Always send the actual registered model ID
    # to the backend.
    payload["model"] = model.model_id

    # -----------------------------------------------------
    # Streaming
    # -----------------------------------------------------

    if payload.get("stream") is True:
        raise HTTPException(
            status_code=501,
            detail="Streaming is not implemented yet",
        )

    # -----------------------------------------------------
    # Resolve provider
    # -----------------------------------------------------

    try:
        provider = provider_registry.get(
            model.provider_name
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Provider '{model.provider_name}' "
                "is not registered"
            ),
        ) from exc

    # -----------------------------------------------------
    # Reliability
    # -----------------------------------------------------

    if not reliability.allow_request(
        provider.name
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                f"Provider '{provider.name}' "
                "is currently unavailable"
            ),
        )

    # -----------------------------------------------------
    # Execute inference
    # -----------------------------------------------------

    try:
        response = await provider.chat_completion(
            payload
        )

    except Exception as exc:
        reliability.record_failure(
            provider.name
        )

        raise HTTPException(
            status_code=503,
            detail=(
                f"Inference failed for provider "
                f"'{provider.name}'"
            ),
        ) from exc

    reliability.record_success(
        provider.name
    )

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return JSONResponse(
        content=response,
        headers={
            "X-Agenyx-Provider": provider.name,
            "X-Agenyx-Model": model.model_id,
        },
    )


# =========================================================
# RELIABILITY
# =========================================================

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
                "circuit_state": (
                    state.circuit_state.value
                ),
                "consecutive_failures": (
                    state.consecutive_failures
                ),
                "total_failures": (
                    state.total_failures
                ),
                "total_successes": (
                    state.total_successes
                ),
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
                "circuit_opened_at": (
                    state.circuit_opened_at.isoformat()
                    if state.circuit_opened_at
                    else None
                ),
                "circuit_half_opened_at": (
                    state.circuit_half_opened_at.isoformat()
                    if state.circuit_half_opened_at
                    else None
                ),
            }
            for state in reliability.list_states()
        ],
    }
