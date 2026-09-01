import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import get_settings
from app.failover.manager import FailoverManager
from app.logger import logger
from app.metrics import (
    HTTP_ERRORS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    INFERENCE_REQUESTS_IN_PROGRESS,
    INFERENCE_REQUESTS_TOTAL,
    INFERENCE_REQUEST_DURATION_SECONDS,
)
from app.models import ModelDefinition, ModelRegistry
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.registry import ProviderRegistry
from app.reliability.manager import ReliabilityManager


# =========================================================
# SETTINGS
# =========================================================

settings = get_settings()


# =========================================================
# REGISTRIES
# =========================================================

provider_registry = ProviderRegistry()
model_registry = ModelRegistry()


# =========================================================
# RELIABILITY
# =========================================================

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

for provider_name in provider_registry.list():
    reliability.register(provider_name)


# =========================================================
# MODELS
# =========================================================

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


# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)


# =========================================================
# HTTP OBSERVABILITY
# =========================================================

@app.middleware("http")
async def prometheus_http_metrics(
    request: Request,
    call_next,
):
    """
    Record HTTP-level Prometheus metrics.

    The normalized FastAPI route is used instead of the raw URL
    to prevent high-cardinality Prometheus labels.

    Example:

        /users/123
        /users/456
        /users/789

    are all represented as:

        /users/{user_id}
    """

    start = time.perf_counter()

    method = request.method

    route = request.scope.get("route")
    route_name = getattr(route, "path", None)

    if not route_name:
        route_name = request.url.path

    HTTP_REQUESTS_IN_PROGRESS.labels(
        method=method,
        route=route_name,
    ).inc()

    try:
        response = await call_next(request)

        status_code = str(response.status_code)

        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            route=route_name,
            status_code=status_code,
        ).inc()

        if response.status_code >= 400:
            HTTP_ERRORS_TOTAL.labels(
                method=method,
                route=route_name,
                status_code=status_code,
            ).inc()

        return response

    except Exception:
        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            route=route_name,
            status_code="500",
        ).inc()

        HTTP_ERRORS_TOTAL.labels(
            method=method,
            route=route_name,
            status_code="500",
        ).inc()

        raise

    finally:
        duration = time.perf_counter() - start

        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=method,
            route=route_name,
        ).observe(duration)

        HTTP_REQUESTS_IN_PROGRESS.labels(
            method=method,
            route=route_name,
        ).dec()


# =========================================================
# METRICS
# =========================================================

@app.get(
    "/metrics",
    include_in_schema=False,
)
async def metrics() -> Response:
    """
    Prometheus metrics endpoint.
    """

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
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

    logger.debug("Health check requested")

    return {
        "status": "ok",
    }


# =========================================================
# READINESS
# =========================================================

@app.get("/ready")
async def ready() -> dict[str, Any]:
    """
    Readiness probe.

    At least one configured provider must be reachable.
    """

    for provider_name in settings.providers:
        try:
            provider = provider_registry.get(provider_name)

        except KeyError:
            logger.warning(
                "Configured provider is not registered",
                extra={
                    "provider": provider_name,
                },
            )
            continue

        if await provider.health():
            logger.debug(
                "Inference service ready",
                extra={
                    "provider": provider.name,
                },
            )

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

    provider_list = provider_registry.list()

    logger.info(
        "Inference providers listed",
        extra={
            "providers": provider_list,
        },
    )

    return {
        "object": "list",
        "data": [
            {
                "id": provider_name,
                "object": "provider",
            }
            for provider_name in provider_list
        ],
    }


# =========================================================
# MODELS
# =========================================================

