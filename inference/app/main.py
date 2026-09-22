import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.auth import require_service_auth
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
from app.telemetry import configure_telemetry, instrument_app


# =========================================================
# API ERROR HELPERS
# =========================================================


def api_error(
    *,
    status_code: int,
    code: str,
    message: str,
) -> HTTPException:
    """
    Create a consistent API error response.

    All expected HTTP API errors use the following structure:

        {
            "detail": {
                "code": "...",
                "message": "..."
            }
        }
    """

    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
        },
    )


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

for provider_name in settings.providers:
    provider_registry.register(
        OpenAICompatibleProvider(
            provider_name=provider_name,
            base_url=settings.backend_base_url,
            api_key=settings.backend_api_key,
            timeout=settings.request_timeout_seconds,
            max_connections=settings.max_connections,
            max_keepalive_connections=settings.max_keepalive_connections,
            max_retries=settings.max_retries,
        )
    )

    reliability.register(provider_name)


# =========================================================
# MODELS
# =========================================================

for model_id, provider_name in settings.models:
    if provider_name not in provider_registry.list():
        raise ValueError(
            f"Model '{model_id}' references "
            f"unregistered provider '{provider_name}'"
        )

    model_registry.register(
        ModelDefinition(
            model_id=model_id,
            provider_name=provider_name,
        )
    )


# =========================================================
# FAILOVER
# =========================================================

model_routes: dict[str, tuple[str, ...]] = {
    model_id: (provider_name,)
    for model_id, provider_name in settings.models
}

for model_id, providers in settings.model_failover_providers.items():
    if model_id not in model_routes:
        raise ValueError(
            f"Failover route references "
            f"unregistered model '{model_id}'"
        )

    model_routes[model_id] = providers


failover = FailoverManager(
    registry=provider_registry,
    reliability=reliability,
    model_routes=model_routes,
    max_attempts=settings.max_failover_attempts,
)


# =========================================================
# TELEMETRY
# =========================================================

tracer_provider = configure_telemetry(settings)


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
            "models": [
                {
                    "model": model.model_id,
                    "provider": model.provider_name,
                }
                for model in model_registry.list_models()
            ],
            "default_model": settings.default_model,
        },
    )

    yield

    logger.info("Inference service shutting down")

    await provider_registry.close()

    logger.info("Inference providers closed")

    tracer_provider.shutdown()

    logger.info("Inference telemetry shut down")


# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

instrument_app(app)


