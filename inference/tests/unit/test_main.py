from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, model_registry, reliability, settings


# =========================================================
# FIXTURES
# =========================================================


@pytest.fixture
def client():
    """
    Create a FastAPI test client.

    Using TestClient as a context manager ensures that the
    application's lifespan is executed.
    """
    settings.service_api_key = "test-service-key"

    with TestClient(
        app,
        headers={
            "X-Agenyx-Service-Key": "test-service-key",
        },
    ) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_reliability():
    """
    Reset provider reliability state between tests.
    """
    provider_name = "ollama-local"

    state = reliability._states[provider_name]

    state.consecutive_failures = 0
    state.total_failures = 0
    state.total_successes = 0
    state.last_failure_at = None
    state.last_success_at = None
    state.circuit_opened_at = None
    state.circuit_half_opened_at = None

    state.status = type(state.status).HEALTHY
    state.circuit_state = type(state.circuit_state).CLOSED

    reliability._half_open_probe.clear()

    yield


# =========================================================
# HEALTH
# =========================================================


def test_health(client):
    """
    Liveness endpoint should always return HTTP 200 when
    the application process is running.
    """
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }


# =========================================================
# READINESS
# =========================================================


def test_ready_when_provider_is_healthy(client):
    """
    Readiness should return 200 when at least one configured
    provider is healthy.
    """
    mock_provider = AsyncMock()
    mock_provider.name = "ollama-local"
    mock_provider.health.return_value = True

    with patch(
        "app.main.provider_registry.get",
        return_value=mock_provider,
    ):
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "provider": "ollama-local",
    }

    mock_provider.health.assert_awaited_once()


def test_ready_when_provider_is_unhealthy(client):
    """
    Readiness should return 503 when no provider is healthy.
    """
    mock_provider = AsyncMock()
    mock_provider.name = "ollama-local"
    mock_provider.health.return_value = False

    with patch(
        "app.main.provider_registry.get",
        return_value=mock_provider,
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "NO_PROVIDERS_AVAILABLE",
            "message": "No inference providers available",
        },
    }


def test_ready_skips_unregistered_provider(client):
    """
    An unknown configured provider should be skipped rather
    than crashing the readiness endpoint.
    """
    with patch(
        "app.main.provider_registry.get",
        side_effect=KeyError("unknown-provider"),
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "NO_PROVIDERS_AVAILABLE",
            "message": "No inference providers available",
        },
    }


# =========================================================
# PROVIDERS
# =========================================================


def test_list_providers(client):
    """
    Verify the provider listing endpoint.
    """
    response = client.get("/v1/providers")

    assert response.status_code == 200

    data = response.json()

    assert data["object"] == "list"
    assert isinstance(data["data"], list)

    provider_ids = [
        provider["id"]
        for provider in data["data"]
    ]

    assert "ollama-local" in provider_ids


def test_list_providers_structure(client):
    """
    Every provider entry should contain the expected fields.
    """
    response = client.get("/v1/providers")

    assert response.status_code == 200

    for provider in response.json()["data"]:
        assert "id" in provider
        assert "object" in provider
        assert provider["object"] == "provider"


# =========================================================
# MODELS
# =========================================================


def test_list_models(client):
    """
    Verify that registered models are exposed.
    """
    response = client.get("/v1/models")

    assert response.status_code == 200

    data = response.json()

    assert data["object"] == "list"
    assert isinstance(data["data"], list)

    model_ids = [
        model["id"]
        for model in data["data"]
    ]

    assert "qwen2.5:7b" in model_ids
    assert "llama3.2:3b" in model_ids


def test_list_models_structure(client):
    """
    Every model entry should contain the expected OpenAI-style
    model metadata.
    """
    response = client.get("/v1/models")

    assert response.status_code == 200

    for model in response.json()["data"]:
        assert "id" in model
        assert "object" in model
        assert "owned_by" in model


# =========================================================
# CHAT COMPLETIONS - REQUEST VALIDATION
# =========================================================


