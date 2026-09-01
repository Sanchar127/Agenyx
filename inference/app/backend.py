
import json

import httpx
import pytest

from app.backend import OpenAICompatibleBackend


# =========================================================
# HELPERS
# =========================================================


def create_backend(
    handler,
    *,
    max_retries: int = 2,
) -> OpenAICompatibleBackend:
    """
    Create a backend using httpx.MockTransport.

    No real network request is performed.
    """

    backend = OpenAICompatibleBackend(
        base_url="http://test-backend/v1",
        api_key="test-key",
        timeout=10.0,
        max_connections=10,
        max_keepalive_connections=5,
        max_retries=max_retries,
    )

    transport = httpx.MockTransport(handler)

    # Replace the real transport with the mock transport.
    backend.client._transport = transport

    return backend


def completion_payload(
    model: str = "qwen2.5:7b",
) -> dict:
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Hello",
            }
        ],
    }


# =========================================================
# CONFIGURATION
# =========================================================


def test_invalid_base_url() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleBackend(
            base_url="",
            api_key="test-key",
            timeout=10.0,
            max_connections=10,
            max_keepalive_connections=5,
        )


def test_invalid_timeout() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleBackend(
            base_url="http://test",
            api_key="test-key",
            timeout=0,
            max_connections=10,
            max_keepalive_connections=5,
        )


def test_invalid_max_connections() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleBackend(
            base_url="http://test",
            api_key="test-key",
            timeout=10,
            max_connections=0,
            max_keepalive_connections=0,
        )


def test_invalid_keepalive_connections() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleBackend(
            base_url="http://test",
            api_key="test-key",
            timeout=10,
            max_connections=5,
            max_keepalive_connections=10,
        )


def test_invalid_max_retries() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleBackend(
            base_url="http://test",
            api_key="test-key",
            timeout=10,
            max_connections=10,
            max_keepalive_connections=5,
            max_retries=-1,
        )


# =========================================================
# HEADERS
# =========================================================


@pytest.mark.asyncio
async def test_headers() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.headers["Authorization"] == (
            "Bearer test-key"
        )

        assert request.headers["Content-Type"] == (
            "application/json"
        )

        return httpx.Response(
            200,
            json={
                "id": "test",
            },
        )

    backend = create_backend(handler)

    try:
        response = await backend.chat_completion(
            completion_payload()
        )

        assert response["id"] == "test"

    finally:
        await backend.close()


# =========================================================
# SUCCESS
# =========================================================


@pytest.mark.asyncio
async def test_chat_completion_success() -> None:
    calls = 0

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        assert request.method == "POST"
        assert str(request.url) == (
            "http://test-backend/v1/chat/completions"
        )

        body = json.loads(request.content)

        assert body["model"] == "qwen2.5:7b"
        assert body["messages"]

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [],
            },
        )

    backend = create_backend(handler)

    try:
        response = await backend.chat_completion(
            completion_payload()
        )

        assert response["id"] == "chatcmpl-test"
        assert calls == 1

    finally:
        await backend.close()


# =========================================================
# CLIENT ERRORS
# =========================================================


@pytest.mark.asyncio
async def test_client_error_is_not_retried() -> None:
    calls = 0

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Invalid request",
                }
            },
        )

    backend = create_backend(
        handler,
        max_retries=2,
    )

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await backend.chat_completion(
                completion_payload()
            )

        assert calls == 1

    finally:
        await backend.close()


# =========================================================
# SERVER RETRIES
# =========================================================


@pytest.mark.asyncio
async def test_server_error_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls < 3:
            return httpx.Response(503)

        return httpx.Response(
            200,
            json={
                "id": "recovered",
            },
        )

    backend = create_backend(
        handler,
        max_retries=2,
    )

    async def no_sleep(
        delay: float,
    ) -> None:
        return None

    monkeypatch.setattr(
        backend,
        "_backoff",
        no_sleep,
    )

    try:
        response = await backend.chat_completion(
            completion_payload()
        )

        assert response["id"] == "recovered"
        assert calls == 3

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_retries_are_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        return httpx.Response(503)

    backend = create_backend(
        handler,
        max_retries=2,
    )

    async def no_sleep(
        delay: float,
    ) -> None:
        return None

    monkeypatch.setattr(
        backend,
        "_backoff",
        no_sleep,
    )

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await backend.chat_completion(
                completion_payload()
            )

        # Initial request + 2 retries.
        assert calls == 3

    finally:
        await backend.close()


# =========================================================
# TIMEOUT
# =========================================================


@pytest.mark.asyncio
async def test_timeout_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            raise httpx.ReadTimeout(
                "backend timeout",
                request=request,
            )

        return httpx.Response(
            200,
            json={
                "id": "after-timeout",
            },
        )

    backend = create_backend(
        handler,
        max_retries=1,
    )

    async def no_sleep(
        delay: float,
    ) -> None:
        return None

    monkeypatch.setattr(
        backend,
        "_backoff",
        no_sleep,
    )

    try:
        response = await backend.chat_completion(
            completion_payload()
        )

        assert response["id"] == "after-timeout"
        assert calls == 2

    finally:
        await backend.close()


# =========================================================
# NETWORK FAILURE
# =========================================================