# =========================================================
# ERROR HANDLING
# =========================================================


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Convert unexpected application exceptions into a safe,
    consistent HTTP 500 response.

    Internal exception details are logged server-side but are
    never exposed to the client.
    """

    logger.error(
        "Unhandled inference service exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "error_type": type(exc).__name__,
        },
        exc_info=True,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": (
                    "An unexpected internal error occurred."
                ),
            },
        },
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

    raise api_error(
        status_code=503,
        code="NO_PROVIDERS_AVAILABLE",
        message="No inference providers available",
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
    _: None = Depends(require_service_auth),
) -> JSONResponse:
    """
    OpenAI-compatible chat completion endpoint.
    """

    request_start = time.perf_counter()

    # -----------------------------------------------------
    # Parse JSON
    # -----------------------------------------------------

    try:
        body = await request.body()

    except Exception as exc:
        logger.warning(
            "Failed to read inference request body",
            extra={
                "error_type": type(exc).__name__,
            },
        )

        raise api_error(
            status_code=400,
            code="REQUEST_BODY_READ_FAILED",
            message="Unable to read request body",
        ) from exc

    if len(body) > settings.max_request_body_bytes:
        logger.warning(
            "Inference request body exceeds configured limit",
            extra={
                "body_bytes": len(body),
                "max_body_bytes": settings.max_request_body_bytes,
            },
        )

        raise api_error(
            status_code=413,
            code="REQUEST_BODY_TOO_LARGE",
            message=(
                "Request body exceeds the maximum allowed size "
                f"of {settings.max_request_body_bytes} bytes"
            ),
        )

    try:
        payload = await request.json()

    except Exception as exc:
        logger.warning(
            "Inference request contained invalid JSON",
            extra={
                "error_type": type(exc).__name__,
            },
        )

        raise api_error(
            status_code=400,
            code="INVALID_JSON",
            message="Invalid JSON request",
        ) from exc

    if not isinstance(payload, dict):
        logger.warning(
            "Inference request body is not a JSON object"
        )

        raise api_error(
            status_code=400,
            code="INVALID_REQUEST_BODY",
            message="Request body must be a JSON object",
        )

    # -----------------------------------------------------
    # Validate messages
    # -----------------------------------------------------

    messages = payload.get("messages")

    if not isinstance(messages, list) or not messages:
        logger.warning(
            "Inference request contains invalid messages"
        )

        raise api_error(
            status_code=400,
            code="INVALID_MESSAGES",
            message=(
                "Field 'messages' must be a "
                "non-empty list"
            ),
        )

    if len(messages) > settings.max_messages:
        logger.warning(
            "Inference request exceeds maximum message count",
            extra={
                "message_count": len(messages),
                "max_messages": settings.max_messages,
            },
        )

        raise api_error(
            status_code=400,
            code="TOO_MANY_MESSAGES",
            message=(
                "Field 'messages' exceeds the maximum allowed "
                f"count of {settings.max_messages}"
            ),
        )

    total_content_chars = 0

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            logger.warning(
                "Inference request contains invalid message",
                extra={
                    "message_index": index,
                },
            )

            raise api_error(
                status_code=400,
                code="INVALID_MESSAGE",
                message=(
                    f"Message at index {index} "
                    "must be a JSON object"
                ),
            )

        content = message.get("content")

        if content is None:
            continue

        if not isinstance(content, str):
            logger.warning(
                "Inference request contains invalid message content",
                extra={
                    "message_index": index,
                },
            )

            raise api_error(
                status_code=400,
                code="INVALID_MESSAGE_CONTENT",
                message=(
                    f"Message at index {index} "
                    "'content' must be a string"
                ),
            )

        content_chars = len(content)

        if content_chars > settings.max_message_content_chars:
            logger.warning(
                "Inference message content exceeds configured limit",
                extra={
                    "message_index": index,
                    "content_chars": content_chars,
                    "max_content_chars": (
                        settings.max_message_content_chars
                    ),
                },
            )

            raise api_error(
                status_code=400,
                code="MESSAGE_CONTENT_TOO_LARGE",
                message=(
                    f"Message at index {index} content exceeds "
                    "the maximum allowed size of "
                    f"{settings.max_message_content_chars} "
                    "characters"
                ),
            )

        total_content_chars += content_chars

    if (
        total_content_chars
        > settings.max_total_message_content_chars
    ):
        logger.warning(
            "Inference request exceeds total message content limit",
            extra={
                "total_content_chars": total_content_chars,
                "max_total_content_chars": (
                    settings.max_total_message_content_chars
                ),
            },
        )

        raise api_error(
            status_code=400,
            code="TOTAL_MESSAGE_CONTENT_TOO_LARGE",
            message=(
                "Total message content exceeds the maximum "
                "allowed size of "
                f"{settings.max_total_message_content_chars} "
                "characters"
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

        raise api_error(
            status_code=400,
            code="INVALID_MODEL",
            message="Field 'model' must be a string",
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

        raise api_error(
            status_code=404,
            code="MODEL_NOT_FOUND",
            message=f"Model '{requested_model}' was not found",
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

        raise api_error(
            status_code=501,
            code="STREAMING_NOT_IMPLEMENTED",
            message="Streaming is not implemented yet",
        )

    # -----------------------------------------------------
    # Execute inference with model-aware failover
    # -----------------------------------------------------

    INFERENCE_REQUESTS_IN_PROGRESS.labels(
        provider="failover",
        model=model.model_id,
    ).inc()

    request_provider_start = time.perf_counter()

    try:
        result = await failover.chat_completion(
            payload
        )

    except KeyError as exc:
        logger.error(
            "Inference failover route is not configured",
            extra={
                "model": model.model_id,
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )

        raise api_error(
            status_code=503,
            code="MODEL_UNAVAILABLE",
            message=(
                f"No inference route is configured "
                f"for model '{model.model_id}'"
            ),
        ) from exc

    except RuntimeError as exc:
        request_duration = (
            time.perf_counter()
            - request_provider_start
        )

        INFERENCE_REQUESTS_TOTAL.labels(
            provider="failover",
            model=model.model_id,
            status="error",
        ).inc()

        INFERENCE_REQUEST_DURATION_SECONDS.labels(
            provider="failover",
            model=model.model_id,
        ).observe(request_duration)

        logger.error(
            "Inference request exhausted failover providers",
            extra={
                "model": model.model_id,
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

        raise api_error(
            status_code=503,
            code="INFERENCE_FAILED",
            message=(
                f"Inference failed for model "
                f"'{model.model_id}'"
            ),
        ) from exc

    else:
        request_duration = (
            time.perf_counter()
            - request_provider_start
        )

        INFERENCE_REQUESTS_TOTAL.labels(
            provider=result.provider,
            model=model.model_id,
            status="success",
        ).inc()

        INFERENCE_REQUEST_DURATION_SECONDS.labels(
            provider=result.provider,
            model=model.model_id,
        ).observe(request_duration)

    finally:
        INFERENCE_REQUESTS_IN_PROGRESS.labels(
            provider="failover",
            model=model.model_id,
        ).dec()

    response = result.response
    provider = result.provider

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
            "provider": provider,
            "latency_ms": latency_ms,
        },
    )

    return JSONResponse(
        content=response,
        headers={
            "X-Agenyx-Provider": provider,
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