def test_chat_completion_invalid_json(client):
    """
    Invalid JSON should return HTTP 400.
    """
    response = client.post(
        "/v1/chat/completions",
        content="not-valid-json",
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "code": "INVALID_JSON",
            "message": "Invalid JSON request",
        },
    }


def test_chat_completion_requires_json_object(client):
    """
    Request body must be a JSON object.
    """
    response = client.post(
        "/v1/chat/completions",
        json=["invalid"],
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "code": "INVALID_REQUEST_BODY",
            "message": "Request body must be a JSON object",
        },
    }


def test_chat_completion_requires_messages(client):
    """
    messages must be present.
    """
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:7b",
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "code": "INVALID_MESSAGES",
            "message": (
                "Field 'messages' must be a "
                "non-empty list"
            ),
        },
    }


def test_chat_completion_rejects_empty_messages(client):
    """
    messages must contain at least one message.
    """
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:7b",
            "messages": [],
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "code": "INVALID_MESSAGES",
            "message": (
                "Field 'messages' must be a "
                "non-empty list"
            ),
        },
    }


def test_chat_completion_rejects_non_list_messages(client):
    """
    messages must be a list.
    """
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:7b",
            "messages": "hello",
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "code": "INVALID_MESSAGES",
            "message": (
                "Field 'messages' must be a "
                "non-empty list"
            ),
        },
    }


def test_chat_completion_rejects_non_string_model(client):
    """
    model must be a string when supplied.
    """
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": 123,
            "messages": [
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "code": "INVALID_MODEL",
            "message": "Field 'model' must be a string",
        },
    }


def test_chat_completion_unknown_model(client):
    """
    An unknown model should return HTTP 404.
    """
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "does-not-exist",
            "messages": [
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": {
            "code": "MODEL_NOT_FOUND",
            "message": (
                "Model 'does-not-exist' was not found"
            ),
        },
    }


def test_chat_completion_streaming_not_implemented(client):
    """
    Streaming is currently intentionally unsupported.
    """
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:7b",
            "messages": [
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
            "stream": True,
        },
    )

    assert response.status_code == 501

    assert response.json() == {
        "detail": {
            "code": "STREAMING_NOT_IMPLEMENTED",
            "message": "Streaming is not implemented yet",
        },
    }


# =========================================================
# CHAT COMPLETIONS - FAILOVER INTEGRATION
# =========================================================


def test_chat_completion_success(client):
    """
    A successful FailoverManager response should be returned
    to the client unchanged.

    Provider selection itself is tested in test_failover.py.
    """
    fake_response = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "qwen2.5:7b",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello!",
                },
                "finish_reason": "stop",
            }
        ],
    }

    mock_result = type(
        "FakeFailoverResult",
        (),
        {
            "response": fake_response,
            "provider": "ollama-local",
        },
    )()

    with patch(
        "app.main.failover.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_failover:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",
                "messages": [
                    {
                        "role": "user",
                        "content": "hello",
                    }
                ],
            },
        )

    assert response.status_code == 200

    assert response.json() == fake_response

    assert response.headers["X-Agenyx-Provider"] == "ollama-local"
    assert response.headers["X-Agenyx-Model"] == "qwen2.5:7b"

    mock_failover.assert_awaited_once_with(
        {
            "model": "qwen2.5:7b",
            "messages": [
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
        }
    )


def test_chat_completion_passes_payload_to_failover_manager(client):
    """
    The endpoint should pass the validated request payload to
    FailoverManager unchanged.
    """
    fake_response = {
        "id": "test",
        "object": "chat.completion",
        "choices": [],
    }

    mock_result = type(
        "FakeFailoverResult",
        (),
        {
            "response": fake_response,
            "provider": "ollama-local",
        },
    )()

    payload = {
        "model": "qwen2.5:7b",
        "messages": [
            {
                "role": "user",
                "content": "hello",
            }
        ],
        "temperature": 0.7,
    }

    with patch(
        "app.main.failover.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_failover:
        response = client.post(
            "/v1/chat/completions",
            json=payload,
        )

    assert response.status_code == 200

    mock_failover.assert_awaited_once_with(payload)


# =========================================================
# CHAT COMPLETIONS - FAILOVER EXHAUSTION
# =========================================================


def test_chat_completion_failover_exhausted(client):
    """
    When FailoverManager exhausts all providers, the endpoint
    should return HTTP 503.
    """
    with patch(
        "app.main.failover.chat_completion",
        new_callable=AsyncMock,
        side_effect=RuntimeError(
            "All failover providers failed for model "
            "'qwen2.5:7b'"
        ),
    ) as mock_failover:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",
                "messages": [
                    {
                        "role": "user",
                        "content": "hello",
                    }
                ],
            },
        )

    assert response.status_code == 503

    assert response.json() == {
        "detail": {
            "code": "INFERENCE_FAILED",
            "message": (
                "Inference failed for model "
                "'qwen2.5:7b'"
            ),
        },
    }

    mock_failover.assert_awaited_once()


