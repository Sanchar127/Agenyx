from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agent_runtime.retry_policy import RetryPolicy
from app.core.errors import (
    LLMConnectionError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.inference.client import InferenceClient
import time
from typing import Any

VALID_RESPONSE = {
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": "hello",
            }
        }
    ]
}


@pytest.fixture
def client() -> InferenceClient:
    return InferenceClient(
        base_url="http://inference:8004",
        retry_policy=RetryPolicy(
            max_attempts=3,
            base_delay=0,
            max_delay=0,
            jitter=False,
        ),
    )


@pytest.mark.asyncio
async def test_successful_request(
    client: InferenceClient,
) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = VALID_RESPONSE

    client._client.post = AsyncMock(
        return_value=response,
    )

    result = await client.complete(
        model="test-model",
        messages=[
            {
                "role": "user",
                "content": "hello",
            }
        ],
        tools=[],
    )

    assert result == VALID_RESPONSE
    client._client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_connection_error_is_retried(
    client: InferenceClient,
) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = VALID_RESPONSE

    client._client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("connection failed"),
            httpx.ConnectError("connection failed"),
            response,
        ]
    )

    result = await client.complete(
        model="test-model",
        messages=[],
        tools=[],
    )

    assert result == VALID_RESPONSE
    assert client._client.post.await_count == 3


@pytest.mark.asyncio
async def test_timeout_is_retried(
    client: InferenceClient,
) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = VALID_RESPONSE

    client._client.post = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("timeout"),
            response,
        ]
    )

    result = await client.complete(
        model="test-model",
        messages=[],
        tools=[],
    )

    assert result == VALID_RESPONSE
    assert client._client.post.await_count == 2


@pytest.mark.asyncio
async def test_http_500_is_retried(
    client: InferenceClient,
) -> None:
    failed_response = MagicMock()
    failed_response.status_code = 503
    failed_response.text = "service unavailable"

    success_response = MagicMock()
    success_response.status_code = 200
    success_response.json.return_value = VALID_RESPONSE

    client._client.post = AsyncMock(
        side_effect=[
            failed_response,
            success_response,
        ]
    )

    result = await client.complete(
        model="test-model",
        messages=[],
        tools=[],
    )

    assert result == VALID_RESPONSE
    assert client._client.post.await_count == 2


@pytest.mark.asyncio
async def test_http_400_is_not_retried(
    client: InferenceClient,
) -> None:
    response = MagicMock()
    response.status_code = 400
    response.text = "bad request"

    client._client.post = AsyncMock(
        return_value=response,
    )

    with pytest.raises(LLMResponseError):
        await client.complete(
            model="test-model",
            messages=[],
            tools=[],
        )

    client._client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_json_is_not_retried(
    client: InferenceClient,
) -> None:
    response = MagicMock()
    response.status_code = 200
    response.text = "not-json"
    response.json.side_effect = ValueError(
        "invalid json"
    )

    client._client.post = AsyncMock(
        return_value=response,
    )

    with pytest.raises(LLMResponseError):
        await client.complete(
            model="test-model",
            messages=[],
            tools=[],
        )

    client._client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_exhaustion_raises_final_error(
    client: InferenceClient,
) -> None:
    client._client.post = AsyncMock(
        side_effect=httpx.ConnectError(
            "connection failed"
        )
    )

    with pytest.raises(LLMConnectionError):
        await client.complete(
            model="test-model",
            messages=[],
            tools=[],
        )

    assert client._client.post.await_count == 3


@pytest.mark.asyncio
async def test_retry_delay_is_applied(
    client: InferenceClient,
) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = VALID_RESPONSE

    client._client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("connection failed"),
            response,
        ]
    )

    with patch(
        "app.inference.client.asyncio.sleep",
        new_callable=AsyncMock,
    ) as sleep:
        result = await client.complete(
            model="test-model",
            messages=[],
            tools=[],
        )

    assert result == VALID_RESPONSE
    sleep.assert_awaited_once_with(0)

@pytest.mark.asyncio
async def test_retry_stops_when_deadline_cannot_accommodate_backoff() -> None:
    client = InferenceClient(
        base_url="http://inference",
        retry_policy=RetryPolicy(
            max_attempts=3,
            base_delay=1.0,
            max_delay=1.0,
            jitter=False,
        ),
    )

    attempts = 0

    async def fake_complete_once(
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        nonlocal attempts

        attempts += 1

        raise LLMConnectionError(
            "temporary failure"
        )

    client._complete_once = fake_complete_once

    deadline = time.monotonic() + 0.01

    with pytest.raises(
        LLMConnectionError,
        match="temporary failure",
    ):
        await client.complete(
            model="test-model",
            messages=[],
            tools=[],
            deadline=deadline,
        )

    assert attempts == 1

    await client.close()
