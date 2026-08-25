import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import httpx


class InferenceBackend(ABC):
    """Abstract interface for an inference backend."""

    @abstractmethod
    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a non-streaming chat completion request."""
        raise NotImplementedError

    @abstractmethod
    async def chat_completion_stream(
        self,
        payload: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """Execute a streaming chat completion request."""
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        """Check whether the inference backend is available."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close backend resources."""
        raise NotImplementedError


class OpenAICompatibleBackend(InferenceBackend):
    """HTTP client for an OpenAI-compatible inference backend."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float,
        max_connections: int,
        max_keepalive_connections: int,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_retries = max_retries

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=min(timeout, 10.0),
                read=timeout,
                write=timeout,
                pool=timeout,
            ),
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            ),
        )

    @property
    def headers(self) -> dict[str, str]:
        """Build headers for provider requests."""

        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat_completion(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a non-streaming chat completion request."""

        url = f"{self.base_url}/chat/completions"

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.post(
                    url,
                    json=payload,
                    headers=self.headers,
                )

                # Never retry client errors.
                if 400 <= response.status_code < 500:
                    response.raise_for_status()

                # Retry transient provider failures.
                if response.status_code >= 500:
                    if attempt >= self.max_retries:
                        response.raise_for_status()

                    await self._backoff(attempt)
                    continue

                response.raise_for_status()

                try:
                    data = response.json()
                except ValueError as exc:
                    raise RuntimeError(
                        "Inference backend returned invalid JSON"
                    ) from exc

                if not isinstance(data, dict):
                    raise RuntimeError(
                        "Inference backend returned a non-object JSON response"
                    )

                return data

            except httpx.TimeoutException:
                if attempt >= self.max_retries:
                    raise

                await self._backoff(attempt)

            except httpx.ConnectError:
                if attempt >= self.max_retries:
                    raise

                await self._backoff(attempt)

            except httpx.NetworkError:
                if attempt >= self.max_retries:
                    raise

                await self._backoff(attempt)

        raise RuntimeError("Inference request failed")

    async def chat_completion_stream(
        self,
        payload: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """
        Stream an OpenAI-compatible chat completion response.

        The provider response is forwarded without buffering the
        complete response in memory.
        """

        url = f"{self.base_url}/chat/completions"

        # Streaming requests should not be retried after the response
        # has started. Retrying could result in duplicated tokens.
        try:
            async with self.client.stream(
                "POST",
                url,
                json=payload,
                headers=self.headers,
            ) as response:

                # Surface provider errors before yielding any data.
                if response.status_code >= 400:
                    body = await response.aread()

                    error = httpx.Response(
                        status_code=response.status_code,
                        headers=response.headers,
                        content=body,
                        request=response.request,
                    )

                    error.raise_for_status()

                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk

        except httpx.HTTPError:
            raise

    async def _backoff(
        self,
        attempt: int,
    ) -> None:
        """Apply exponential backoff between retries."""

        delay = 0.5 * (2**attempt)
        await asyncio.sleep(delay)

    async def health(self) -> bool:
        """Check whether the backend is reachable."""

        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
            )

            return response.status_code < 500

        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""

        if not self.client.is_closed:
            await self.client.aclose()
