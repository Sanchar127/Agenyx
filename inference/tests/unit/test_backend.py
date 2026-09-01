import httpx
import pytest

from app.backend import OpenAICompatibleBackend


@pytest.fixture
def backend() -> OpenAICompatibleBackend:
    return OpenAICompatibleBackend(
        base_url="http://test-backend/v1",
        api_key="test-key",
        timeout=10.0,
        max_connections=10,
        max_keepalive_connections=5,
        max_retries=2,
    )


@pytest.mark.asyncio
async def test_chat_completion_success(backend):
    """
    Backend should return the provider response when the
    inference request succeeds.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == (
            "http://test-backend/v1/chat/completions"
        )

        assert request.headers["Authorization"] == (
            "Bearer test-key"
        )

        payload = request.content

        assert b"qwen2.5:7b" in payload

        return httpx.Response(
            status_code=200,
            json={
                "id": "test-response",
                "object": "chat.completion",
                "choices": [],
            },
            request=request,
        )

    transport = httpx.MockTransport(handler)

    backend.client = httpx.AsyncClient(
        transport=transport,
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

    try:
        result = await backend.chat_completion(payload)

        assert result == {
            "id": "test-response",
            "object": "chat.completion",
            "choices": [],
        }

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_does_not_retry_client_error(backend):
    """
    4xx errors should not be retried.
    """

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        return httpx.Response(
            status_code=400,
            json={
                "error": "bad request",
            },
            request=request,
        )

    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
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

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await backend.chat_completion(payload)

        assert attempts == 1

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_retries_transient_error(backend):
    """
    5xx transient errors should be retried.
    """

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts < 3:
            return httpx.Response(
                status_code=503,
                json={
                    "error": "service unavailable",
                },
                request=request,
            )

        return httpx.Response(
            status_code=200,
            json={
                "id": "success",
                "choices": [],
            },
            request=request,
        )

    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
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

    try:
        result = await backend.chat_completion(payload)

        assert result["id"] == "success"

        # Initial request + 2 retries.
        assert attempts == 3

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_fails_after_max_retries(backend):
    """
    If the provider continues returning a transient error,
    the backend should stop after max_retries.
    """

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        return httpx.Response(
            status_code=503,
            json={
                "error": "service unavailable",
            },
            request=request,
        )

    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
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

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await backend.chat_completion(payload)

        # max_retries=2 means:
        # initial request + 2 retries = 3 attempts.
        assert attempts == 3

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_retries_network_error(backend):
    """
    Network errors should be retried.
    """

    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts < 3:
            raise httpx.ConnectError(
                "connection failed",
                request=request,
            )

        return httpx.Response(
            status_code=200,
            json={
                "id": "success",
                "choices": [],
            },
            request=request,
        )

    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
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

    try:
        result = await backend.chat_completion(payload)

        assert result["id"] == "success"
        assert attempts == 3

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_rejects_invalid_payload(backend):
    """
    Payload must be a dictionary.
    """

    with pytest.raises(TypeError, match="payload must be a dictionary"):
        await backend.chat_completion(None)

    await backend.close()


@pytest.mark.asyncio
async def test_chat_completion_rejects_invalid_json_response(backend):
    """
    Provider returning invalid JSON should result in RuntimeError.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            content=b"not-json",
            request=request,
        )

    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
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

    try:
        with pytest.raises(
            RuntimeError,
            match="invalid JSON",
        ):
            await backend.chat_completion(payload)

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_health_returns_true_when_backend_is_available(backend):
    """
    Health check should return True for a successful provider response.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "data": [],
            },
            request=request,
        )

    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    )

    try:
        result = await backend.health()

        assert result is True

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_health_returns_false_when_backend_is_unavailable(backend):
    """
    Health check should return False when the provider is unreachable.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "connection failed",
            request=request,
        )

    backend.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    )

    try:
        result = await backend.health()

        assert result is False

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_close_closes_http_client(backend):
    """
    close() should close the underlying HTTP client.
    """

    assert backend.client.is_closed is False

    await backend.close()

    assert backend.client.is_closed is True
