from unittest.mock import AsyncMock

import pytest

from app.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


@pytest.fixture
def provider():
    provider = OpenAICompatibleProvider(
        provider_name="ollama-local",
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        timeout=10.0,
        max_connections=10,
        max_keepalive_connections=5,
        max_retries=2,
    )

    return provider


@pytest.mark.asyncio
async def test_provider_name(provider):
    assert provider.name == "ollama-local"

    await provider.close()


def test_provider_rejects_empty_name():
    with pytest.raises(
        ValueError,
        match="provider_name must not be empty",
    ):
        OpenAICompatibleProvider(
            provider_name="",
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            timeout=10.0,
            max_connections=10,
            max_keepalive_connections=5,
            max_retries=2,
        )


@pytest.mark.asyncio
async def test_chat_completion(provider):
    provider.backend.chat_completion = AsyncMock(
        return_value={
            "id": "test-id",
            "choices": [],
        }
    )

    payload = {
        "model": "qwen2.5:7b",
        "messages": [
            {
                "role": "user",
                "content": "Hello",
            }
        ],
    }

    response = await provider.chat_completion(
        payload
    )

    assert response["id"] == "test-id"

    provider.backend.chat_completion.assert_awaited_once_with(
        payload
    )

    await provider.close()


@pytest.mark.asyncio
async def test_chat_completion_requires_model(provider):
    with pytest.raises(
        ValueError,
        match="non-empty 'model'",
    ):
        await provider.chat_completion(
            {
                "messages": [],
            }
        )

    await provider.close()


@pytest.mark.asyncio
async def test_chat_completion_rejects_empty_model(provider):
    with pytest.raises(
        ValueError,
        match="non-empty 'model'",
    ):
        await provider.chat_completion(
            {
                "model": "",
                "messages": [],
            }
        )

    await provider.close()


@pytest.mark.asyncio
async def test_health(provider):
    provider.backend.health = AsyncMock(
        return_value=True
    )

    result = await provider.health()

    assert result is True

    provider.backend.health.assert_awaited_once()

    await provider.close()


@pytest.mark.asyncio
async def test_health_failure(provider):
    provider.backend.health = AsyncMock(
        return_value=False
    )

    result = await provider.health()

    assert result is False

    await provider.close()


@pytest.mark.asyncio
async def test_close(provider):
    provider.backend.close = AsyncMock()

    await provider.close()

    provider.backend.close.assert_awaited_once()
