from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


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

    with TestClient(app) as test_client:
        yield test_client


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
        "detail": "No inference providers available",
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
        "detail": "No inference providers available",
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
        "detail": "Invalid JSON request",
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
        "detail": (
            "Request body must be a JSON object"
        ),
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
        "detail": (
            "Field 'messages' must be a "
            "non-empty list"
        ),
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
        "detail": (
            "Field 'messages' must be a "
            "non-empty list"
        ),
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
        "detail": (
            "Field 'messages' must be a "
            "non-empty list"
        ),
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
        "detail": "Field 'model' must be a string",
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
        "detail": (
            "Streaming is not implemented yet"
        ),
    }


# =========================================================
# CHAT COMPLETIONS - PROVIDER RESOLUTION
# =========================================================


def test_chat_completion_provider_not_registered(client):
    """
    A model whose provider is not registered should return
    HTTP 503.
    """

    fake_model = type(
        "FakeModel",
        (),
        {
            "model_id": "test-model",
            "provider_name": "missing-provider",
        },
    )()

    with patch(
        "app.main.model_registry.get",
        return_value=fake_model,
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "test-model",
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
        "detail": (
            "Provider 'missing-provider' "
            "is not registered"
        ),
    }


# =========================================================
# CHAT COMPLETIONS - RELIABILITY
# =========================================================


def test_chat_completion_rejected_by_reliability(client):
    """
    Requests must fail fast when the reliability manager
    does not allow traffic to the provider.
    """

    mock_provider = AsyncMock()
    mock_provider.name = "ollama-local"

    with patch(
        "app.main.provider_registry.get",
        return_value=mock_provider,
    ), patch(
        "app.main.reliability.allow_request",
        return_value=False,
    ):
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
        "detail": (
            "Provider 'ollama-local' "
            "is currently unavailable"
        ),
    }

    mock_provider.chat_completion.assert_not_awaited()


# =========================================================
# CHAT COMPLETIONS - SUCCESS
# =========================================================


def test_chat_completion_success(client):
    """
    A successful provider response should be returned to the
    client unchanged.
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

    mock_provider = AsyncMock()
    mock_provider.name = "ollama-local"
    mock_provider.chat_completion.return_value = (
        fake_response
    )

    with patch(
        "app.main.provider_registry.get",
        return_value=mock_provider,
    ), patch(
        "app.main.reliability.allow_request",
        return_value=True,
    ), patch(
        "app.main.reliability.record_success"
    ) as mock_record_success:

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

    assert (
        response.headers["X-Agenyx-Provider"]
        == "ollama-local"
    )

    assert (
        response.headers["X-Agenyx-Model"]
        == "qwen2.5:7b"
    )

    mock_provider.chat_completion.assert_awaited_once()

    mock_record_success.assert_called_once_with(
        "ollama-local"
    )


def test_chat_completion_passes_payload_to_provider(client):
    """
    The resolved model and original messages should be passed
    to the provider.
    """

    fake_response = {
        "id": "test",
        "object": "chat.completion",
        "choices": [],
    }

    mock_provider = AsyncMock()
    mock_provider.name = "ollama-local"
    mock_provider.chat_completion.return_value = (
        fake_response
    )

    with patch(
        "app.main.provider_registry.get",
        return_value=mock_provider,
    ):
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
                "temperature": 0.7,
            },
        )

    assert response.status_code == 200

    mock_provider.chat_completion.assert_awaited_once()

    payload = (
        mock_provider.chat_completion
        .await_args.args[0]
    )

    assert payload["model"] == "qwen2.5:7b"

    assert payload["messages"] == [
        {
            "role": "user",
            "content": "hello",
        }
    ]

    assert payload["temperature"] == 0.7


# =========================================================
# CHAT COMPLETIONS - FAILURE
# =========================================================


def test_chat_completion_provider_failure(client):
    """
    Provider exceptions should be converted to HTTP 503
    and recorded as reliability failures.
    """

    mock_provider = AsyncMock()
    mock_provider.name = "ollama-local"

    mock_provider.chat_completion.side_effect = (
        RuntimeError("backend unavailable")
    )

    with patch(
        "app.main.provider_registry.get",
        return_value=mock_provider,
    ), patch(
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

    assert response.status_code == 503

    assert response.json() == {
        "detail": (
            "Inference failed for provider "
            "'ollama-local'"
        ),
    }

    mock_record_failure.assert_called_once_with(
        "ollama-local"
    )


def test_chat_completion_does_not_record_success_on_failure(
    client,
):
    """
    A failed inference must never be recorded as a success.
    """

    mock_provider = AsyncMock()
    mock_provider.name = "ollama-local"

    mock_provider.chat_completion.side_effect = (
        RuntimeError("backend unavailable")
    )

    with patch(
        "app.main.provider_registry.get",
        return_value=mock_provider,
    ), patch(
        "app.main.reliability.record_failure"
    ), patch(
        "app.main.reliability.record_success"
    ) as mock_record_success:

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

    mock_record_success.assert_not_called()


# =========================================================
# RELIABILITY ENDPOINT
# =========================================================


def test_reliability_status(client):
    """
    Reliability endpoint should expose the current provider
    state.
    """

    response = client.get(
        "/v1/reliability"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["object"] == "reliability"

    assert isinstance(
        data["providers"],
        list,
    )

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

    from app.main import settings

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
            "default_model": settings.default_model,
        },
    )

    mock_logger.info.assert_any_call(
        "Inference service shutting down"
    )

    mock_logger.info.assert_any_call(
        "Inference providers closed"
    )