def test_chat_completion_does_not_record_reliability_directly(
    client,
):
    """
    Reliability bookkeeping belongs to FailoverManager.

    The HTTP endpoint must not directly call record_success
    or record_failure.
    """
    fake_response = {
        "id": "test",
        "object": "chat.completion",
        "choices": [],
    }

    mock_result = type(
        "FakeFailoverResult",
        (),
        {
            "response": fake_response,
            "provider": "ollama-local",
        },
    )()

    with patch(
        "app.main.failover.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_result,
    ), patch(
        "app.main.reliability.record_success"
    ) as mock_record_success, patch(
        "app.main.reliability.record_failure"
    ) as mock_record_failure:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",
                "messages": [
                    {
                        "role": "user",
                        "content": "hello",
                    }
                ],
            },
        )

    assert response.status_code == 200

    mock_record_success.assert_not_called()
    mock_record_failure.assert_not_called()


def test_chat_completion_unconfigured_failover_route(client):
    """
    A missing failover route should be converted into HTTP 503.
    """
    with patch(
        "app.main.failover.chat_completion",
        new_callable=AsyncMock,
        side_effect=KeyError(
            "No failover route configured for model "
            "'qwen2.5:7b'"
        ),
    ) as mock_failover:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",
                "messages": [
                    {
                        "role": "user",
                        "content": "hello",
                    }
                ],
            },
        )

    assert response.status_code == 503

    assert response.json() == {
        "detail": {
            "code": "MODEL_UNAVAILABLE",
            "message": (
                "No inference route is configured "
                "for model 'qwen2.5:7b'"
            ),
        },
    }

    mock_failover.assert_awaited_once()


# =========================================================
# RELIABILITY ENDPOINT
# =========================================================


def test_reliability_status(client):
    """
    Reliability endpoint should expose the current provider
    state.
    """
    response = client.get("/v1/reliability")

    assert response.status_code == 200

    data = response.json()

    assert data["object"] == "reliability"
    assert isinstance(data["providers"], list)
    assert len(data["providers"]) >= 1

    provider = data["providers"][0]

    assert "provider" in provider
    assert "status" in provider
    assert "circuit_state" in provider
    assert "consecutive_failures" in provider
    assert "total_failures" in provider
    assert "total_successes" in provider
    assert "last_failure_at" in provider
    assert "last_success_at" in provider
    assert "circuit_opened_at" in provider
    assert "circuit_half_opened_at" in provider


# =========================================================
# LIFESPAN
# =========================================================


def test_lifespan_closes_provider_registry():
    """
    Application shutdown should close all provider resources.
    """
    with patch(
        "app.main.provider_registry.close",
        new_callable=AsyncMock,
    ) as mock_close:
        with TestClient(app):
            pass

        mock_close.assert_awaited_once()


