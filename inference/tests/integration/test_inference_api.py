from unittest.mock import AsyncMock, patch

import pytest


# =========================================================
# HEALTH
# =========================================================


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
    }


# =========================================================
# PROVIDERS
# =========================================================


@pytest.mark.asyncio
async def test_providers_endpoint(client):
    response = await client.get("/v1/providers")

    assert response.status_code == 200

    data = response.json()

    assert data["object"] == "list"
    assert isinstance(data["data"], list)

    provider_ids = [
        provider["id"]
        for provider in data["data"]
    ]

    assert "ollama-local" in provider_ids


# =========================================================
# MODELS
# =========================================================


@pytest.mark.asyncio
async def test_models_endpoint(client):
    response = await client.get("/v1/models")

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


# =========================================================
# CHAT COMPLETIONS - SUCCESS
# =========================================================


@pytest.mark.asyncio
async def test_chat_completion_end_to_end(client):
    expected_response = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello from Agenyx",
                },
                "finish_reason": "stop",
            }
        ],
    }

    with patch(
        "app.main.provider_registry.get"
    ) as mock_get:
        provider = mock_get.return_value
        provider.name = "ollama-local"

        provider.chat_completion = AsyncMock(
            return_value=expected_response
        )

        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.json() == expected_response

    assert (
        response.headers["X-Agenyx-Provider"]
        == "ollama-local"
    )

    assert (
        response.headers["X-Agenyx-Model"]
        == "qwen2.5:7b"
    )

    provider.chat_completion.assert_awaited_once()

    payload = provider.chat_completion.call_args.args[0]

    assert payload["model"] == "qwen2.5:7b"
    assert payload["messages"][0]["content"] == "Hello"


# =========================================================
# CHAT COMPLETIONS - SSRF / PROVIDER ROUTING
# =========================================================


@pytest.mark.asyncio
async def test_chat_completion_cannot_override_provider_url(client):
    """
    Request fields that look like provider-routing controls
    must not change provider selection.

    The fields are passed through as ordinary payload fields,
    but provider resolution remains controlled by the model
    registry and configured provider registry.
    """
    expected_response = {
        "id": "chatcmpl-ssrf-test",
        "object": "chat.completion",
        "choices": [],
    }

    with patch(
        "app.main.provider_registry.get"
    ) as mock_get:
        provider = mock_get.return_value
        provider.name = "ollama-local"

        provider.chat_completion = AsyncMock(
            return_value=expected_response
        )

        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello",
                    }
                ],
                "base_url": "http://169.254.169.254",
                "provider_url": "http://attacker.example",
                "endpoint": "http://attacker.example",
            },
        )

    assert response.status_code == 200

    provider.chat_completion.assert_awaited_once()

    payload = provider.chat_completion.call_args.args[0]

    assert payload["model"] == "qwen2.5:7b"
    assert payload["messages"][0]["content"] == "Hello"

    # These fields are ordinary request payload fields.
    # They must never control the provider's outbound URL.
    assert payload["base_url"] == "http://169.254.169.254"
    assert payload["provider_url"] == "http://attacker.example"
    assert payload["endpoint"] == "http://attacker.example"

    # Provider selection remains configuration/model-registry driven.
    mock_get.assert_called_once_with("ollama-local")


# =========================================================
# CHAT COMPLETIONS - DEFAULT MODEL
# =========================================================


@pytest.mark.asyncio
async def test_chat_completion_default_model(client):
    expected_response = {
        "id": "chatcmpl-default",
        "object": "chat.completion",
        "choices": [],
    }

    with patch(
        "app.main.provider_registry.get"
    ) as mock_get:
        provider = mock_get.return_value
        provider.name = "ollama-local"

        provider.chat_completion = AsyncMock(
            return_value=expected_response
        )

        response = await client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello",
                    }
                ],
            },
        )

    assert response.status_code == 200

    provider.chat_completion.assert_awaited_once()

    payload = provider.chat_completion.call_args.args[0]

    assert "model" in payload


# =========================================================
# CHAT COMPLETIONS - MODEL VALIDATION
# =========================================================


@pytest.mark.asyncio
async def test_chat_completion_unknown_model(client):
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "does-not-exist",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
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


# =========================================================
# CHAT COMPLETIONS - STREAMING
# =========================================================


@pytest.mark.asyncio
async def test_chat_completion_streaming_rejected(client):
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5:7b",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
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
# CHAT COMPLETIONS - PROVIDER FAILURE
# =========================================================


@pytest.mark.asyncio
async def test_chat_completion_provider_failure(client):
    """
    Provider exceptions should be converted to HTTP 503.

    Internal provider exception details must not be exposed
    through the API response.
    """
    with patch(
        "app.main.provider_registry.get"
    ) as mock_get:
        provider = mock_get.return_value
        provider.name = "ollama-local"

        provider.chat_completion = AsyncMock(
            side_effect=RuntimeError(
                "backend unavailable"
            )
        )

        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5:7b",
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello",
                    }
                ],
            },
        )

    assert response.status_code == 503

    assert response.json() == {
        "detail": {
            "code": "INFERENCE_FAILED",
            "message": (
                "Inference failed for provider "
                "'ollama-local'"
            ),
        },
    }

    # Internal backend details must not leak to the client.
    assert "backend unavailable" not in response.text
