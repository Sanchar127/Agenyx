from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app, reliability


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture(autouse=True)
def reset_reliability():
    provider_name = "ollama-local"

    state = reliability.get(provider_name)

    state.consecutive_failures = 0
    state.total_failures = 0
    state.total_successes = 0
    state.last_failure_at = None
    state.last_success_at = None
    state.circuit_opened_at = None
    state.circuit_half_opened_at = None

    state.status = type(
        state.status
    ).HEALTHY

    state.circuit_state = type(
        state.circuit_state
    ).CLOSED

    yield


@pytest.mark.asyncio
async def test_success_records_reliability_success(client):
    expected_response = {
        "id": "chatcmpl-success",
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
            },
        )

    assert response.status_code == 200

    state = reliability.get(
        "ollama-local"
    )

    assert state.total_successes >= 1
    assert state.consecutive_failures == 0


@pytest.mark.asyncio
async def test_failure_records_reliability_failure(client):
    with patch(
        "app.main.provider_registry.get"
    ) as mock_get:

        provider = mock_get.return_value
        provider.name = "ollama-local"

        provider.chat_completion = AsyncMock(
            side_effect=RuntimeError(
                "backend failure"
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

    state = reliability.get(
        "ollama-local"
    )

    assert state.total_failures >= 1
    assert state.consecutive_failures >= 1


@pytest.mark.asyncio
async def test_repeated_failures_open_circuit(client):
    with patch(
        "app.main.provider_registry.get"
    ) as mock_get:

        provider = mock_get.return_value
        provider.name = "ollama-local"

        provider.chat_completion = AsyncMock(
            side_effect=RuntimeError(
                "backend failure"
            )
        )

        for _ in range(3):
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

    state = reliability.get(
        "ollama-local"
    )

    assert state.total_failures >= 3

    assert (
        state.circuit_state.value
        == "open"
    )


@pytest.mark.asyncio
async def test_open_circuit_rejects_request_without_calling_provider(
    client,
):
    state = reliability.get(
        "ollama-local"
    )

    state.circuit_state = type(
        state.circuit_state
    ).OPEN

    with patch(
        "app.main.provider_registry.get"
    ) as mock_get:

        provider = mock_get.return_value
        provider.name = "ollama-local"

        provider.chat_completion = AsyncMock()

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

    provider.chat_completion.assert_not_awaited()


@pytest.mark.asyncio
async def test_reliability_endpoint_reflects_provider_state(
    client,
):
    response = await client.get(
        "/v1/reliability"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["object"] == "reliability"

    assert isinstance(
        data["providers"],
        list,
    )

    providers = {
        item["provider"]: item
        for item in data["providers"]
    }

    assert "ollama-local" in providers

    provider = providers["ollama-local"]

    assert "status" in provider
    assert "circuit_state" in provider
    assert "consecutive_failures" in provider
    assert "total_failures" in provider
    assert "total_successes" in provider