def test_lifespan_logs_startup_and_shutdown():
    """
    Verify that application lifecycle logging is executed.
    """
    with patch(
        "app.main.provider_registry.close",
        new_callable=AsyncMock,
    ), patch(
        "app.main.logger"
    ) as mock_logger:
        with TestClient(app):
            pass

    mock_logger.info.assert_any_call(
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

    mock_logger.info.assert_any_call(
        "Inference service shutting down"
    )

    mock_logger.info.assert_any_call(
        "Inference providers closed"
    )


# =========================================================
# REQUEST LIMITS
# =========================================================


def test_chat_completion_rejects_too_many_messages(client):
    """
    Requests exceeding the configured message count limit
    should return HTTP 400.
    """
    with patch(
        "app.main.settings.max_messages",
        2,
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",
                "messages": [
                    {"role": "user", "content": "one"},
                    {"role": "user", "content": "two"},
                    {"role": "user", "content": "three"},
                ],
            },
        )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "code": "TOO_MANY_MESSAGES",
            "message": (
                "Field 'messages' exceeds the maximum "
                "allowed count of 2"
            ),
        },
    }


def test_chat_completion_rejects_non_object_message(client):
    """
    Every message must be a JSON object.
    """
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:7b",
            "messages": ["hello"],
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "code": "INVALID_MESSAGE",
            "message": (
                "Message at index 0 "
                "must be a JSON object"
            ),
        },
    }


def test_chat_completion_rejects_oversized_message_content(client):
    """
    Individual message content must stay within the configured
    character limit.
    """
    with patch(
        "app.main.settings.max_message_content_chars",
        10,
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",
                "messages": [
                    {
                        "role": "user",
                        "content": "a" * 11,
                    }
                ],
            },
        )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "code": "MESSAGE_CONTENT_TOO_LARGE",
            "message": (
                "Message at index 0 content exceeds "
                "the maximum allowed size of 10 characters"
            ),
        },
    }


def test_chat_completion_rejects_oversized_total_content(client):
    """
    Combined message content must stay within the configured
    total character limit.
    """
    with patch(
        "app.main.settings.max_total_message_content_chars",
        10,
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",
                "messages": [
                    {
                        "role": "user",
                        "content": "hello",
                    },
                    {
                        "role": "user",
                        "content": "world!",
                    },
                ],
            },
        )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "code": "TOTAL_MESSAGE_CONTENT_TOO_LARGE",
            "message": (
                "Total message content exceeds the maximum "
                "allowed size of 10 characters"
            ),
        },
    }


def test_chat_completion_rejects_oversized_body(client):
    """
    Request bodies larger than the configured limit should
    return HTTP 413 before JSON parsing or provider execution.
    """
    original_limit = settings.max_request_body_bytes
    settings.max_request_body_bytes = 100

    try:
        response = client.post(
            "/v1/chat/completions",
            content=b"x" * 101,
            headers={
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 413

        assert response.json() == {
            "detail": {
                "code": "REQUEST_BODY_TOO_LARGE",
                "message": (
                    "Request body exceeds the maximum allowed size "
                    "of 100 bytes"
                ),
            },
        }

    finally:
        settings.max_request_body_bytes = original_limit


# =========================================================
# UNEXPECTED EXCEPTIONS
# =========================================================


def test_unexpected_exception_returns_safe_500():
    """
    Unexpected application exceptions should be converted into
    a safe, consistent HTTP 500 response without leaking the
    internal exception details.
    """
    settings.service_api_key = "test-service-key"

    with patch(
        "app.main.provider_registry.list",
        side_effect=RuntimeError(
            "secret internal failure"
        ),
    ):
        with TestClient(
            app,
            headers={
                "X-Agenyx-Service-Key": "test-service-key",
            },
            raise_server_exceptions=False,
        ) as test_client:
            response = test_client.get("/v1/providers")

    assert response.status_code == 500

    assert response.json() == {
        "detail": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": (
                "An unexpected internal error occurred."
            ),
        },
    }

    assert "secret internal failure" not in response.text