@pytest.mark.asyncio
async def test_network_error_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            raise httpx.ConnectError(
                "connection failed",
                request=request,
            )

        return httpx.Response(
            200,
            json={
                "id": "connected",
            },
        )

    backend = create_backend(
        handler,
        max_retries=1,
    )

    async def no_sleep(
        delay: float,
    ) -> None:
        return None

    monkeypatch.setattr(
        backend,
        "_backoff",
        no_sleep,
    )

    try:
        response = await backend.chat_completion(
            completion_payload()
        )

        assert response["id"] == "connected"
        assert calls == 2

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_network_error_after_all_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        raise httpx.ConnectError(
            "connection failed",
            request=request,
        )

    backend = create_backend(
        handler,
        max_retries=2,
    )

    async def no_sleep(
        delay: float,
    ) -> None:
        return None

    monkeypatch.setattr(
        backend,
        "_backoff",
        no_sleep,
    )

    try:
        with pytest.raises(httpx.ConnectError):
            await backend.chat_completion(
                completion_payload()
            )

        assert calls == 3

    finally:
        await backend.close()


# =========================================================
# RESPONSE VALIDATION
# =========================================================


@pytest.mark.asyncio
async def test_invalid_json_response() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
        )

    backend = create_backend(handler)

    try:
        with pytest.raises(
            RuntimeError,
            match="invalid JSON",
        ):
            await backend.chat_completion(
                completion_payload()
            )

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_non_object_json_response() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                "not",
                "an",
                "object",
            ],
        )

    backend = create_backend(handler)

    try:
        with pytest.raises(
            RuntimeError,
            match="non-object JSON",
        ):
            await backend.chat_completion(
                completion_payload()
            )

    finally:
        await backend.close()


# =========================================================
# INVALID PAYLOAD
# =========================================================


@pytest.mark.asyncio
async def test_chat_completion_rejects_invalid_payload() -> None:
    backend = create_backend(
        lambda request: httpx.Response(200)
    )

    try:
        with pytest.raises(TypeError):
            await backend.chat_completion(
                "invalid"  # type: ignore[arg-type]
            )

    finally:
        await backend.close()


# =========================================================
# BACKOFF
# =========================================================


@pytest.mark.asyncio
async def test_backoff_uses_exponential_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def fake_sleep(
        delay: float,
    ) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        asyncio,
        "sleep",
        fake_sleep,
    )

    # Remove randomness for deterministic test.
    monkeypatch.setattr(
        random,
        "uniform",
        lambda start, end: 0.0,
    )

    backend = OpenAICompatibleBackend(
        base_url="http://test",
        api_key="test",
        timeout=10,
        max_connections=10,
        max_keepalive_connections=5,
    )

    try:
        await backend._backoff(0)
        await backend._backoff(1)
        await backend._backoff(2)

        assert delays == [
            0.5,
            1.0,
            2.0,
        ]

    finally:
        await backend.close()


# =========================================================
# STREAMING
# =========================================================


@pytest.mark.asyncio
async def test_streaming_success() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            200,
            content=(
                b'data: {"delta":"Hello"}\n\n'
                b'data: {"delta":" world"}\n\n'
            ),
            headers={
                "Content-Type": "text/event-stream",
            },
        )

    backend = create_backend(handler)

    chunks: list[bytes] = []

    try:
        async for chunk in backend.chat_completion_stream(
            completion_payload()
        ):
            chunks.append(chunk)

        body = b"".join(chunks)

        assert b"Hello" in body
        assert b"world" in body

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_streaming_client_error() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Bad request",
                }
            },
        )

    backend = create_backend(handler)

    try:
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in backend.chat_completion_stream(
                completion_payload()
            ):
                pass

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_streaming_server_error() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(
            503,
            json={
                "error": {
                    "message": "Unavailable",
                }
            },
        )

    backend = create_backend(handler)

    try:
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in backend.chat_completion_stream(
                completion_payload()
            ):
                pass

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_streaming_does_not_retry() -> None:
    calls = 0

    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1

        return httpx.Response(
            503,
            json={
                "error": {
                    "message": "Unavailable",
                }
            },
        )

    backend = create_backend(
        handler,
        max_retries=3,
    )

    try:
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in backend.chat_completion_stream(
                completion_payload()
            ):
                pass

        # Streaming intentionally performs only one request.
        assert calls == 1

    finally:
        await backend.close()


# =========================================================
# HEALTH
# =========================================================


@pytest.mark.asyncio
async def test_health_success() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == (
            "http://test-backend/v1/models"
        )

        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [],
            },
        )

    backend = create_backend(handler)

    try:
        assert await backend.health() is True

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_health_failure_on_server_error() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(503)

    backend = create_backend(handler)

    try:
        assert await backend.health() is False

    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_health_failure_on_network_error() -> None:
    async def handler(
        request: httpx.Request,
    ) -> httpx.Response:
        raise httpx.ConnectError(
            "backend unavailable",
            request=request,
        )

    backend = create_backend(handler)

    try:
        assert await backend.health() is False

    finally:
        await backend.close()


# =========================================================
# CLOSE
# =========================================================


@pytest.mark.asyncio
async def test_close() -> None:
    backend = OpenAICompatibleBackend(
        base_url="http://test",
        api_key="test",
        timeout=10,
        max_connections=10,
        max_keepalive_connections=5,
    )

    assert backend.client.is_closed is False

    await backend.close()

    assert backend.client.is_closed is True


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    backend = OpenAICompatibleBackend(
        base_url="http://test",
        api_key="test",
        timeout=10,
        max_connections=10,
        max_keepalive_connections=5,
    )

    await backend.close()
    await backend.close()

    assert backend.client.is_closed is True
