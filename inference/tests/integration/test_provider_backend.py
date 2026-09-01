from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.backend import OpenAICompatibleBackend
from app.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


@pytest.mark.asyncio
async def test_provider_calls_backend():
    provider = OpenAICompatibleProvider(
        provider_name="test-provider",
        base_url="http://inference",
        api_key="test-key",
        timeout=5.0,
        max_connections=10,
        max_keepalive_connections=5,
        max_retries=2,
    )

    expected_response = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [],
    }

    with patch.object(
        provider.backend,
        "chat_completion",
        new_callable=AsyncMock,
        return_value=expected_response,
    ) as mock_backend:

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

    assert response == expected_response

    mock_backend.assert_awaited_once_with(
        payload
    )

    await provider.close()


@pytest.mark.asyncio
async def test_backend_sends_openai_compatible_request():
    backend = OpenAICompatibleBackend(
        provider_name="test-provider",
        base_url="http://inference",
        api_key="test-key",
        timeout=5.0,
        max_connections=10,
        max_keepalive_connections=5,
        max_retries=0,
    )

    expected_response = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [],
    }

    request = httpx.Request(
        "POST",
        "http://inference/chat/completions",
    )

    response = httpx.Response(
        status_code=200,
        json=expected_response,
        request=request,
    )

    request_mock = AsyncMock(
        return_value=response
    )

    with patch.object(
        backend.client,
        "post",
        request_mock,
    ):
        payload = {
            "model": "qwen2.5:7b",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                }
            ],
        }

        result = await backend.chat_completion(
            payload
        )

    assert result == expected_response

    request_mock.assert_awaited_once()

    call = request_mock.call_args

    assert call.args[0] == (
        "http://inference/chat/completions"
    )

    assert call.kwargs["json"] == payload

    assert (
        call.kwargs["headers"]["Authorization"]
        == "Bearer test-key"
    )

    await backend.close()


@pytest.mark.asyncio
async def test_backend_retry_integrates_with_provider():
    provider = OpenAICompatibleProvider(
        provider_name="test-provider",
        base_url="http://inference",
        api_key="test-key",
        timeout=5.0,
        max_connections=10,
        max_keepalive_connections=5,
        max_retries=2,
    )

    success_response = {
        "id": "chatcmpl-success",
        "object": "chat.completion",
        "choices": [],
    }

    first_request = httpx.Request(
        "POST",
        "http://inference/chat/completions",
    )

    second_request = httpx.Request(
        "POST",
        "http://inference/chat/completions",
    )

    responses = [
        httpx.Response(
            status_code=503,
            request=first_request,
        ),
        httpx.Response(
            status_code=200,
            json=success_response,
            request=second_request,
        ),
    ]

    async def fake_post(*args, **kwargs):
        return responses.pop(0)

    with patch.object(
        provider.backend.client,
        "post",
        side_effect=fake_post,
    ) as mock_post, patch.object(
        provider.backend,
        "_backoff",
        new_callable=AsyncMock,
    ):

        response = await provider.chat_completion(
            {
                "model": "qwen2.5:7b",
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello",
                    }
                ],
            }
        )

    assert response == success_response

    assert mock_post.await_count == 2

    await provider.close()


@pytest.mark.asyncio
async def test_provider_health_uses_backend_health():
    provider = OpenAICompatibleProvider(
        provider_name="test-provider",
        base_url="http://inference",
        api_key="test-key",
        timeout=5.0,
        max_connections=10,
        max_keepalive_connections=5,
        max_retries=0,
    )

    with patch.object(
        provider.backend,
        "health",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_health:

        healthy = await provider.health()

    assert healthy is True

    mock_health.assert_awaited_once()

    await provider.close()
