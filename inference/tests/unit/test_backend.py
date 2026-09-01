import httpx
import pytest

from app.backend import OpenAICompatibleBackend


@pytest.fixture
def backend() -> OpenAICompatibleBackend:
    return OpenAICompatibleBackend(
        base_url="http://ollama:11434/v1",
        api_key="ollama",
        timeout=10.0,
        max_connections=10,
        max_keepalive_connections=5,
        max_retries=2,
    )


@pytest.mark.asyncio
async def test_chat_completion_success(backend):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "id": "test-id",
                "object": "chat.completion",
                "choices": [],
            },
        )
    )

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(transport=transport)

    response = await backend.chat_completion(
        {
            "model": "qwen2.5:7b",
            "messages": [
                {"role": "user", "content": "Hello"},
            ],
        }
    )

    assert response["id"] == "test-id"
    assert response["object"] == "chat.completion"

    await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_client_error_does_not_retry(backend):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1

        return httpx.Response(
            400,
            json={"error": "bad request"},
        )

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    with pytest.raises(httpx.HTTPStatusError):
        await backend.chat_completion(
            {
                "model": "qwen2.5:7b",
                "messages": [],
            }
        )

    assert calls == 1

    await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_retries_on_503(backend):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1

        if calls < 3:
            return httpx.Response(503)

        return httpx.Response(
            200,
            json={
                "id": "success",
                "choices": [],
            },
        )

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    backend._backoff = lambda attempt: _no_sleep()

    response = await backend.chat_completion(
        {
            "model": "qwen2.5:7b",
            "messages": [],
        }
    )

    assert response["id"] == "success"
    assert calls == 3

    await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_fails_after_max_retries(backend):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    backend._backoff = lambda attempt: _no_sleep()

    with pytest.raises(httpx.HTTPStatusError):
        await backend.chat_completion(
            {
                "model": "qwen2.5:7b",
                "messages": [],
            }
        )

    assert calls == 3

    await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_invalid_json(backend):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=b"not-json",
        )
    )

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=transport
    )

    with pytest.raises(
        RuntimeError,
        match="invalid JSON",
    ):
        await backend.chat_completion(
            {
                "model": "qwen2.5:7b",
                "messages": [],
            }
        )

    await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_rejects_non_dict_payload(backend):
    with pytest.raises(
        TypeError,
        match="payload must be a dictionary",
    ):
        await backend.chat_completion([])

    await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_timeout_retries(backend):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout(
            "timeout",
            request=request,
        )

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    backend._backoff = lambda attempt: _no_sleep()

    with pytest.raises(httpx.TimeoutException):
        await backend.chat_completion(
            {
                "model": "qwen2.5:7b",
                "messages": [],
            }
        )

    assert calls == 3

    await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_network_error_retries(backend):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1

        raise httpx.ConnectError(
            "connection failed",
            request=request,
        )

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )

    backend._backoff = lambda attempt: _no_sleep()

    with pytest.raises(httpx.NetworkError):
        await backend.chat_completion(
            {
                "model": "qwen2.5:7b",
                "messages": [],
            }
        )

    assert calls == 3

    await backend.close()


@pytest.mark.asyncio
async def test_streaming_success(backend):
    async def handler(request):
        return httpx.Response(
            200,
            content=b"hello",
        )

    transport = httpx.MockTransport(handler)

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=transport
    )

    chunks = []

    async for chunk in backend.chat_completion_stream(
        {
            "model": "qwen2.5:7b",
            "messages": [],
            "stream": True,
        }
    ):
        chunks.append(chunk)

    assert b"".join(chunks) == b"hello"

    await backend.close()


@pytest.mark.asyncio
async def test_streaming_error(backend):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            500,
            content=b"server error",
        )
    )

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=transport
    )

    with pytest.raises(httpx.HTTPStatusError):
        async for _ in backend.chat_completion_stream(
            {
                "model": "qwen2.5:7b",
                "messages": [],
                "stream": True,
            }
        ):
            pass

    await backend.close()


@pytest.mark.asyncio
async def test_health_success(backend):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200)
    )

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=transport
    )

    assert await backend.health() is True

    await backend.close()


@pytest.mark.asyncio
async def test_health_failure(backend):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503)
    )

    await backend.client.aclose()
    backend.client = httpx.AsyncClient(
        transport=transport
    )

    assert await backend.health() is False

    await backend.close()


@pytest.mark.asyncio
async def test_close_backend(backend):
    assert backend.client.is_closed is False

    await backend.close()

    assert backend.client.is_closed is True

    # close should be safe multiple times
    await backend.close()


@pytest.mark.asyncio
async def _no_sleep():
    return None