@app.get("/v1/models")
async def models() -> dict[str, Any]:
    """
    List models exposed by Agenyx.
    """

    model_list = model_registry.list_models()

    logger.info(
        "Inference models listed",
        extra={
            "models": [
                model.model_id
                for model in model_list
            ],
        },
    )

    return {
        "object": "list",
        "data": [
            {
                "id": model.model_id,
                "object": model.object,
                "owned_by": model.owned_by,
            }
            for model in model_list
        ],
    }


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
    """

    request_start = time.perf_counter()

    # -----------------------------------------------------
    # Parse JSON
    # -----------------------------------------------------

    try:
        payload = await request.json()

    except Exception as exc:
        logger.warning(
            "Inference request contained invalid JSON",
            extra={
                "error_type": type(exc).__name__,
            },
        )

        raise HTTPException(
            status_code=400,
            detail="Invalid JSON request",
        ) from exc

    if not isinstance(payload, dict):
        logger.warning(
            "Inference request body is not a JSON object"
        )

        raise HTTPException(
            status_code=400,
            detail="Request body must be a JSON object",
        )

    # -----------------------------------------------------
    # Validate messages
    # -----------------------------------------------------

    messages = payload.get("messages")

    if not isinstance(messages, list) or not messages:
        logger.warning(
            "Inference request contains invalid messages"
        )

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
        logger.warning(
            "Inference request contains invalid model field",
            extra={
                "model": requested_model,
            },
        )

        raise HTTPException(
            status_code=400,
            detail="Field 'model' must be a string",
        )

    try:
        model = model_registry.get(requested_model)

    except KeyError as exc:
        logger.warning(
            "Requested inference model not found",
            extra={
                "model": requested_model,
            },
        )

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    payload["model"] = model.model_id

    logger.info(
        "Inference request received",
        extra={
            "model": model.model_id,
            "provider": model.provider_name,
        },
    )

    # -----------------------------------------------------
    # Streaming
    # -----------------------------------------------------

    if payload.get("stream") is True:
        logger.warning(
            "Streaming inference request rejected",
            extra={
                "model": model.model_id,
                "provider": model.provider_name,
            },
        )

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
        logger.error(
            "Inference provider is not registered",
            extra={
                "model": model.model_id,
                "provider": model.provider_name,
            },
        )

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

    if not reliability.allow_request(provider.name):
        logger.warning(
            "Inference request rejected by reliability manager",
            extra={
                "model": model.model_id,
                "provider": provider.name,
            },
        )

        INFERENCE_REQUESTS_TOTAL.labels(
            provider=provider.name,
            model=model.model_id,
            status="circuit_open",
        ).inc()

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

    INFERENCE_REQUESTS_IN_PROGRESS.labels(
        provider=provider.name,
        model=model.model_id,
    ).inc()

    provider_start = time.perf_counter()

    try:
        response = await provider.chat_completion(
            payload
        )

    except Exception as exc:
        provider_duration = (
            time.perf_counter() - provider_start
        )

        reliability.record_failure(
            provider.name
        )

        INFERENCE_REQUESTS_TOTAL.labels(
            provider=provider.name,
            model=model.model_id,
            status="error",
        ).inc()

        INFERENCE_REQUEST_DURATION_SECONDS.labels(
            provider=provider.name,
            model=model.model_id,
        ).observe(provider_duration)

        logger.error(
            "Inference request failed",
            extra={
                "model": model.model_id,
                "provider": provider.name,
                "error_type": type(exc).__name__,
                "latency_ms": round(
                    (
                        time.perf_counter()
                        - request_start
                    )
                    * 1000,
                    2,
                ),
            },
            exc_info=True,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                f"Inference failed for provider "
                f"'{provider.name}'"
            ),
        ) from exc

    else:
        provider_duration = (
            time.perf_counter() - provider_start
        )

        reliability.record_success(
            provider.name
        )

        INFERENCE_REQUESTS_TOTAL.labels(
            provider=provider.name,
            model=model.model_id,
            status="success",
        ).inc()

        INFERENCE_REQUEST_DURATION_SECONDS.labels(
            provider=provider.name,
            model=model.model_id,
        ).observe(provider_duration)

    finally:
        INFERENCE_REQUESTS_IN_PROGRESS.labels(
            provider=provider.name,
            model=model.model_id,
        ).dec()

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    latency_ms = round(
        (
            time.perf_counter()
            - request_start
        )
        * 1000,
        2,
    )

    logger.info(
        "Inference request completed",
        extra={
            "model": model.model_id,
            "provider": provider.name,
            "latency_ms": latency_ms,
        },
    )

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

    states = reliability.list_states()

    logger.debug(
        "Reliability status requested",
        extra={
            "provider_count": len(states),
        },
    )

    return {
        "object": "reliability",
        "providers": [
            {
                "provider": state.provider_name,
                "status": state.status.value,
                "circuit_state": state.circuit_state.value,
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
            for state in states
        ],
    }
