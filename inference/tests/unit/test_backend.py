from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.backend import OpenAICompatibleBackend


@pytest.fixture
def backend():
    backend = OpenAICompatibleBackend(
        provider_name="test-provider",
        base_url="http://inference",
        api_key="test-key",
        timeout=5.0,
        max_connections=10,
        max_keepalive_connections=5,
        max_retries=2,
    )

    yield backend


def make_response(
    status_code: int,
    *,
    json: dict | None = None,
) -> httpx.Response:
    request = httpx.Request(
        "POST",
        "http://inference/chat/completions",
    )

    return httpx.Response(
        status_code=status_code,
        json=json,
        request=request,
    )


@pytest.mark.asyncio
async def test_retryable_5xx_retries_then_succeeds(backend):
    success_response = {
        "id": "chatcmpl-success",
        "object": "chat.completion",
        "choices": [],
    }

    responses = [
        make_response(503),
        make_response(200, json=success_response),
    ]

    async def fake_post(*args, **kwargs):
        return responses.pop(0)

    with patch.object(
        backend.client,
        "post",
        side_effect=fake_post,
    ) as mock_post, patch.object(
        backend,
        "_backoff",
        new_callable=AsyncMock,
    ) as mock_backoff:
        result = await backend.chat_completion(
            {
                "model": "qwen2.5:7b",
                "messages": [],
            }
        )

    assert result == success_response
    assert mock_post.await_count == 2
    mock_backoff.assert_awaited_once_with(0)

    await backend.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [500, 502, 503, 504],
)
async def test_all_retryable_5xx_status_codes_retry(
    backend,
    status_code,
):
    success_response = {
        "id": "chatcmpl-success",
        "choices": [],
    }

    responses = [
        make_response(status_code),
        make_response(200, json=success_response),
    ]

    async def fake_post(*args, **kwargs):
        return responses.pop(0)

    with patch.object(
        backend.client,
        "post",
        side_effect=fake_post,
    ) as mock_post, patch.object(
        backend,
        "_backoff",
        new_callable=AsyncMock,
    ):
        result = await backend.chat_completion(
            {
                "model": "qwen2.5:7b",
                "messages": [],
            }
        )

    assert result == success_response
    assert mock_post.await_count == 2

    await backend.close()


@pytest.mark.asyncio
async def test_timeout_retries_then_succeeds(backend):
    success_response = {
        "id": "chatcmpl-success",
        "choices": [],
    }

    responses = [
        httpx.ReadTimeout("provider timed out"),
        make_response(200, json=success_response),
    ]

    async def fake_post(*args, **kwargs):
        result = responses.pop(0)

        if isinstance(result, Exception):
            raise result

        return result

    with patch.object(
        backend.client,
        "post",
        side_effect=fake_post,
    ) as mock_post, patch.object(
        backend,
        "_backoff",
        new_callable=AsyncMock,
    ) as mock_backoff:
        result = await backend.chat_completion(
            {
                "model": "qwen2.5:7b",
                "messages": [],
            }
        )

    assert result == success_response
    assert mock_post.await_count == 2
    mock_backoff.assert_awaited_once_with(0)

    await backend.close()


@pytest.mark.asyncio
async def test_network_error_retries_then_succeeds(backend):
    success_response = {
        "id": "chatcmpl-success",
        "choices": [],
    }

    responses = [
        httpx.ConnectError("connection failed"),
        make_response(200, json=success_response),
    ]

    async def fake_post(*args, **kwargs):
        result = responses.pop(0)

        if isinstance(result, Exception):
            raise result

        return result

    with patch.object(
        backend.client,
        "post",
        side_effect=fake_post,
    ) as mock_post, patch.object(
        backend,
        "_backoff",
        new_callable=AsyncMock,
    ):
        result = await backend.chat_completion(
            {
                "model": "qwen2.5:7b",
                "messages": [],
            }
        )

    assert result == success_response
    assert mock_post.await_count == 2

    await backend.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_code",
    [400, 401, 403, 404, 422],
)
async def test_4xx_is_not_retried(
    backend,
    status_code,
):
    response = make_response(status_code)

    with patch.object(
        backend.client,
        "post",
        new_callable=AsyncMock,
        return_value=response,
    ) as mock_post, patch.object(
        backend,
        "_backoff",
        new_callable=AsyncMock,
    ) as mock_backoff:
        with pytest.raises(httpx.HTTPStatusError):
            await backend.chat_completion(
                {
                    "model": "qwen2.5:7b",
                    "messages": [],
                }
            )

    mock_post.assert_awaited_once()
    mock_backoff.assert_not_awaited()

    await backend.close()


@pytest.mark.asyncio
async def test_retries_exhausted_raise_last_error(backend):
    responses = [
        make_response(503),
        make_response(503),
        make_response(503),
    ]

    async def fake_post(*args, **kwargs):
        return responses.pop(0)

    with patch.object(
        backend.client,
        "post",
        side_effect=fake_post,
    ) as mock_post, patch.object(
        backend,
        "_backoff",
        new_callable=AsyncMock,
    ) as mock_backoff:
        with pytest.raises(httpx.HTTPStatusError):
            await backend.chat_completion(
                {
                    "model": "qwen2.5:7b",
                    "messages": [],
                }
            )

    assert mock_post.await_count == 3
    assert mock_backoff.await_count == 2

    await backend.close()


@pytest.mark.asyncio
async def test_max_retries_zero_makes_one_request():
    backend = OpenAICompatibleBackend(
        provider_name="test-provider",
        base_url="http://inference",
        timeout=5.0,
        max_retries=0,
    )

    response = make_response(503)

    with patch.object(
        backend.client,
        "post",
        new_callable=AsyncMock,
        return_value=response,
    ) as mock_post, patch.object(
        backend,
        "_backoff",
        new_callable=AsyncMock,
    ) as mock_backoff:
        with pytest.raises(httpx.HTTPStatusError):
            await backend.chat_completion(
                {
                    "model": "qwen2.5:7b",
                    "messages": [],
                }
            )

    mock_post.assert_awaited_once()
    mock_backoff.assert_not_awaited()

    await backend.close()


@pytest.mark.asyncio
async def test_streaming_request_is_not_retried(backend):
    response = make_response(503)

    stream = AsyncMock()
    stream.__aenter__.return_value = response
    stream.__aexit__.return_value = False

    with patch.object(
        backend.client,
        "stream",
        return_value=stream,
    ) as mock_stream:
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in backend.chat_completion_stream(
                {
                    "model": "qwen2.5:7b",
                    "messages": [],
                }
            ):
                pass

    mock_stream.assert_called_once()

    await backend.close()
