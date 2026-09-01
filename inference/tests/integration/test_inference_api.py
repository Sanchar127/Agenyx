from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
    }


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


@pytest.mark.asyncio
async def test_chat_completion_provider_failure(client):
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
    assert "Inference failed" in response.json()["detail"]
